from flask import Blueprint, request, jsonify

classify_bp = Blueprint("classify", __name__)

@classify_bp.route("/", methods=["POST"])
def classify():
    url = request.json.get("url")
    if not url:
        return jsonify({"error": "URL이 없습니다."}), 400

    # 실제 분류 로직으로 교체 가능
    result = {"url": url, "label": "safe", "message": "정상 URL로 분류되었습니다."}
    return jsonify(result), 200
