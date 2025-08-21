# routes/auth.py
from flask import Blueprint, render_template, request, redirect, url_for, session, jsonify
from models.user_dao import UserDAO
from werkzeug.security import generate_password_hash, check_password_hash
from models.history_dao import HistoryDAO
from urllib.parse import urlparse, urljoin   # ← (추가) 안전한 URL 체크용

auth_bp = Blueprint("auth", __name__, url_prefix="/auth")

#✅ URL 리다이렉트 보호
# (추가) 내부 URL만 허용하는 간단한 안전 체크
from urllib.parse import urlparse, urljoin

def _is_safe_url(target: str) -> bool:
    if not target:
        return False
    base = urlparse(request.host_url)
    test = urlparse(urljoin(request.host_url, target))
    return test.scheme in ("http", "https") and base.netloc == test.netloc

@auth_bp.route("/login", methods=["GET"])
def login_page():
    return render_template("auth/login.html")

# @auth_bp.route("/loginProc", methods=["POST"])
# def login_proc():
#     email = request.form.get("email")
#     if user and check_password_hash(user["password"], password):
#         guest_id = session.get("guest_id")  # ⬅️ 로그인 전 guest_id 백업
#         session.clear()                    # ⬅️ 세션 초기화

#         session["user_id"] = user["id"]
#         session["nickname"] = user["nickname"]

#         # ✅ guest 기록을 user 기록으로 마이그레이션
#         if guest_id:
#             HistoryDAO.migrate_guest_to_user(guest_id, user["id"])

#         return redirect(request.form.get("redirectTo", "/home"))
#     else:
#         return redirect(url_for("auth.login_page") + "?error=true")

# @auth_bp.route("/loginProc", methods=["POST"])
# def login_proc():
#     email = request.form.get("email")
#     password = request.form.get("password")

#     user = UserDAO.find_by_email(email)
#     if user and check_password_hash(user["password"], password):
#         guest_id = session.get("guest_id")
#         session.clear()  # ✅ 세션 초기화

#         session["user_id"] = user["id"]
#         session["nickname"] = user["nickname"]
#         session["is_guest"] = user["is_guest"]  # ✅ 새 로그인 시 정확히 반영

#         # ✅ guest 기록 이관
#         if guest_id:
#             HistoryDAO.migrate_guest_to_user(guest_id, user["id"])

#         return redirect(request.form.get("redirectTo", "/home"))
#     else:
#         return redirect(url_for("auth.login_page") + "?error=true")
@auth_bp.route("/loginProc", methods=["POST"])
def login_proc():
    # ✅ 1) 입력값
    email = request.form.get("email")
    password = request.form.get("password")

    # ✅ 2) 로그인 전 게스트 ID 백업(이관용)
    prev_guest_id = session.get("guest_id")

    # ✅ 3) 사용자 조회/검증
    user = UserDAO.find_by_email(email)
    if user and check_password_hash(user["password"], password):
        # ✅ 4) 세션 초기화 (이전에 있던 guest_id 포함 전부 삭제)
        session.clear()

        # ✅ 5) 회원 세션 세팅
        session["user_id"] = user["id"]
        session["nickname"] = user["nickname"]
        session["is_guest"] = False   # ← 회원 로그인 확정(게스트 아님)

        # ✅ 6) 게스트 기록 이관 (게스트로 쌓인 히스토리를 회원으로 옮김)
        if prev_guest_id:
            try:
                HistoryDAO.migrate_guest_to_user(prev_guest_id, user["id"])
            except Exception as e:
                # 이관 실패해도 로그인은 성공시키고 서버 로그만 남김
                print(f"[WARN] migrate guest -> user fail: guest={prev_guest_id}, user={user['id']}, err={e}")

        # ✅ 7) 안전한 리다이렉트: redirectTo가 비었거나 외부면 기본 경로로 폴백
        redirect_to = request.form.get("redirectTo", "")
        if _is_safe_url(redirect_to):
            return redirect(redirect_to, code=303)   # PRG 패턴
        return redirect("/settings", code=303)       # 기본 이동(원하면 "/home"으로 교체)

    # ❌ 로그인 실패 시
    return redirect(url_for("auth.login_page") + "?error=true", code=303)

@auth_bp.route("/logout")
def logout():
    session.clear()
    return redirect("/auth/login")


@auth_bp.route("/register", methods=["GET"])
def register_page():
    return render_template("auth/register.html")
