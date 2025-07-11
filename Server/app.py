# # app.py
# from flask import Flask
# from routes.home import home_bp
# from routes.scan import scan_bp
# from routes.analyze import analyze_bp
# from routes.history import history_bp
# from routes.chatbot import chatbot_bp
# from routes.classify import classify_bp
# from routes.scan_list import scan_list_bp
# from routes.settings import settings_bp
# from routes.auth import auth_bp

# app = Flask(__name__)
# app.secret_key = "your-very-secret-key"

# # 블루프린트 등록
# app.register_blueprint(home_bp)  # 기본 '/' 및 '/home' 경로용
# app.register_blueprint(scan_bp, url_prefix="/scan")
# app.register_blueprint(analyze_bp, url_prefix="/analyze")
# app.register_blueprint(history_bp, url_prefix="/history")
# app.register_blueprint(chatbot_bp, url_prefix="/chatbot")
# app.register_blueprint(classify_bp, url_prefix="/classify")
# app.register_blueprint(scan_list_bp, url_prefix="/scan_list")
# app.register_blueprint(settings_bp, url_prefix="/settings")
# app.register_blueprint(auth_bp)

# if __name__ == "__main__":
#     app.run(debug=True, use_reloader=False, threaded=True)

from flask import Flask, session
import uuid
from datetime import timedelta

from routes.home import home_bp
from routes.scan import scan_bp
from routes.analyze import analyze_bp
from routes.history import history_bp
from routes.chatbot import chatbot_bp
from routes.classify import classify_bp
from routes.scan_list import scan_list_bp
from routes.settings import settings_bp
from routes.auth import auth_bp

app = Flask(__name__)
app.secret_key = "your-very-secret-key"
app.permanent_session_lifetime = timedelta(days=30)

# ✅ guest_id 세션 자동 생성 + 유지
@app.before_request
def assign_guest_id():
    session.permanent = True
    if "user_id" not in session and "guest_id" not in session:
        session["guest_id"] = str(uuid.uuid4())

# ✅ 로그인 상태를 모든 템플릿에 전달
@app.context_processor
def inject_user_status():
    return {
        "is_logged_in": "user_id" in session,
        "nickname": session.get("nickname")
    }


# 블루프린트 등록
app.register_blueprint(home_bp)  # 기본 '/' 및 '/home' 경로용
app.register_blueprint(scan_bp, url_prefix="/scan")
app.register_blueprint(analyze_bp, url_prefix="/analyze")
app.register_blueprint(history_bp, url_prefix="/history")
app.register_blueprint(chatbot_bp, url_prefix="/chatbot")
app.register_blueprint(classify_bp, url_prefix="/classify")
app.register_blueprint(scan_list_bp, url_prefix="/scan_list")
app.register_blueprint(settings_bp, url_prefix="/settings")
app.register_blueprint(auth_bp)

if __name__ == "__main__":
    app.run(debug=True, use_reloader=False, threaded=True)
