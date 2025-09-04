# from flask import Blueprint, render_template, session
# from Server.models.history_dao import HistoryDAO

# history_bp = Blueprint("history", __name__)

# @history_bp.route("/", methods=["GET"])
# def history():
#     user_id = session.get("user_id")
#     guest_id = session.get("guest_id")  # 👈 비로그인 사용자용 UUID
#     is_logged_in = user_id is not None

#     if is_logged_in:
#         scans = HistoryDAO.get_user_history(user_id)
#     else:
#         scans = HistoryDAO.get_guest_history(guest_id, limit=10)  # ✅ 사용자별 기록으로 수정됨

#     return render_template("history.html", scans=scans, is_logged_in=is_logged_in)


from flask import Blueprint, render_template, session, request
from Server.models.history_dao import HistoryDAO

history_bp = Blueprint("history", __name__, url_prefix="/history")

@history_bp.route("/", methods=["GET"])
def history():
    user_id = session.get("user_id")
    guest_id = session.get("guest_id")
    is_logged_in = user_id is not None

    # ?filter=all|legit|malicious
    filt = request.args.get("filter")
    if not filt:
        # 세션 기본값(설정) 사용
        filt = (session.get("app_settings") or {}).get("history", {}).get("default_filter", "all")

    if is_logged_in:
        base = HistoryDAO.get_user_history(user_id)
    else:
        base = HistoryDAO.get_guest_history(guest_id, limit=10)

    # 필터링은 DAO단/쿼리로 하는 게 베스트. 여기선 예시로 파이썬에서 필터:
    if filt == "legit":
        scans = [x for x in base if (x.get("label") or "").upper() in ("LEGITIMATE", "SAFE", "정상")]
    elif filt == "malicious":
        scans = [x for x in base if (x.get("label") or "").upper() in ("MALICIOUS", "DANGER", "악성")]
    else:
        scans = base

    return render_template("history.html", scans=scans, is_logged_in=is_logged_in, current_filter=filt)
