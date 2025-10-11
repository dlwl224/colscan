# routes/auth.py
from flask import Blueprint, render_template, request, redirect, url_for, session, jsonify
from Server.models.user_dao import UserDAO
from Server.models.history_dao import HistoryDAO
from werkzeug.security import generate_password_hash, check_password_hash
from urllib.parse import urlparse, urljoin
import re
from datetime import datetime, date 

try:
    from pymysql.err import IntegrityError
except ImportError:
    # 사용하는 DB 라이브러리가 다를 경우를 대비한 안전 장치입니다.
    class IntegrityError(Exception):
        pass

auth_bp = Blueprint("auth", __name__, url_prefix="/auth")

def _is_safe_url(target: str) -> bool:
    if not target:
        return False
    base = urlparse(request.host_url)
    test = urlparse(urljoin(request.host_url, target))
    return test.scheme in ("http", "https") and base.netloc == test.netloc

@auth_bp.route("/login", methods=["GET"])
def login_page():
    return render_template("auth/login.html")

@auth_bp.route("/loginProc", methods=["POST"])
def login_proc():
    email = request.form.get("email", "")
    password = request.form.get("password", "")
    redirect_to = request.form.get("redirectTo", "")

    user = UserDAO.find_by_email(email)
    if user and check_password_hash(user["password"], password):
        prev_guest_id = session.get("guest_id")  # 로그인 전 게스트 식별자만 보존
        # 🔐 세션 초기화(쿠키는 유지되지만 서버측 세션키 reset)
        session.clear()
        # 로그인 세션 세팅
        session["user_id"]  = user["id"]
        session["nickname"] = user["nickname"]

        # 게스트 히스토리 → 회원 이관
        if prev_guest_id:
            try:
                HistoryDAO.migrate_guest_to_user(prev_guest_id, user["id"])
            except Exception as e:
                print(f"[WARN] migrate guest->user fail: guest={prev_guest_id}, user={user['id']}, err={e}")

        #return redirect(redirect_to if _is_safe_url(redirect_to) else "/settings", code=303)
        return jsonify({"success": True}), 200 # 성공

    #return redirect(url_for("auth.login_page") + "?error=true", code=303)
    return jsonify({"success": False, "error": "로그인 정보가 일치하지 않습니다."}), 401

@auth_bp.route("/logout")
def logout():
    # # 회원 세션만 제거하고 즉시 '새로운 게스트' 세션으로 전환
    # session.clear()
    # from uuid import uuid4
    # session["guest_id"] = str(uuid4())
    # return redirect("/auth/login")


    # 🌟 [수정] 회원 정보만 제거하고, 게스트 정보는 before_request에 의해 유지되도록 합니다. 
    # 이렇게 하면 게스트 세션은 유지됩니다.
    if "user_id" in session:
        session.pop("user_id")
    if "nickname" in session:
        session.pop("nickname")
    # session.clear() 대신 pop을 사용하여 guest_id가 유지되거나 새로 설정되도록 유도합니다.
    return redirect("/auth/login")

@auth_bp.route("/register", methods=["GET"])
def register_page():
    return render_template("auth/register.html")

@auth_bp.route("/registerProc", methods=["POST"])
def register_proc():

    data = request.form
    password = data.get("password")

    pw_pattern = r"^(?=.*[A-Z])(?=.*\d)(?=.*[!#%\^*])[A-Za-z\d!#%\^*]{8,}$"
    if not re.match(pw_pattern, password):
        return redirect(url_for("auth.register_page") + "?error=weak_password")

    required_fields = ["email", "password", "nickname", "birthDate", "gender"]
    for field in required_fields:
        if not data.get(field):
            return redirect(url_for("auth.register_page") + "?error=missing")

    hashed_pw = generate_password_hash(password)
    birth_date = datetime.strptime(data["birthDate"], "%Y-%m-%d")

    # UserDAO.create_user(
    #     email=data["email"],
    #     password=hashed_pw,
    #     nickname=data["nickname"],
    #     birth_date=birth_date,
    #     gender=data["gender"]
    # )
    # return redirect("/auth/login")
    try:
        UserDAO.create_user(
            email=data["email"],
            password=hashed_pw,
            nickname=data["nickname"],
            birth_date=birth_date,
            gender=data["gender"]
        )
        return redirect("/auth/login")
    except IntegrityError as e:
        # 💡 (1062, "Duplicate entry ...") 에러는 여기서 잡음
        if "Duplicate entry" in str(e) and "email" in str(e):
            return jsonify({
                "success": False,
                "error": "이미 사용 중인 이메일입니다."
            }), 409 # Conflict (충돌) 에러 코드 사용
        # 다른 IntegrityError(예: UNIQUE key 위반 등)는 일반적인 오류로 처리
        return jsonify({
            "success": False,
            "error": "데이터베이스 오류가 발생했습니다."
        }), 500
    except Exception as e:
        # 기타 다른 오류
        return jsonify({
            "success": False,
            "error": f"서버 오류가 발생했습니다: {e}"
        }), 500

