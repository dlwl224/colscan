# Server/routes/history.py
from flask import Blueprint, render_template, session, request
from Server.models.history_dao import HistoryDAO

history_bp = Blueprint("history", __name__, url_prefix="/history")

@history_bp.route("/", methods=["GET"])
def history():
    user_id  = session.get("user_id")
    guest_id = session.get("guest_id")
    is_guest = bool(session.get("is_guest", False))  # [추가]
    # [변경] '로그인 회원'은 is_guest가 False일 때만
    is_logged_in = (user_id is not None) and (not is_guest)

    # 필터
    filt = request.args.get("filter") or (session.get("app_settings") or {}).get("history", {}).get("default_filter", "all")

    scans, total, pages = [], None, None
    page, per_page = 1, 10
    q = None

    if is_logged_in:
        # --- 회원(정회원) 전용: 검색/페이지네이션 ---
        try:
            page = int(request.args.get("page", "1"))
        except ValueError:
            page = 1
        try:
            per_page = int(request.args.get("per_page", "10"))
        except ValueError:
            per_page = 10
        q = (request.args.get("q") or "").strip() or None

        scans, total = HistoryDAO.get_user_history_paginated(user_id, page=page, per_page=per_page, q=q)

        # 필터
        if filt == "legit":
            scans = [x for x in scans if (x.get("label") or "").upper() in ("LEGITIMATE", "SAFE", "정상")]
        elif filt == "malicious":
            scans = [x for x in scans if (x.get("label") or "").upper() in ("MALICIOUS", "DANGER", "악성")]

        pages = (total + per_page - 1) // per_page if total is not None else None

    else:
        # --- 비회원 모드(게스트 로그인 포함): 5개 고정 ---
        # [변경] effective_id: 게스트 로그인은 user_id, 순수 게스트는 guest_id
        effective_id = user_id if is_guest else guest_id
        base = HistoryDAO.get_guest_history(effective_id, limit=HistoryDAO.GUEST_LIMIT)

        if filt == "legit":
            scans = [x for x in base if (x.get("label") or "").upper() in ("LEGITIMATE", "SAFE", "정상")]
        elif filt == "malicious":
            scans = [x for x in base if (x.get("label") or "").upper() in ("MALICIOUS", "DANGER", "악성")]
        else:
            scans = base

    return render_template(
        "history.html",
        scans=scans,
        is_logged_in=is_logged_in,       # [변경] 정회원만 True
        current_filter=filt,
        page=page,
        per_page=per_page,
        q=(q or ""),
        total=total,
        pages=pages
    )
