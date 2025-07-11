from flask import Blueprint, request, jsonify, session
from models.url_analysis_dao import UrlAnalysisDAO
from models.scan_dao import ScanDAO
from models.history_dao import HistoryDAO
from models.urlonly_dao import UrlOnlyDAO 
import datetime
import uuid

analyze_bp = Blueprint("analyze", __name__)

@analyze_bp.route("/", methods=["POST"])
def analyze():
    # if "user_id" not in session:
    #     session["user_id"] = f"anon_{uuid.uuid4().hex}"
    url = request.json.get("url")
    if not url:
        return jsonify({"error": "URL 데이터가 없습니다"}), 400

    if UrlOnlyDAO.exists(url):
        result = UrlAnalysisDAO.find_by_url(url)
        if result is not None:
            print("result['label'] =", result["label"]) 
            label_kor = {
                "LEGITIMATE": "정상",
                "CAUTION": "주의",
                "MALICIOUS": "악성"
            }   
    #         user_id = session.get("user_id")

    #         # ✅ 익명 사용자는 저장하지 않음
    #         if not user_id.startswith("anon_"):
    #             HistoryDAO.save_history(user_id, url, result["label"])
            
    #         return jsonify({
    #             "message": "분석 완료된 URL입니다.",
    #             "url": url,  # ⚠ result["url"] → result에 포함 안 되면 url 그대로 사용
    #             "result": result["label"],
    #             "domain": result["domain"] or "-",
    #             "created": str(result["created_date"]) if result["created_date"] else "-",
    #             "expiry": str(result["expiry_date"]) if result["expiry_date"] else "-",
    #             "date": datetime.datetime.now().strftime("%Y-%m-%d %H:%M"),
    #             "source": "analyzed"
    #         })
    #     else:
    #         return jsonify({"message": "분석 데이터가 존재하지 않습니다."}), 404
    # else:
    #     return jsonify({"message": "해당 URL은 아직 등록되지 않았습니다."}), 404
            
            # ✅ user_id 또는 guest_id 사용
            user_or_guest_id = session.get("user_id") or session.get("guest_id")
            HistoryDAO.save_history(user_or_guest_id, url, result["label"])
            
            return jsonify({
                "message": "분석 완료된 URL입니다.",
                "url": url,
                "result": result["label"],
                "domain": result["domain"] or "-",
                "created": str(result["created_date"]) if result["created_date"] else "-",
                "expiry": str(result["expiry_date"]) if result["expiry_date"] else "-",
                "date": datetime.datetime.now().strftime("%Y-%m-%d %H:%M"),
                "source": "analyzed"
            })
        else:
            return jsonify({"message": "분석 데이터가 존재하지 않습니다."}), 404
    else:
        return jsonify({"message": "해당 URL은 아직 등록되지 않았습니다."}), 404