@auth_bp.route("/check-email")
def check_email():
    email = request.args.get("email")
    user = UserDAO.find_by_email(email)
    return jsonify({"exists": user is not None})

# ✅ 더 이상 '비회원으로 로그인'은 필요치 않음 — 하위호환으로 유지만 하고 홈으로 보내기
@auth_bp.route("/guest-login")
def guest_login():
    # 모든 비로그인 사용자는 이미 게스트이므로 별도 처리 불필요
    return redirect("/home")

@auth_bp.route("/reset-password", methods=["POST"])
def reset_password():
    # 클라이언트(ResetPW.js)에서 JSON 형태로 데이터를 보냄
    data = request.json
    
    # 1. 필수 필드 추출 및 검증
    email = data.get("email")
    nickname = data.get("nickname")
    new_password = data.get("password")

    if not all([email, nickname, new_password]):
        return jsonify({"success": False, "error": "이메일, 닉네임, 새 비밀번호를 모두 입력해주세요."}), 400

    # 2. 사용자 인증 (이메일 및 닉네임 일치 확인)
    # UserDAO.find_by_email_and_nickname 메서드 (UserDAO에 추가됨) 사용
    user = UserDAO.find_by_email_and_nickname(email.strip(), nickname.strip())
    
    if not user:
        return jsonify({"success": False, "error": "사용자 정보가 일치하지 않습니다. 이메일과 닉네임을 확인해주세요."}), 404

    # 3. 새 비밀번호 유효성 검사 (회원가입 규칙과 동일)
    # 최소 8자, 대문자, 숫자, 특수문자(!#%^*) 포함
    # pw_pattern = r"^(?=.*[A-Z])(?=.*\d)(?=.*[!#%\^*])[A-Za-z\d!#%\^*]{8,}$"
    # if not re.match(pw_pattern, new_password):
    #     return jsonify({
    #         "success": False, 
    #         "error": "새 비밀번호는 8자 이상이며, 대문자, 숫자, 특수문자(!#%^*)를 포함해야 합니다."
    #     }), 400

    # try:
    #     # 4. 비밀번호 재설정 및 저장
    #     hashed_pw = generate_password_hash(new_password)
        
    #     # UserDAO.update_password 메서드 (UserDAO에 추가됨) 사용
    #     UserDAO.update_password(user["id"], hashed_pw)

    #     # 1. ✅ 여기에 비밀번호 재설정 성공 로그를 추가합니다.
    #     print(f"[SUCCESS] Password reset for user: {email} (ID: {user['id']})") 
        
    #     # 5. 성공 응답
    #     return jsonify({"success": True}), 200

    # except Exception as e:
    #     # 데이터베이스 작업 중 발생할 수 있는 오류 처리
    #     print(f"[ERROR] Password reset failed for user_id={user['id']}: {e}")
    #     return jsonify({"success": False, "error": "서버 오류로 인해 비밀번호 재설정에 실패했습니다."}), 500

    # 기존 비밀번호와 동일한지 체크
    hashed_pw_record = UserDAO.find_hashed_password_by_id(user["id"])
    current_hashed_pw = hashed_pw_record.get("password")
    if current_hashed_pw and check_password_hash(current_hashed_pw, new_password):
        return jsonify({"success": False, "error": "기존 비밀번호와 동일합니다. 다른 비밀번호를 사용해주세요."}), 400

    # 비밀번호 규칙 체크
    pw_pattern = r"^(?=.*[A-Z])(?=.*\d)(?=.*[!#%\^*])[A-Za-z\d!#%\^*]{8,}$"
    if not re.match(pw_pattern, new_password):
        return jsonify({
            "success": False, 
            "error": "새 비밀번호는 8자 이상이며, 대문자, 숫자, 특수문자(!#%^*)를 포함해야 합니다."
        }), 400

    try:
        # 비밀번호 해시 후 저장
        hashed_pw = generate_password_hash(new_password)
        UserDAO.update_password(user["id"], hashed_pw)
        print(f"[SUCCESS] Password reset for user: {email} (ID: {user['id']})") 
        return jsonify({"success": True}), 200

    except Exception as e:
        print(f"[ERROR] Password reset failed for user_id={user['id']}: {e}")
        return jsonify({"success": False, "error": "서버 오류로 인해 비밀번호 재설정에 실패했습니다."}), 500

