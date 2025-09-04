# from flask import Blueprint, render_template

# chatbot_bp = Blueprint("chatbot", __name__)

# @chatbot_bp.route("/", methods=["GET"])
# def chatbot():
#     return render_template("chatbot.html")


# routes/chatbot.py
from flask import Blueprint, render_template, session

chatbot_bp = Blueprint("chatbot", __name__, url_prefix="/chatbot")

@chatbot_bp.route("/", methods=["GET"])
def chatbot():
    # 1) app_settings.chatbot.mode 우선
    # 2) 없으면 chatbot_mode
    # 3) 최종 기본 'normal'
    app_settings = session.get("app_settings") or {}
    mode = (
        (app_settings.get("chatbot") or {}).get("mode")
        or session.get("chatbot_mode")
        or "normal"
    )
    return render_template("chatbot.html", mode=mode)
