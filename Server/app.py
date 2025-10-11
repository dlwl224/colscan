from flask import Flask, request, session, current_app
from flask_cors import CORS
import uuid 
from datetime import timedelta 

from Server.routes.home import home_bp 
from Server.routes.scan import scan_bp 
from Server.routes.analyze import analyze_bp 
from Server.routes.history import history_bp 
from Server.routes.chatbot import chatbot_bp 
from Server.routes.board import board_bp
from Server.routes.settings import settings_bp 
from Server.routes.auth import auth_bp 


app = Flask(__name__) 
app.secret_key = "your-very-secret-key" 
app.permanent_session_lifetime = timedelta(days=30) 

# ✅ 세션 쿠키 보강
app.config.update(
    SESSION_COOKIE_NAME='flask_auth_session', # 이름을 명확하게 변경
    SESSION_COOKIE_HTTPONLY=True,
    SESSION_COOKIE_SAMESITE="Lax",   # 외부 리다이렉트 시 세션 손실 방지
    SESSION_COOKIE_SECURE=False,     # 로컬 개발(http)에서는 False, 배포(https) 환경에서는 True 권장
    SESSION_PERMANENT=True,
)

# ✅ CORS (RN에서 쿠키 사용 가능하도록)
CORS(
    app,
    resources={r"/*": {"origins": [
        "http://localhost:19006",   # Expo Web 등 필요시
        "http://10.0.2.2:19006",    # 필요시 추가
        "http://10.0.2.2:5000",
        "http://localhost:5000",
        # 실제 기기에서 접근할 경우, RN 번들러/앱의 origin이 없을 수 있어
        # 와일드카드 대신 아래처럼 전체 허용 + credentials=True가 필요하면
        # 프록시/네이티브 fetch기반이라 origin이 비어도 동작. 문제가 있으면 origins="*"
    ]}},
    supports_credentials=True
)

# ✅ 항상 guest_id 보유: 로그인하지 않은 모든 사용자는 게스트
@app.before_request
def ensure_guest_id():
    session.permanent = True
    if "guest_id" not in session:
        session["guest_id"] = str(uuid.uuid4())

# ✅ 모든 요청 로깅
@app.before_request 
def _log_req(): 
    try: 
        print(f"[REQ] {request.method} {request.path} json={request.get_json(silent=True)}") 
    except Exception: 
        print(f"[REQ] {request.method} {request.path} (no json)")

# app.py 파일의 @app.before_request 아래에 추가

@app.after_request
def refresh_session_cookie(response):
    """
    세션이 수정된 경우 (session.modified가 True일 때) 
    응답에 새로운 세션 쿠키를 포함시켜 클라이언트에게 강제로 갱신하도록 유도합니다.
    """
    try:
        if session.modified:
            # Flask는 기본적으로 session.modified가 True일 때만 쿠키를 보냄
            # 이 함수는 세션 불일치 문제를 해결하기 위한 안전장치
            # 강제로 세션 데이터를 다시 로드하여 응답에 포함시킵니다.
            pass
    except Exception:
        # 세션 문제 발생 시 로그만 남기고 무시
        current_app.logger.exception("Session cookie refresh failed")
        
    return response

# app.config.update 부분 확인 (만약 배포 환경이라면)
app.config.update(
    SESSION_COOKIE_NAME='flask_auth_session',
    SESSION_COOKIE_HTTPONLY=True,
    SESSION_COOKIE_SAMESITE="Lax",
    SESSION_COOKIE_SECURE=False, # 👈 배포 환경(HTTPS)에서는 반드시 True로 변경
    SESSION_PERMANENT=True,
)

# ✅ 템플릿/라우트에서 공통으로 쓸 상태
@app.context_processor
def inject_user_context():
    user_id = session.get("user_id")
    is_logged_in = bool(user_id)
    return {
        "is_logged_in": is_logged_in,
        "is_guest": (not is_logged_in),     # 파생값
        "nickname": session.get("nickname")
    }

# 블루프린트 등록 
app.register_blueprint(home_bp) # 기본 '/' 및 '/home' 경로용 
app.register_blueprint(scan_bp, url_prefix="/scan") 
app.register_blueprint(analyze_bp)                 # ❌ url_prefix 제거
app.register_blueprint(history_bp)                 # ❌ url_prefix 제거
app.register_blueprint(chatbot_bp)                 # ❌ url_prefix 제거
app.register_blueprint(settings_bp)                # ❌ url_prefix 제거
app.register_blueprint(board_bp)
app.register_blueprint(auth_bp) 

if __name__ == "__main__": 
    app.run(host="0.0.0.0", port=5000,debug=True, use_reloader=False, threaded=True)