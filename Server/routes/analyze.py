from flask import Blueprint, request, jsonify, session, current_app
from Server.models.history_dao import HistoryDAO
from Server.models.urlbert_dao import UrlBertDAO
from urllib.parse import urlparse
from datetime import datetime
#from time import time


from PIL import Image
import io, numpy as np
import traceback

#모델 파이프라인을 그대로 사용
from bot.qr_analysis import get_analysis_for_qr_scan

# 새로 만든 ocr_handler 모듈에서 URL 추출 함수를 가져옵니다.
from bot.ocr_handler import extract_valid_urls_from_image

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

        # URL 정규화: 스킴이 없으면 http:// 를 붙여 파서가 깨지지 않도록
        url = raw_url
        parsed = urlparse(url)
        if not parsed.scheme:
            url = "http://" + url
            parsed = urlparse(url)

        # 모든 검색을 세션 로그에 누적(히스토리 DB 제한과 별개)
        try:
            log = session.get("all_searches", [])
            log.append({"url": url, "ts": datetime.now().strftime("%Y-%m-%d %H:%M:%S")})
            session["all_searches"] = log[-200:]
        except Exception:
            current_app.logger.exception("session search log append failed")

        # 세션/게스트 상태
        # user_id  = session.get("user_id")
        # guest_id = session.get("guest_id")
        # is_guest_login = bool(session.get("is_guest", False))
        # effective_id = user_id or guest_id
        # is_non_member_mode = is_guest_login or (not user_id and guest_id)
        user_id  = session.get("user_id")
        guest_id = session.get("guest_id")
        is_logged_in = bool(user_id)
        effective_id = user_id if is_logged_in else guest_id
        is_non_member_mode = not is_logged_in

        # 1) DB HIT
        if UrlBertDAO.exists(url):
            result = UrlBertDAO.find_by_url(url)

            if not result:
                # 실패 → 저장 안 함
                return jsonify({
                    "message": "DB 조회 실패",
                    "url": url,
                    "result": "FAILED",
                    "confidence": None,  # 추가: 실패 시 None
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
                    "confidence": None,  # 추가
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
                        "confidence": result.get("confidence"),  # 팝업에도 같이 내려줌
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
                "confidence": result.get("confidence"),    # 추가: 신뢰도 그대로
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
            conf_from_model = model_out.get("confidence")              # 그대로 사용
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
                    "confidence": conf_from_model,  # 팝업에도 같이 내려줌
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
            "confidence": conf_from_model,        # 추가
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

# @analyze_bp.route("/ocr", methods=["POST"])
# def scan_ocr_image():
#     if 'image' not in request.files:
#         return jsonify({"error": "이미지 파일이 전송되지 않았습니다."}), 400

#     image_file = request.files['image']
#     image_content = image_file.read()

#     # --- 스로틀: 최근 0.6초 내 재요청은 조용히 204로 무시 ---
#     _now_for_throttle = datetime.now().timestamp()
#     _last_ts = session.get("ocr_last_ts") or 0
#     if (_now_for_throttle - _last_ts) < 0.6:
#         return ("", 204)
#     session["ocr_last_ts"] = _now_for_throttle

#     # --- 빈 프레임(너무 어둡거나/밝거나, 텍스트 대비 거의 없음) 차단 ---
#     try:
#         img = Image.open(io.BytesIO(image_content)).convert("L")  # grayscale
#         arr = np.array(img, dtype="uint8")
#         mean = float(arr.mean())
#         std  = float(arr.std())
#         # 너무 어둡거나(<=12) 너무 밝거나(>=243) 혹은 변별력 낮음(std<=6) → 무음 204
#         if mean <= 12 or mean >= 243 or std <= 6.0:
#             return ("", 204)
#     except Exception:
#         pass

#     try:
#         candidates = extract_valid_urls_from_image(image_content)

#         # 세션 상태
#         from time import time
#         now = time()
#         hist = session.get("ocr_hist", [])
#         hist.append({"ts": now, "cands": candidates[:5]})
#         hist = [h for h in hist if now - h["ts"] <= 3.5]
#         session["ocr_hist"] = hist

#         # 유사도 클러스터링 + 득표
#         from difflib import SequenceMatcher

#         def _merge_similar(urls, threshold=0.90):
#             groups = []
#             for u in urls:
#                 placed = False
#                 for g in groups:
#                     rep = g[0]
#                     if SequenceMatcher(a=rep.lower(), b=u.lower()).ratio() >= threshold:
#                         g.append(u)
#                         placed = True
#                         break
#                 if not placed:
#                     groups.append([u])
#             reps = {max(g, key=len): g for g in groups}
#             return reps

#         all_recent = []
#         for h in hist:
#             all_recent.extend(h["cands"])
#         grouped = _merge_similar(all_recent, threshold=0.90)

#         vote = {}
#         for rep, members in grouped.items():
#             count = 0
#             for h in hist:
#                 for u in h["cands"]:
#                     if any(SequenceMatcher(a=u.lower(), b=m.lower()).ratio() >= 0.90 for m in members):
#                         count += 1
#                         break
#             vote[rep] = count

#         primary_url = None
#         if vote:
#             top = sorted(vote.items(), key=lambda x: x[1], reverse=True)
#             top_url, top_votes = top[0]

#             MIN_VOTES = 2
#             consecutive = 0
#             last_match = False
#             for h in sorted(hist, key=lambda x: x["ts"]):
#                 matched = any(
#                     SequenceMatcher(a=top_url.lower(), b=u.lower()).ratio() >= 0.90
#                     for u in h["cands"]
#                 )
#                 consecutive = (consecutive + 1) if matched and last_match else (1 if matched else 0)
#                 last_match = matched

#             if top_votes >= MIN_VOTES and consecutive >= 2:
#                 primary_url = top_url

#         # 스티키: 직전 primary가 있으면 2초간 유지
#         sticky = session.get("ocr_primary") or {}
#         prev_url = sticky.get("url")
#         prev_ts  = sticky.get("ts") or 0
#         if prev_url and (now - prev_ts) <= 2.0:
#             # 새 primary가 있어도 표가 박빙이면 기존 유지
#             if primary_url is None:
#                 primary_url = prev_url

#         # primary 갱신
#         if primary_url:
#             session["ocr_primary"] = {"url": primary_url, "ts": now}
#         else:
#             # 확정 실패시 스티키는 유지하되, 오래되면 제거
#             if prev_url and (now - prev_ts) > 2.0:
#                 session.pop("ocr_primary", None)

#         # 로깅: 스팸 방지(변경시에만)
#         last_log = session.get("ocr_last_log") or ""
#         log_key = f"{primary_url}|{candidates[:3]}"
#         if log_key != last_log:
#             current_app.logger.info(f"[OCR] primary={primary_url} (top3={candidates[:3]})")
#             session["ocr_last_log"] = log_key

#         # 반환 정책:
#         # - primary 확정 전: 프런트가 /analyze 못 부르게 urls=[] 만 준다.
#         # - primary 확정 시: urls=[primary] 만 내려준다(명확성).
#         if primary_url:
#             return jsonify({
#                 "message": "primary 확정",
#                 "urls": [primary_url],
#                 "primary_url": primary_url
#             }), 200
#         else:
#             return jsonify({
#                 "message": "primary 미확정",
#                 "urls": [],               # ← 프런트가 자동 analyze 호출 못 하게
#                 "primary_url": None
#             }), 200

#     except Exception as e:
#         current_app.logger.exception("OCR scan failed")
#         return jsonify({"error": str(e)}),

@analyze_bp.route("/ocr", methods=["POST"])
def scan_ocr_image():
    # 1. 이미지 파일이 없는 경우 에러 반환
    if 'image' not in request.files:
        return jsonify({"error": "이미지 파일이 전송되지 않았습니다."}), 400

    image_file = request.files['image']
    image_content = image_file.read()

    # 2. 이미지 내용이 비어있는 경우 빈 목록 반환
    if not image_content:
        return jsonify({"urls": [], "message": "빈 이미지 파일입니다."}), 200

    # 3. (선택적) 간단한 이미지 유효성 검사 (너무 어둡거나 밝은 이미지 필터링)
    try:
        img = Image.open(io.BytesIO(image_content)).convert("L")
        arr = np.array(img, dtype="uint8")
        mean, std = float(arr.mean()), float(arr.std())
        if mean <= 12 or mean >= 243 or std <= 6.0:
            return jsonify({"urls": [], "message": "텍스트를 감지할 수 없는 이미지입니다."}), 200
    except Exception as e:
        current_app.logger.warning(f"OCR 이미지 유효성 검사 중 오류: {e}")
        # 유효성 검사에 실패해도 일단 OCR은 시도하도록 넘어갑니다.
        pass

    # 4. OCR 실행 및 결과 반환
    try:
        # ocr_handler.py의 함수를 호출하여 URL 후보 목록을 받습니다.
        candidates = extract_valid_urls_from_image(image_content)
        
        current_app.logger.info(f"[OCR] 최종 감지된 URL: {candidates}")

        # ▼▼▼▼▼ 핵심 수정 부분 ▼▼▼▼▼
        # 추출된 URL 목록을 JSON 형식으로 즉시 포장하여 반환합니다.
        return jsonify({
            "message": "OCR 분석 완료",
            "urls": candidates 
        })
        # ▲▲▲▲▲ 핵심 수정 부분 ▲▲▲▲▲

    except Exception as e:
        current_app.logger.exception("OCR 스캔 중 심각한 오류 발생")
        return jsonify({"error": "OCR 분석 중 서버에서 오류가 발생했습니다.", "details": str(e)}), 500