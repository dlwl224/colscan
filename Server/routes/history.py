# from flask import Blueprint, render_template, session
# from models.history_dao import HistoryDAO

# history_bp = Blueprint("history", __name__)

# @history_bp.route("/", methods=["GET"])
# def history():
#     user_id = session.get("user_id")
#     is_logged_in = user_id is not None

#     if is_logged_in:
#         scans = HistoryDAO.get_user_history(user_id)
#     else:
#         scans = HistoryDAO.get_recent_history(limit=10)  # ❗ 따로 구현 필요

#     return render_template("history.html", scans=scans, is_logged_in=is_logged_in)

from flask import Blueprint, render_template, session
from models.history_dao import HistoryDAO

history_bp = Blueprint("history", __name__)

@history_bp.route("/", methods=["GET"])
def history():
    user_id = session.get("user_id")
    guest_id = session.get("guest_id")  # 👈 비로그인 사용자용 UUID
    is_logged_in = user_id is not None

    if is_logged_in:
        scans = HistoryDAO.get_user_history(user_id)
    else:
        scans = HistoryDAO.get_guest_history(guest_id, limit=10)  # ✅ 사용자별 기록으로 수정됨

    return render_template("history.html", scans=scans, is_logged_in=is_logged_in)
