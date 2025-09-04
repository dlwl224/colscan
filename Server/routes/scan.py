from flask import Blueprint, request, jsonify
import datetime
from Server.models.scan_dao import ScanDAO

scan_bp = Blueprint("scan", __name__)

@scan_bp.route("/", methods=["POST"])
def scan_qr():
    """QR 코드 데이터를 저장하는 API"""
    data = request.json
    qr_code = data.get("qr_code")
    url = data.get("url")

    if not qr_code or not url:
        return jsonify({"error": "QR 코드 데이터 또는 URL이 없습니다"}), 400

    scan_id = ScanDAO.save_scan(qr_code, url)
    return jsonify({"message": "QR 코드 데이터 저장 완료", "scan_id": scan_id}), 201

@scan_bp.route("/<int:scan_id>", methods=["GET"])
def get_scan(scan_id):
    """QR 코드 데이터를 ID로 검색"""
    scan_data = ScanDAO.get_scan(scan_id)
    if not scan_data:
        return jsonify({"error": "해당 ID의 데이터가 없습니다"}), 404
    return jsonify(scan_data), 200

@scan_bp.route("/all", methods=["GET"])
def get_all_scans():
    """저장된 모든 QR 코드 데이터를 반환"""
    scans = ScanDAO.get_all_scans()
    return jsonify(scans), 200

@scan_bp.route("/classify", methods=["POST"])
def classify_qr():
    data = request.json
    url = data.get("qr_code")

    if not url:
        return jsonify({"error": "QR 코드(URL)가 없습니다"}), 400

    all_logs = ScanDAO.get_all_scans()
    for entry in all_logs:
        if entry["url"] == url:
            is_malicious = "phishing" in url or "malicious" in url or "danger" in url
            result = "위험" if is_malicious else "안전"
            return jsonify({"result": result, "source": "database"}), 200

    # 👉 ML 모델 예측 연결 예시
    from predict_model import predict_url_safety
    result = predict_url_safety(url)  # 예: 안전, 위험 반환
    return jsonify({"result": result, "source": "ml_model"}), 200
