# routes/chatbot.py
from flask import Blueprint, render_template, session, request, jsonify
from werkzeug.exceptions import BadRequest
import json
from datetime import datetime, timedelta, timezone
import os

# DB 연결 함수 import
from Server.DB_conn import get_connection_dict as get_db_conn

# FastAPI 대신 바로 챗봇 로직 호출
#   - 경로 문제 나면 아래 try/except 블록 그대로 두면 됨.
from bot.bot_main3 import get_chatbot_response, llm
'''
try:
    from bot.bot_main4 import get_chatbot_response
except Exception:
    # 프로젝트 루트/모듈 경로 보정 (WSL에서도 안전)
    import os, sys
    project_root = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
    project_root = os.path.abspath(os.path.join(project_root, ".."))
    if project_root not in sys.path:
        sys.path.insert(0, project_root)
    from bot.bot_main3 import get_chatbot_response
'''
chatbot_bp = Blueprint("chatbot", __name__, url_prefix="/chatbot")

SESSION_TIMEOUT_MINUTES = 30 

# 추가: 현재 로그인 사용자 id를 세션에서만 꺼내는 헬퍼
def _current_user_id():
    """
    세션 기반 로그인 사용자 ID를 'user_id' 키에서 직접 읽어옵니다.
    """
    return session.get("user_id")
    # user_id = session.get("user_id")
    # if user_id:
    #     # Flask 세션은 직렬화 가능(serializable)한 타입만 저장하므로
    #     # 문자열로 변환하여 반환하는 것이 안전합니다.
    #     return str(user_id)
    # return None

# 추가(2-1): Gemini API로 대화 내용을 요약하는 함수
def _summarize_with_gemini(messages: list) -> str:
    """Gemini API를 사용해 대화 내용을 한 줄 제목으로 요약합니다."""
    if not messages:
        return "새 대화"

    conversation_text = "\n".join([f"{msg.get('role', 'unknown')}: {msg.get('text', '')}" for msg in messages])
    prompt = f"""다음 대화 내용을 한국어로 짧은 제목으로 요약해줘:\n\n{conversation_text}\n\n제목: """

    try:
        response = llm.invoke(prompt)
        summary = response.content.strip().replace('"', '')
        first_user_message = next((msg['text'] for msg in messages if msg.get('role') == 'user'), "새 대화")
        return summary if summary else first_user_message[:40]
    except Exception as e:
        print(f"Error during Gemini summary: {e}")
        first_user_message = next((msg['text'] for msg in messages if msg.get('role') == 'user'), "새 대화")
        return first_user_message[:40]



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

# 프론트에서 여기로 POST → 바로 로컬 함수 호출
@chatbot_bp.route("/api", methods=["POST"])
def chatbot_api():
    payload = request.get_json(silent=True) or {}
    # 프론트는 message로 보냄 — 기존 서버는 query를 기대했으니 둘 다 허용
    q = (payload.get("query") or payload.get("message") or "").strip()
    if not q:
        raise BadRequest("query가 비어 있습니다.")
    mode = payload.get("mode") or "basic"
    meta = payload.get("meta") or {}

    # 로컬 챗봇 함수 호출
    # get_chatbot_response(q, mode, meta) 형태를 추천. 기존이 q만 받으면 그대로 사용
    data = get_chatbot_response(q) or {}
    reply = data.get("reply") or data.get("answer") or ""

    # 프론트가 기대하는 필드명 맞추기 (reply)
    # data가 {"answer": "..."} 형태면 reply로 복사
    out = {
        "reply": reply,
        "mode": data.get("mode") or mode,
        "sources": data.get("sources") or [],
    }
    return jsonify({
    "reply": reply,                          # 항상 reply 포함
    "answer": data.get("answer") or reply,   # (선택) 하위호환
    "mode": data.get("mode") or mode,
    "sources": data.get("sources") or [],
    }), 200

# 추가: 히스토리 저장/조회 API

