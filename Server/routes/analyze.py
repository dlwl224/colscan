from flask import Blueprint, request, jsonify, session, current_app
from Server.models.history_dao import HistoryDAO
from Server.models.urlbert_dao import UrlBertDAO
from urllib.parse import urlparse
import datetime
import traceback

analyze_bp = Blueprint("analyze", __name__, url_prefix="/analyze")

@analyze_bp.route("", methods=["POST"])      # /analyze
@analyze_bp.route("/", methods=["POST"])     # /analyze/
def analyze():
    try:
        data = request.get_json(silent=True) or {}         # 안전 파싱
        current_app.logger.info(f"/analyze payload={data}") # 서버 콘솔에 찍힘

        url = (data.get("url") or "").strip()                              # ★ request.json 대신 data 사용
        if not url:
            return jsonify({"error": "URL 데이터가 없습니다"}), 400

        # URL 등록 여부
        if not UrlBertDAO.exists(url):
            # 404 대신 Unity가 색 바꿀 수 있게 200 + 기본 라벨로 응답 (원하면 404로 바꿔도 됨)
            return jsonify({"message": "등록 안됨", "url": url, "result": "CAUTION"}), 200

        # 분석 결과 조회
        result = UrlBertDAO.find_by_url(url)
        if result is None:
            return jsonify({"message": "분석 없음", "url": url, "result": "CAUTION"}), 200

        # 히스토리 저장 (있을 때만)
        user_or_guest_id = session.get("user_id") or session.get("guest_id")
        if user_or_guest_id:
            try:
                HistoryDAO.save_history(user_or_guest_id, url, result.get("label", "CAUTION"))
            except Exception:
                current_app.logger.exception("history save failed")  # 로그만 남기고 계속 진행

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