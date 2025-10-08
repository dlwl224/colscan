# routes/scan.py
#로그만 저장
from flask import Blueprint, request, jsonify
from Server.models.scan_dao import ScanDAO

scan_bp = Blueprint("scan", __name__)

@scan_bp.route("/log", methods=["POST"])
def log_scan():
    data = request.get_json(silent=True) or {}
    qr_code = data.get("qr_code")
    url = data.get("url")
    if not qr_code or not url:
        return jsonify({"error": "qr_code와 url이 필요합니다."}), 400
    scan_id = ScanDAO.save_scan(qr_code, url)
    return jsonify({"message": "logged", "scan_id": scan_id}), 201

@scan_bp.route("/all", methods=["GET"])
def list_scans():
    return jsonify(ScanDAO.get_all_scans()), 200