@chatbot_bp.route("/history/save", methods=["POST"])
def save_history():
    payload  = request.get_json(silent=True) or {}
    # 변경: 프론트에서 온 user_id는 무시하고 세션에서만 판정
    user_id  = _current_user_id()
    messages = payload.get("messages") or [] 

    # messages 변수가 정의된 후, title과 preview를 계산합니다.
    title = _summarize_with_gemini(messages)
    preview = (messages[-1].get("text") or "").strip()[:80]
    messages_json = json.dumps(messages, ensure_ascii=False)

    # 로그인 안 됐으면 조용히 스킵(200)  ← 게스트 저장 금지
    if not user_id:
        return jsonify({"ok": True, "skipped": "GUEST"})

     # DB 로직 및 만료 시간 계산에 사용되는 현재 시간을 정의합니다.
    now = datetime.now(timezone.utc)

    ttl_days   = int(os.getenv("CHAT_HISTORY_TTL_DAYS", "30"))
    expires_at = now + timedelta(days=ttl_days)

    conn = get_db_conn()
    try:
        with conn.cursor() as cur:
             # 변경(2-2): 매번 새 기록을 만드는 대신, 30분 이내의 대화는 기존 기록에 덮어쓰는 로직으로 수정합니다.
            cur.execute(
                "SELECT id, created_at FROM chat_history WHERE user_id = %s ORDER BY created_at DESC LIMIT 1",
                (str(user_id),)
            )
            last_session = cur.fetchone()

            session_id_to_update = None
            if last_session:
                last_time = last_session['created_at'].replace(tzinfo=timezone.utc)
                # SESSION_TIMEOUT_MINUTES는 이제 전역에 정의되어 작동합니다.
                if (now - last_time) < timedelta(minutes=SESSION_TIMEOUT_MINUTES):
                    session_id_to_update = last_session['id']
            
            # if session_id_to_update:
            #     # 30분 내 대화가 있으면 UPDATE (기록 덮어쓰기)
            #     cur.execute(
            #         "UPDATE chat_history SET title=%s, preview=%s, messages=%s, created_at=%s WHERE id=%s",
            #         (title, preview, messages_json, now, session_id_to_update)
            #     )
            # else:
            #     # 새 대화는 INSERT (새 기록 생성)
            #     ttl_days = int(os.getenv("CHAT_HISTORY_TTL_DAYS", "1"))
            #     expires_at = now + timedelta(days=ttl_days)
            #     cur.execute(
            #         "INSERT INTO chat_history (user_id, title, preview, messages, created_at, expires_at) VALUES (%s, %s, %s, %s, %s, %s)",
            #         (str(user_id), title, preview, messages_json, now, expires_at)
            #     )

            if session_id_to_update:
                # 30분 내 대화가 있으면 UPDATE (기록 덮어쓰기)
                cur.execute(
                    "UPDATE chat_history SET title=%s, preview=%s, messages=%s, created_at=%s, expires_at=%s WHERE id=%s",
                    (title, preview, messages_json, now, expires_at, session_id_to_update) # 👈 created_at과 expires_at 추가
                )
            else:
                # 새 대화는 INSERT (새 기록 생성)
                # ttl_days 및 expires_at 계산은 함수 시작 부분에서 이미 한 번 했으므로 중복 제거
                # ❌ 필요 없는 재정의를 삭제하거나, 아니면 맨 위 ttl_days, expires_at을 사용하도록 통일합니다.
                # -------------------------------------------------------------
                # ttl_days = int(os.getenv("CHAT_HISTORY_TTL_DAYS", "1")) # 이 줄 삭제
                # expires_at = now + timedelta(days=ttl_days) # 이 줄 삭제
                # -------------------------------------------------------------
                cur.execute(
                    "INSERT INTO chat_history (user_id, title, preview, messages, created_at, expires_at) VALUES (%s, %s, %s, %s, %s, %s)",
                    (str(user_id), title, preview, messages_json, now, expires_at)
                )
            
            # 중요: DB 변경사항을 최종 반영하기 위해 commit을 추가해야 합니다.
            conn.commit()
            
    except Exception as e:
        conn.rollback()
        print(f"DB Error on save_history: {e}")
        return jsonify({"ok": False, "error": str(e)}), 500
    finally:
        conn.close()

    return jsonify({"ok": True}), 201

@chatbot_bp.route("/history/list", methods=["GET"])
def list_history():
    # ... (기존 list_history 코드는 거의 동일, 시간 포맷팅 부분만 개선)
    user_id = _current_user_id()
    if not user_id:
        return jsonify({"sessions": [], "error": "LOGIN_REQUIRED"})
    
    conn = get_db_conn()
    rows = []
    try:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT id, title, preview, created_at, expires_at FROM chat_history WHERE user_id=%s ORDER BY created_at DESC",
                (str(user_id),)
            )
            rows = cur.fetchall() or []
    finally:
        conn.close()

    now_utc = datetime.now(timezone.utc)
    for r in rows:
        exp = r.get("expires_at")
        if exp:
            if exp.tzinfo is None: exp = exp.replace(tzinfo=timezone.utc)
            r["ttl_seconds"] = max(0, int((exp - now_utc).total_seconds()))
            r["expires_at"] = exp.isoformat()
        ca = r.get("created_at")
        if ca:
            if ca.tzinfo is None: ca = ca.replace(tzinfo=timezone.utc)
            r["created_at"] = ca.isoformat()

    return jsonify({"sessions": rows})

# 추가(2-1-1): 대화 복원 기능을 위해 특정 세션의 전체 대화 내용을 ID로 조회하는 API
@chatbot_bp.route("/history/session/<int:session_id>", methods=["GET"])
def get_session(session_id):
    user_id = _current_user_id()
    if not user_id:
        return jsonify({"error": "LOGIN_REQUIRED"}), 401

    conn = get_db_conn()
    session_data = None
    try:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT messages FROM chat_history WHERE id=%s AND user_id=%s",
                (session_id, str(user_id))
            )
            result = cur.fetchone()
            if result and result.get('messages'):
                session_data = {"messages": json.loads(result['messages'])}
    finally:
        conn.close()

    if not session_data:
        return jsonify({"error": "Session not found"}), 404
        
    return jsonify(session_data)