# routes/board.py
from flask import Blueprint, request, jsonify, session
from Server.models.board_dao import BoardDAO
from Server.models.user_dao import UserDAO
from Server.models.urlbert_dao import UrlBertDAO # UrlBertDAO 임포트 (3-2-1용)
from bot.qr_analysis import get_analysis_for_qr_scan 

board_bp = Blueprint("board", __name__, url_prefix="/board")

def _get_analysis_for_report(url: str) -> dict:
    """
    관리자 심사를 위한 URL 분석 헬퍼. 
    기존 /analyze 로직을 참조하되, 히스토리 저장이나 세션 관리는 제외합니다.
    """
    
    # 1. DB HIT (캐시 조회)
    if UrlBertDAO.exists(url):
        result = UrlBertDAO.find_by_url(url)

        if result and (result.get("label") in ("MALICIOUS", "LEGITIMATE")):
            label = (result.get("label") or "FAILED").upper()
            confidence = result.get("confidence")
            
            # DB 캐시 결과를 프론트엔드 형식에 맞춤
            text_result = f"DB 캐시: **{label}**로 판별됨 (신뢰도: {confidence*100:.1f}%)" if confidence else f"DB 캐시: **{label}**로 판별됨"
            
            return {
                "is_malicious": 1 if label == "MALICIOUS" else 0,
                "confidence": confidence,
                "text_result": text_result,
                "source": "db"
            }

    # 2. DB MISS → 모델 실행
    try:
        # 모델 파이프라인 호출 (내부적으로 urlbert_analysis에 upsert 수행)
        model_out = get_analysis_for_qr_scan(url)
        label = (model_out.get("label") or "FAILED").upper()
        confidence = model_out.get("confidence")

    except Exception as e:
        # current_app 임포트가 필요하며, Flask 앱 컨텍스트 내에서 실행되어야 함
        # 현재 코드 조각에는 current_app 임포트가 없으므로 임시로 주석 처리하거나,
        # 파일 맨 위 임포트에 `from flask import ..., current_app`을 추가해야 합니다.
        # current_app.logger.exception(f"모델 호출 실패: {e}") 
        label = "FAILED"
        confidence = None

    if label not in ("MALICIOUS", "LEGITIMATE"):
        return {
            "is_malicious": -1,
            "confidence": None,
            "text_result": "모델 분석 결과: **확인불가** 또는 실패" , 
            "source": "model"
        }
        
    text_result = f"URLBERT 모델: **{label}**로 판별됨 (신뢰도: {confidence*100:.1f}%)"
    
    return {
        "is_malicious": 1 if label == "MALICIOUS" else 0,
        "confidence": confidence,
        "text_result": text_result,
        "source": "model"
    }

@board_bp.route("/reports", methods=["GET"])
def get_reports():
    # 6. 신고 내역은 본인만 확인 가능 (ADMIN은 전체 조회)
    page = request.args.get("page", 1, type=int)
    size = request.args.get("size", 20, type=int)
    query = request.args.get("q", "")
    
    # 1. 사용자 ID(회원)와 신고 필터링 ID(회원 또는 게스트) 분리
    user_id = session.get("user_id") # 로그인된 회원 ID (권한 확인용)
    reporter_id = user_id or session.get("guest_id") # 필터링에 사용할 ID (회원 우선)

    if not reporter_id:
        # 1-1. 비회원(또는 유효한 세션 없음)일 때 신고 내역 확인 불가
        return jsonify({"items": [], "message": "로그인 또는 게스트 세션이 필요합니다."}), 401

    # 2. ADMIN 여부 확인
    is_admin = False
    if user_id:
        # DB에서 권한 조회 (user_id가 있을 때만 유효)
        user_role = UserDAO.find_user_role(user_id) 
        if user_role == 'ADMIN':
            is_admin = True
    
    try:
        # 3. BoardDAO.list_reports 호출 시 is_admin 인자 전달
        items = BoardDAO.list_reports(
            page=page, 
            size=size, 
            q=query, 
            reporter_id=reporter_id, # 본인 신고 내역 필터링을 위한 ID
            is_admin=is_admin # ✅ ADMIN이면 필터링 무시
        )
        print(f"[DEBUG] /reports response (Admin: {is_admin}): item_count={len(items)}, first_item={items[0] if items else 'None'}")
        return jsonify({"items": items})
    except Exception as e:
        print(f"[ERROR] get_reports fail: {e}")
        return jsonify({"items": [], "message": "목록 조회 실패"}), 500


@board_bp.route("/malicious", methods=["GET"])
def get_malicious():
    # 7. 악성 URL 목록은 모든 사용자 확인 가능
    page  = request.args.get("page", 1, type=int)
    size  = request.args.get("size", 20, type=int)
    query = request.args.get("q", "")
    items = BoardDAO.list_malicious(page=page, size=size, q=query)
    return jsonify({"items": items})

