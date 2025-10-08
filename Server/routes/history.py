# Server/routes/history.py
from flask import Blueprint, render_template, session, request
from Server.models.history_dao import HistoryDAO

history_bp = Blueprint("history", __name__, url_prefix="/history")

@history_bp.route("/", methods=["GET"])
def history():
    user_id  = session.get("user_id")
    guest_id = session.get("guest_id")
    is_logged_in = bool(user_id)          # 파생
    is_guest     = not is_logged_in

    # 필터
    filt = request.args.get("filter") or (session.get("app_settings") or {}).get("history", {}).get("default_filter", "all")

    scans, total, pages = [], None, None
    page, per_page = 1, 10
    q = None

    if is_logged_in:
        # 회원: 페이징/검색
        try: page = int(request.args.get("page", "1"))
        except ValueError: page = 1
        try: per_page = int(request.args.get("per_page", "10"))
        except ValueError: per_page = 10
        q = (request.args.get("q") or "").strip() or None

        scans, total = HistoryDAO.get_user_history_paginated(user_id, page=page, per_page=per_page, q=q)

        if filt == "legit":
            scans = [x for x in scans if (x.get("label") or "").upper() in ("LEGITIMATE", "SAFE", "정상")]
        elif filt == "malicious":
            scans = [x for x in scans if (x.get("label") or "").upper() in ("MALICIOUS", "DANGER", "악성")]

        pages = (total + per_page - 1) // per_page if total is not None else None

    else:
        # 게스트(=비회원): 5개 고정
        base = HistoryDAO.get_guest_history(guest_id, limit=HistoryDAO.GUEST_LIMIT)
        if filt == "legit":
            scans = [x for x in base if (x.get("label") or "").upper() in ("LEGITIMATE", "SAFE", "정상")]
        elif filt == "malicious":
            scans = [x for x in base if (x.get("label") or "").upper() in ("MALICIOUS", "DANGER", "악성")]
        else:
            scans = base

    if request.args.get("format") == "json":
        return {
            "is_logged_in": is_logged_in,
            "current_filter": filt,
            "scans": [
                {
                    "id": i,
                    "url": it.get("url"),
                    "label": it.get("label"),
                    "analysis_date": it.get("analyzed_at").strftime("%Y-%m-%d %H:%M:%S") if it.get("analyzed_at") else "-"
                }
                for i, it in enumerate(scans)
            ]
        }, 200

    return render_template(
        "history.html",
        scans=scans,
        is_logged_in=is_logged_in,
        current_filter=filt,
        page=page,
        per_page=per_page,
        q=(q or ""),
        total=total,
        pages=pages
    )