@auth_bp.route("/profile-details", methods=["GET"])
def profile_details():
    user_id = session.get("user_id")
    
    if not user_id:
        # 401 Unauthorized 대신 401 에러 코드와 메시지 반환
        return jsonify({
            "success": False, 
            "error": "로그인이 필요합니다."
        }), 401

    try:
        # UserDAO는 이미 find_user_profile_data를 가지고 있다고 가정
        user_info = UserDAO.find_user_profile_data(user_id)
        
        if not user_info:
            return jsonify({
                "success": False, 
                "error": "사용자 정보를 찾을 수 없습니다."
            }), 404
        
        birth_date_str = None
        birth_date_obj = user_info.get("birth_date")
        
        # datetime.datetime 또는 datetime.date 객체를 문자열로 변환
        if isinstance(birth_date_obj, (datetime, date)): 
            birth_date_str = birth_date_obj.strftime("%Y-%m-%d")

        # 성공 응답
        return jsonify({
            "success": True,
            "email": user_info.get("email"),
            "nickname": user_info.get("nickname"),
            "role": user_info.get("role", "USER"),
            "birth_date": birth_date_str,
            "gender": user_info.get("gender"),
        }), 200

    except Exception as e:
        print(f"[ERROR] Failed to fetch profile details for user {user_id}: {e}")
        return jsonify({
            "success": False, 
            "error": "서버 오류로 인해 프로필 정보를 불러오지 못했습니다."
        }), 500
    
@auth_bp.route("/me")
def me():
    user_id = session.get("user_id")
    is_logged_in = bool(user_id)

    # --- 여기부터 수정 ---
    nickname = None
    effective_user_id = None # user_id 또는 guest_id를 담을 변수
    role = None # 로그인된 회원일 경우에만 DB role(USER/ADMIN)이 들어갑니다.
    
    if is_logged_in:
        # 1. 로그인된 회원인 경우:
        nickname = session.get("nickname")
        effective_user_id = user_id
        
        # 💡 [수정] 로그인된 회원일 때만 DB에서 role을 조회합니다.
        user_role = UserDAO.find_user_role(user_id) 
        if user_role:
             role = user_role # 'USER' 또는 'ADMIN'
        else:
             # DB 조회 오류 시 기본값으로 'USER' 설정 (안전성 확보)
             role = 'USER' 
             
    else:
        # 2. 비로그인 상태 (게스트)인 경우:
        nickname = "게스트"
        # 게스트 ID를 유효 ID로 사용 (신고 내역 필터링 등에 사용 가능)
        effective_user_id = session.get("guest_id") 
        # role은 None 또는 비어있는 상태로 유지
        role = None 

    return jsonify({
        # 💡 프론트엔드가 '회원 여부'를 판단하는 가장 중요한 플래그
        "is_logged_in": is_logged_in, 
        
        # 'is_guest'는 is_logged_in의 반대입니다.
        "is_guest": not is_logged_in, 
        
        "user_id": effective_user_id,
        "nickname": nickname,
        
        # 💡 [핵심] 로그인된 회원만 role 값을 가집니다. (USER/ADMIN)
        "role": role 
    })

@auth_bp.route("/update-nickname", methods=["POST"])
def update_nickname():
    print(f"[DEBUG] Received update-nickname request. Session user_id: {session.get('user_id')}") 
    user_id = session.get("user_id")
    if not user_id:
        return jsonify({"success": False, "error": "로그인이 필요합니다."}), 401

    data = request.get_json(silent=True)
    new_nickname = data.get("nickname")

    if not new_nickname or not new_nickname.strip():
        return jsonify({"success": False, "error": "닉네임을 입력해주세요."}), 400

    try:
        # 💡 [수정] 실제 DB 업데이트 함수 호출
        is_updated = UserDAO.update_nickname(user_id, new_nickname.strip())
        
        if is_updated:
            # DB 업데이트 성공 후 세션도 업데이트
            session["nickname"] = new_nickname.strip() 
            
            print(f"[SUCCESS] Nickname updated for user {user_id} to: {new_nickname.strip()}")
            return jsonify({"success": True}), 200
        else:
            # DB에 변경 사항이 없거나 (같은 닉네임) 업데이트 실패
            return jsonify({"success": False, "error": "닉네임 업데이트에 실패했거나 변경 사항이 없습니다."}), 400

    except Exception as e:
        print(f"[ERROR] Failed to update nickname for user {user_id}: {e}")
        return jsonify({"success": False, "error": "닉네임 업데이트 중 서버 오류 발생"}), 500
    
@auth_bp.route("/check-password-same", methods=["POST"])
def check_password_same():
    data = request.get_json(silent=True)
    email = data.get("email")
    nickname = data.get("nickname")
    new_password = data.get("password")

    # 이메일+닉네임로 사용자 조회
    user = UserDAO.find_by_email_and_nickname(email.strip(), nickname.strip())
    if not user:
        return jsonify({"success": False, "is_same": False}), 200

    hashed_pw_record = UserDAO.find_hashed_password_by_id(user["id"])
    current_hashed_pw = hashed_pw_record.get("password")
    
    is_same = False
    if current_hashed_pw:
        is_same = check_password_hash(current_hashed_pw, new_password)

    return jsonify({"success": True, "is_same": is_same}), 200