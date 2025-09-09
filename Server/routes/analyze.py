from flask import Blueprint, request, jsonify, session, current_app
from Server.models.history_dao import HistoryDAO
from Server.models.urlbert_dao import UrlBertDAO
from urllib.parse import urlparse
from datetime import datetime
import traceback

#모델 파이프라인을 그대로 사용
from bot.qr_analysis import get_analysis_for_qr_scan

analyze_bp = Blueprint("analyze", __name__, url_prefix="/analyze")

@analyze_bp.route("", methods=["POST"])      # /analyze
@analyze_bp.route("/", methods=["POST"])     # /analyze/
def analyze():
    try:
        data = request.get_json(silent=True) or {}   
        if not data:  # [추가] form/query 백업
            if request.form.get("url"):
                data = {"url": request.form.get("url")}
            elif request.args.get("url"):
                data = {"url": request.args.get("url")}

        current_app.logger.info(f"/analyze payload={data}") # 서버 콘솔에 찍힘

        raw_url = (data.get("url") or "").strip()
        if not raw_url:
            return jsonify({"error": "URL 데이터가 없습니다"}), 400

        # [추가] URL 정규화: 스킴이 없으면 http:// 를 붙여 파서가 깨지지 않도록
        url = raw_url
        parsed = urlparse(url)
        if not parsed.scheme:
            url = "http://" + url
            parsed = urlparse(url)

        # ✅ 모든 검색을 세션 로그에 누적(히스토리 DB 제한과 별개)
        try:
            log = session.get("all_searches", [])
            log.append({"url": url, "ts": datetime.now().strftime("%Y-%m-%d %H:%M:%S")})
            session["all_searches"] = log[-200:]
        except Exception:
            current_app.logger.exception("session search log append failed")

        # 세션/게스트 상태
        user_id  = session.get("user_id")
        guest_id = session.get("guest_id")
        is_guest_login = bool(session.get("is_guest", False))
        effective_id = user_id or guest_id
        is_non_member_mode = is_guest_login or (not user_id and guest_id)

        # 1) DB HIT
        if UrlBertDAO.exists(url):
            result = UrlBertDAO.find_by_url(url)

            if not result:
                # 실패 → 저장 안 함
                return jsonify({
                    "message": "DB 조회 실패",
                    "url": url,
                    "result": "FAILED",
                    "confidence": None,  # ★ 추가: 실패 시 None
                    "domain": parsed.hostname or "-",
                    "created": "-",
                    "expiry": "-",
                    "date": datetime.now().strftime("%Y-%m-%d %H:%M"),
                    "source": "db"
                }), 200

            label = (result.get("label") or "").upper()
            if label not in ("MALICIOUS", "LEGITIMATE"):
                return jsonify({
                    "message": "DB 라벨 비정상",
                    "url": url,
                    "result": "FAILED",
                    "confidence": None,  # ★ 추가
                    "domain": (result.get("domain") or parsed.hostname or "-"),
                    "created": str(result.get("created_date") or "-"),
                    "expiry": str(result.get("expiry_date") or "-"),
                    "date": datetime.now().strftime("%Y-%m-%d %H:%M"),
                    "source": "db"
                }), 200

            # 게스트 5개 제한(저장 시도할 때만)
            if is_non_member_mode and effective_id:
                if not HistoryDAO.can_guest_save_more(effective_id):
                    return jsonify({
                        "popup": True,
                        "message": "비회원은 최근 5개의 기록만 저장됩니다. 더 많은 정보를 원하시면 로그인하세요.",
                        "result": label,
                        "confidence": result.get("confidence"),  # ★ 팝업에도 같이 내려줌
                        "source": "db"
                    }), 200

            # 히스토리 저장
            if effective_id:
                try:
                    HistoryDAO.save_history(effective_id, url, label)
                except Exception:
                    current_app.logger.exception("history save failed")

            return jsonify({
                "message": "분석 완료된 URL입니다.",
                "url": url,
                "result": label,                           # MALICIOUS / LEGITIMATE
                "confidence": result.get("confidence"),    # ★ 추가: 신뢰도 그대로
                "domain": (result.get("domain") or parsed.hostname or "-"),
                "created": str(result.get("created_date") or "-"),
                "expiry": str(result.get("expiry_date") or "-"),
                "date": datetime.now().strftime("%Y-%m-%d %H:%M"),
                "source": "db"
            }), 200

        # 2) DB MISS → 모델 실행
        try:
            model_out = get_analysis_for_qr_scan(url)  # 내부에서 urlbert DB upsert 수행(성공 시)
            label_from_model = (model_out.get("label") or "").upper()  # MALICIOUS / LEGITIMATE
            conf_from_model = model_out.get("confidence")              # ★ 그대로 사용
        except Exception as e:
            current_app.logger.exception(f"모델 호출 실패: {e}")
            label_from_model = "FAILED"
            conf_from_model = None

        if label_from_model not in ("MALICIOUS", "LEGITIMATE"):
            # 모델 실패 → 저장 안 하고 FAILED 반환
            return jsonify({
                "message": "모델 분석 실패",
                "url": url,
                "result": "FAILED",
                "confidence": None,
                "date": datetime.now().strftime("%Y-%m-%d %H:%M"),
                "source": "model"
            }), 200

        result_label = label_from_model  # MALICIOUS / LEGITIMATE

        # 게스트 5개 제한(저장 시도할 때만)
        if is_non_member_mode and effective_id:
            if not HistoryDAO.can_guest_save_more(effective_id):
                return jsonify({
                    "popup": True,
                    "message": "비회원은 최근 5개의 기록만 저장됩니다. 더 많은 정보를 원하시면 로그인하세요.",
                    "result": result_label,
                    "confidence": conf_from_model,  # ★ 팝업에도 같이 내려줌
                    "source": "model"
                }), 200

        # 히스토리 저장 (FAILED 제외)
        if effective_id:
            try:
                HistoryDAO.save_history(effective_id, url, result_label)
            except Exception:
                current_app.logger.exception("history save failed")

        return jsonify({
            "message": "DB 미등록 - 모델 예측 결과 반영",
            "url": url,
            "result": result_label,               # MALICIOUS / LEGITIMATE
            "confidence": conf_from_model,        # ★ 추가
            "domain": parsed.hostname or "-",
            "created": "-",
            "expiry": "-",
            "date": datetime.now().strftime("%Y-%m-%d %H:%M"),
            "source": "model"
        }), 200

    except Exception:
        current_app.logger.exception("analyze error")
        # 총체적 예외 → FAILED (저장 금지)
        return jsonify({"message": "server error", "result": "FAILED"}), 200