#     return redirect("/auth/login")

@auth_bp.route("/registerProc", methods=["POST"])
def register_proc():
    from datetime import datetime
    import re

    data = request.form
    password = data.get("password")

    # ✅ 비밀번호 유효성 검사: 8자 이상, 대문자, 숫자, 특수문자(!#%^*) 포함
    pw_pattern = r"^(?=.*[A-Z])(?=.*\d)(?=.*[!#%\^*])[A-Za-z\d!#%\^*]{8,}$"
    if not re.match(pw_pattern, password):
        return redirect(url_for("auth.register_page") + "?error=weak_password")

    # ✅ 필수 입력값 검사
    required_fields = ["email", "password", "nickname", "birthDate", "gender"]
    for field in required_fields:
        if not data.get(field):
            return redirect(url_for("auth.register_page") + "?error=missing")

    hashed_pw = generate_password_hash(password)
    birth_date = datetime.strptime(data["birthDate"], "%Y-%m-%d")

    UserDAO.create_user(
        email=data["email"],
        password=hashed_pw,
        nickname=data["nickname"],
        birth_date=birth_date,
        gender=data["gender"]
    )
    return redirect("/auth/login")

@auth_bp.route("/check-email")
def check_email():
    email = request.args.get("email")
    user = UserDAO.find_by_email(email)
    return jsonify({"exists": user is not None})


@auth_bp.route("/reset-password", methods=["GET", "POST"])
def reset_password():
    if request.method == "GET":
        return render_template("auth/reset-password.html")

    data = request.get_json()
    email = data.get("email")
    nickname = data.get("nickname")
    password = data.get("password")

    user = UserDAO.find_by_email(email)
    if user and user["nickname"] == nickname:
        conn = get_connection()
        try:
            with conn.cursor() as cursor:
                sql = "UPDATE user SET password = %s WHERE email = %s"
                hashed_pw = generate_password_hash(password)
                cursor.execute(sql, (hashed_pw, email))
                conn.commit()
            return jsonify({"success": True})
        finally:
            conn.close()
    else:
        return jsonify({"success": False, "error": "닉네임이 일치하지 않거나 존재하지 않는 사용자입니다."})

# @auth_bp.route("/guest-login")
# def guest_login():
#     import uuid
#     guest_id = str(uuid.uuid4())
#     email = f"guest_{guest_id[:8]}@guest.com"
#     nickname = f"게스트{guest_id[:4]}"

#     # ✅ 이미 생성된 게스트인지 확인 (중복 방지)
#     user = UserDAO.find_by_email(email)
#     if not user:
#         from werkzeug.security import generate_password_hash
#         password = generate_password_hash("guest")  # 더미 비밀번호
#         UserDAO.create_user(
#             email=email,
#             password=password,
#             nickname=nickname,
#             birth_date="2000-01-01",  # 더미값
#             gender="N",               # 기본값
#             is_guest=True            # 게스트 사용자로 표시
#         )

#     # ✅ 로그인 처리
#     user = UserDAO.find_by_email(email)
#     session["user_id"] = user["id"]
#     session["nickname"] = user["nickname"]

#     return redirect("/home")

@auth_bp.route("/guest-login")
def guest_login():
    import uuid

    # ✅ 세션에 guest_id가 있다면 재사용
    guest_id = session.get("guest_id")
    if guest_id:
        email = f"guest_{guest_id[:8]}@guest.com"
    else:
        # 없으면 새로 생성
        guest_id = str(uuid.uuid4())
        session["guest_id"] = guest_id
        email = f"guest_{guest_id[:8]}@guest.com"

    nickname = f"게스트{guest_id[:4]}"

    # ✅ 이미 생성된 유저가 없으면 생성
    user = UserDAO.find_by_email(email)
    if not user:
        from werkzeug.security import generate_password_hash
        password = generate_password_hash("guest")  # 더미 비밀번호
        UserDAO.create_user(
            email=email,
            password=password,
            nickname=nickname,
            birth_date="2000-01-01",
            gender="N",
            is_guest=True
        )

    # ✅ 로그인 처리
    user = UserDAO.find_by_email(email)
    session["user_id"] = user["id"]
    session["nickname"] = user["nickname"]
    session["is_guest"] = user["is_guest"]  # ✅ is_guest도 세션에 저장

    return redirect("/home")

