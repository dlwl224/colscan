from flask import Blueprint, render_template, request, jsonify

settings_bp = Blueprint("settings", __name__)

@settings_bp.route("/", methods=["GET"])
def settings_page():
    return render_template("settings.html")

@settings_bp.route("/", methods=["POST"])
def update_settings():
    # 실제 설정 저장 로직 추가 가능
    settings_data = request.json
    return jsonify({"message": "설정이 저장되었습니다.", "data": settings_data}), 200