@board_bp.route("/report", methods=["POST"])
def submit_report():
    # 1. 비회원/2. USER 회원 모두 신고 가능
    data = request.get_json(silent=True) or {}
    url = (data.get("url") or "").strip()
    reason = (data.get("reason") or "").strip()

    if not url:
        return jsonify({"ok": False, "message": "URL은 필수입니다."}), 400

    # ✅ [수정] user_id가 없을 경우 guest_id를 fallback으로 사용
    reporter_id = session.get("user_id") or session.get("guest_id")
    reporter_nick = session.get("nickname") or session.get("guest_nick") or "익명"

    if not reporter_id:
        # 이 경우 '세션 ID를 확인할 수 없습니다' 에러가 발생하며 401을 반환합니다.
        return jsonify({"ok": False, "message": "세션 ID를 확인할 수 없습니다."}), 401

    try:
        rid = BoardDAO.create_report( # 이 함수는 이제 url_report 테이블에만 저장합니다.
            url=url, reason=reason,
            reporter_id=reporter_id, reporter_nick=reporter_nick
        )
        # 2-2. 신고 내역에 미확인 상태로 뜸
        return jsonify({"ok": True, "message": "신고가 접수되었습니다. 감사합니다.", "report_id": rid}), 201
    except Exception as e:
        # ✅ [수정 반영] 상세 오류 로그 출력
        print(f"[CRITICAL ERROR] submit_report DB fail: {type(e).__name__}: {e}")
        return jsonify({"ok": False, "message": f"저장 실패: 서버 오류가 발생했습니다."}), 500 # 프론트엔드에 상세 오류 노출 방지

# 3-1. 신고 내역의 URL을 클릭하면 URL 상태를 변경 (ADMIN만 가능)
@board_bp.route("/report/<int:report_id>/judgment", methods=["POST"])
def set_judgment(report_id: int):
    # 🚨 [ADMIN 체크] 3-1 요구사항
    user_id = session.get("user_id")
    if not user_id or UserDAO.find_user_role(user_id) != 'ADMIN':
        return jsonify({"ok": False, "message": "관리자 권한이 없습니다."}), 403
        
    data = request.get_json(silent=True) or {}
    judgment    = (data.get("judgment") or None)      # LEGITIMATE | MALICIOUS
    confidence  = data.get("confidence", None)        # 0~1 float
    updater_id = user_id

    # 3-2. 모델 판별 결과를 프론트에서 받은 후(별도 API) 상태 변경을 진행한다고 가정하고,
    # 여기서는 받은 judgment와 confidence만 업데이트합니다.

    try:
        # BoardDAO.update_judgment가 url_report 테이블 업데이트 및 upsert_board를 호출합니다.
        BoardDAO.update_judgment(report_id, judgment, confidence, updater_id) 
        return jsonify({"ok": True})
    except ValueError as ve:
        return jsonify({"ok": False, "message": str(ve)}), 400
    except Exception as e:
        print(f"[ERROR] set_judgment fail: {e}")
        return jsonify({"ok": False, "message": f"갱신 실패: {e}"}), 500

# 3-2. ADMIN용 URL 판별 결과 제공 API (프론트에서 URL 클릭 시 호출 가정)
@board_bp.route("/report/<int:report_id>/analyze", methods=["GET"])
def get_analysis_for_admin(report_id: int):
    # 🚨 [ADMIN 체크] 3-2 요구사항
    user_id = session.get("user_id")
    if not user_id or UserDAO.find_user_role(user_id) != 'ADMIN':
        return jsonify({"ok": False, "message": "관리자 권한이 없습니다."}), 403

    # 1. 신고 ID로 URL 가져오기
    report = BoardDAO.find_report_by_id(report_id)
    if not report:
        return jsonify({"ok": False, "message": "신고를 찾을 수 없습니다."}), 404
    
    url = report["url"]

    # 2. [변경] 새로운 헬퍼 함수를 사용하여 분석 로직 실행
    analysis_result = _get_analysis_for_report(url) 

    # [핵심 수정] datetime 객체를 ISO 문자열로 변환
    def date_to_iso(dt):
        return dt.isoformat() if hasattr(dt, 'isoformat') else dt

    # 3. 결과를 프론트로 반환 (3-2 요구사항)
    return jsonify({
        "ok": True,
        "id": report["id"],
        "url": report["url"],
        "domain": report.get("domain") or "도메인 정보 없음",
        "reason": report.get("reason") or "사유 없음",
        "status": report["status"], # '확인중', '정상', '악성' 등의 한글 상태
        "reporter_nick": report.get("reporter_nick") or "익명",
        "created_at": date_to_iso(report.get("created_at")),
        "status_updated_at": report["status_updated_at"].isoformat() if report.get("status_updated_at") else None,
        
        "analysis": analysis_result
    })