# routes/home.py
from flask import Blueprint, render_template, request, session, jsonify
from Server.models.history_dao import HistoryDAO

home_bp = Blueprint("home", __name__)

@home_bp.route("/")
@home_bp.route("/home")
def home():
    if request.args.get("format") == "json":
        user_id = session.get("user_id")
        is_logged_in = bool(user_id)

        today_cnt, yday_cnt = (0, 0)
        if is_logged_in:
            today_cnt, yday_cnt = HistoryDAO.get_today_yesterday_counts(user_id)

        return jsonify({
            "is_logged_in": is_logged_in,
            "is_guest": (not is_logged_in),
            "nickname": session.get("nickname") or "",
            "today_count": today_cnt,
            "yesterday_count": yday_cnt,
        })

    return render_template("home.html")
