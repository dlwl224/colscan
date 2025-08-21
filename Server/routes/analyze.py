# from flask import Blueprint, request, jsonify, session
# from models.url_analysis_dao import UrlAnalysisDAO
# from models.scan_dao import ScanDAO
# from models.history_dao import HistoryDAO
# from models.urlonly_dao import UrlOnlyDAO 
# import datetime
# import uuid

# analyze_bp = Blueprint("analyze", __name__, url_prefix="/analyze")

# @analyze_bp.route("", methods=["POST"])   # ← /analyze
# @analyze_bp.route("/", methods=["POST"])  # ← /analyze/

# def analyze():
#     data = request.get_json(silent=True) or {}                     # [CHANGED] 안전 파싱
#     url = request.json.get("url")
#     if not url:
#         return jsonify({"error": "URL 데이터가 없습니다"}), 400

#     # ✅ URL 등록 여부 확인
#     if not UrlOnlyDAO.exists(url):
#         return jsonify({"message": "해당 URL은 아직 등록되지 않았습니다."}), 404

#     # ✅ 분석 결과 조회
#     result = UrlAnalysisDAO.find_by_url(url)
#     if result is None:
#         return jsonify({"message": "분석 데이터가 존재하지 않습니다."}), 404

#     # ✅ 로그인/비회원 사용자 ID 확인
#     user_id = session.get("user_id")
#     guest_id = session.get("guest_id")
#     user_or_guest_id = user_id or guest_id

#     # ✅ 비회원이면 히스토리 개수 검사 (팝업 조건)
#     if guest_id:
#         count = HistoryDAO.count_by_user_id(guest_id)
#         if count >= 10:
#             return jsonify({"popup": True}), 200   
        
#     # 히스토리 저장 (ID가 있을 때만)
#     if user_or_guest_id:                                          # [ADDED] None 보호
#         HistoryDAO.save_history(user_or_guest_id, url, result.get("label", ""))
#                 # [CHANGED] 상태코드 명시

#     # ✅ 결과 반환
#     # return jsonify({
#     #     "message": "분석 완료된 URL입니다.",
#     #     "url": url,
#     #     "result": result["label"],
#     #     "domain": result["domain"] or "-",
#     #     "created": str(result["created_date"]) if result["created_date"] else "-",
#     #     "expiry": str(result["expiry_date"]) if result["expiry_date"] else "-",
#     #     "date": datetime.datetime.now().strftime("%Y-%m-%d %H:%M"),
#     #     "source": "analyzed"
#     # })
#     return jsonify({
#         "message": "분석 완료된 URL입니다.",
#         "url": url,
#         "result": result.get("label", "CAUTION"),                  # [CHANGED] 기본값 보호
#         "domain": (result.get("domain") or urlparse(url).hostname or "-"),  # [CHANGED]
#         "created": (str(result.get("created_date")) if result.get("created_date") else "-"),
#         "expiry": (str(result.get("expiry_date")) if result.get("expiry_date") else "-"),
#         "date": datetime.datetime.now().strftime("%Y-%m-%d %H:%M"),
#         "source": "analyzed"
#     }), 200      


from flask import Blueprint, request, jsonify, session, current_app
from models.url_analysis_dao import UrlAnalysisDAO
from models.history_dao import HistoryDAO
from models.urlonly_dao import UrlOnlyDAO
from urllib.parse import urlparse            # ★ 추가
import datetime
import traceback

analyze_bp = Blueprint("analyze", __name__, url_prefix="/analyze")

@analyze_bp.route("", methods=["POST"])      # /analyze
@analyze_bp.route("/", methods=["POST"])     # /analyze/
def analyze():
    try:
        data = request.get_json(silent=True) or {}         # 안전 파싱
        current_app.logger.info(f"/analyze payload={data}") # 서버 콘솔에 찍힘

        url = data.get("url")                              # ★ request.json 대신 data 사용
        if not url:
            return jsonify({"error": "URL 데이터가 없습니다"}), 400

        # URL 등록 여부
        if not UrlOnlyDAO.exists(url):
            # 404 대신 Unity가 색 바꿀 수 있게 200 + 기본 라벨로 응답 (원하면 404로 바꿔도 됨)
            return jsonify({"message": "등록 안됨", "url": url, "result": "CAUTION"}), 200

        # 분석 결과 조회
        result = UrlAnalysisDAO.find_by_url(url)
        if result is None:
            return jsonify({"message": "분석 없음", "url": url, "result": "CAUTION"}), 200

        # 히스토리 저장 (있을 때만)
        user_or_guest_id = session.get("user_id") or session.get("guest_id")
        if user_or_guest_id:
            HistoryDAO.save_history(user_or_guest_id, url, result.get("label", "CAUTION"))

        # 최종 응답 (Unity는 result 문자열만 있어도 색 변경)
        # resp = {
        #     "message": "분석 완료된 URL입니다.",
        #     "url": url,
        #     "result": result.get("label", "CAUTION"),
        #     "domain": (result.get("domain") or urlparse(url).hostname or "-"),
        #     "created": str(result.get("created_date") or "-"),
        #     "expiry": str(result.get("expiry_date") or "-"),
        #     "date": datetime.datetime.now().strftime("%Y-%m-%d %H:%M"),
        #     "source": "analyzed"
        # }
        # return jsonify(resp), 200
                # 최종 응답 (Unity는 result 문자열만 있어도 색 변경)
        resp = {
            "message": "분석 완료된 URL입니다.",
            "url": url,
            "result": result.get("label", "CAUTION"),
            "domain": (result.get("domain") or urlparse(url).hostname or "-"),
            "created": str(result.get("created_date") or "-"),
            "expiry": str(result.get("expiry_date") or "-"),
            "date": datetime.datetime.now().strftime("%Y-%m-%d %H:%M"),
            "source": "analyzed"
        }
        return jsonify(resp), 200


    except Exception:
        # 예외가 나도 Unity가 로딩에 갇히지 않게 200으로 짧게 돌려줌 + 서버 로그 남김
        current_app.logger.exception("analyze error")
        return jsonify({"message": "server error", "result": "CAUTION"}), 200
