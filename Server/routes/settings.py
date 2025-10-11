# routes/settings.py
from flask import Blueprint, render_template, request, jsonify, session, redirect, url_for
from Server.models.history_dao import HistoryDAO

settings_bp = Blueprint("settings", __name__, url_prefix="/settings")

# ✅ 기본 설정 값
DEFAULT_SETTINGS = {
    "privacy": {
        "camera": True,
        "storage": True,
        "data_consent": True,      # 데이터 수집 동의(로그/분석)
    },
    "display": {
        "theme": "light",          # light | dark
        "font_scale": 100,         # 80~140 (%)
    },
    "language": "ko",              # ko | en
    "history": {
        "default_filter": "all"    # all | legit | malicious
    },
    "chatbot": {
        "mode": "normal"           # normal | pro(심화)
    }
}

def get_settings():
    s = session.get("app_settings") or {}
    # 얕은 병합(없으면 기본값 채우기)
    merged = {**DEFAULT_SETTINGS, **s}
    merged["privacy"] = {**DEFAULT_SETTINGS["privacy"], **merged.get("privacy", {})}
    merged["display"] = {**DEFAULT_SETTINGS["display"], **merged.get("display", {})}
    merged["history"] = {**DEFAULT_SETTINGS["history"], **merged.get("history", {})}
    merged["chatbot"] = {**DEFAULT_SETTINGS["chatbot"], **merged.get("chatbot", {})}
    return merged

@settings_bp.route("/", methods=["GET"])
def settings_page():
    return render_template("settings.html", settings=get_settings())

@settings_bp.route("/", methods=["POST"])
def update_settings():
    """
    프론트에서 JSON으로 오는 payload를 세션에 저장.
    {
      "privacy": {"camera":true, "storage":true, "data_consent":false},
      "display": {"theme":"dark","font_scale":110},
      "language": "en",
      "history": {"default_filter":"legit"},
      "chatbot": {"mode":"pro"}
    }
    """
    data = request.get_json(silent=True) or {}
    cur = get_settings()

    # 값 병합 + 최소 검증
    if "privacy" in data:
        for k in ["camera", "storage", "data_consent"]:
            if k in data["privacy"]:
                cur["privacy"][k] = bool(data["privacy"][k])

    if "display" in data:
        theme = data["display"].get("theme")
        if theme in ["light", "dark"]:
            cur["display"]["theme"] = theme
        try:
            fs = int(data["display"].get("font_scale", cur["display"]["font_scale"]))
            cur["display"]["font_scale"] = min(140, max(80, fs))
        except (TypeError, ValueError):
            pass

    if "language" in data:
        if data["language"] in ["ko", "en"]:
            cur["language"] = data["language"]

    if "history" in data:
        df = data["history"].get("default_filter")
        if df in ["all", "legit", "malicious"]:
            cur["history"]["default_filter"] = df

    if "chatbot" in data:
        mode = data["chatbot"].get("mode")
        if mode in ["normal", "pro"]:
            cur["chatbot"]["mode"] = mode

    # 세션 저장
    session["app_settings"] = cur

    # ✅ (선택) 챗봇 모드를 전역에서 쉽게 쓰고 싶다면 별도 키로도 저장
    session["chatbot_mode"] = cur["chatbot"]["mode"]

    return jsonify({"ok": True, "settings": cur}), 200

# JSON으로 현재 설정 반환 (RN 용)
@settings_bp.route("/json", methods=["GET"])
def settings_json():
    return jsonify({"ok": True, "settings": get_settings()}), 200

@settings_bp.route("/history/summary", methods=["GET"])
def get_history_summary_api():
    """RN 마이페이지에서 사용할 히스토리 요약 통계"""
    # 게스트 ID를 세션에서 가져오는 로직은 보통 auth 라우트에서 처리되지만, 
    # 여기서는 history_dao에서 사용하는 ID를 가져옵니다.
    user_id = session.get("user_id") or session.get("guest_id")
    if not user_id:
        # 로그인/게스트 ID가 없으면 0으로 반환
        return jsonify({"total": 0, "legit": 0, "malicious": 0}), 200

    summary = HistoryDAO.get_history_summary(user_id)
    return jsonify(summary), 200
