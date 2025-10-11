# routes/chatbot.py
from flask import Blueprint, render_template, session, request, jsonify
from werkzeug.exceptions import BadRequest
import json
from datetime import datetime, timedelta, timezone
import os

# DB 연결 함수 import
from Server.DB_conn import get_connection_dict as get_db_conn

# bot_main5 (앱용) 및 Redis 메모리 헬퍼 import
# bot 패키지 구조에 따라 경로가 맞는지 확인하세요 (bot/ 위치에 memory_redis.py, bot_main5.py 존재)
from bot.bot_main5 import get_chatbot_response, llm
from bot.memory_redis import append_message, get_history, new_session_id, clear_session, touch_session

chatbot_bp = Blueprint("chatbot", __name__, url_prefix="/chatbot")

SESSION_TIMEOUT_MINUTES = 30 

# 추가: 현재 로그인 사용자 id를 세션에서만 꺼내는 헬퍼
def _current_user_id():
    """
    세션 기반 로그인 사용자 ID를 'user_id' 키에서 직접 읽어옵니다.
    """
    return session.get("user_id")


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


@chatbot_bp.route("/api", methods=["POST"])
def chatbot_api():
    payload = request.get_json(silent=True) or {}
    q = (payload.get("query") or payload.get("message") or "").strip()
    if not q:
        raise BadRequest("query가 비어 있습니다.")

    session_id = payload.get("session_id")

    print(f"--- API 요청 수신 ---")
    print(f"프론트에서 받은 session_id: {session_id}")
    
    if not session_id:
        try:
            session_id = new_session_id()
            print(f"새로운 session_id 생성: {session_id}")
        except Exception:
            session_id = None
    try:
        data = get_chatbot_response(query=q, session_id=session_id) or {}
    except Exception as e:
        print(f"[chatbot_api] get_chatbot_response error: {e}")
        return jsonify({"reply": "오류가 발생했어요.", "error": str(e)}), 500

    #  프론트엔드로 최종 응답 전달 
    reply = data.get("reply") or data.get("answer") or ""
    response_payload = {
        "reply": reply,
        "answer": data.get("answer") or reply,
        "mode": data.get("mode") or payload.get("mode") or "basic",
        "sources": data.get("sources") or [],
        "session_id": session_id
    }
    return jsonify(response_payload), 200

# 추가: 히스토리 저장/조회 API

@chatbot_bp.route("/history/save", methods=["POST"])
def save_history():
    payload  = request.get_json(silent=True) or {}
    # 변경: 프론트에서 온 user_id는 무시하고 세션에서만 판정
    user_id  = _current_user_id()
    messages = payload.get("messages") or [] 
    # 💡 [핵심 추가] 클라이언트에서 기존 대화의 ID를 보낼 경우를 처리합니다.
    history_id = payload.get("history_id") 

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
    # try:
    #     with conn.cursor() as cur:
    #         cur.execute(
    #             "SELECT id, created_at FROM chat_history WHERE user_id = %s ORDER BY created_at DESC LIMIT 1",
    #             (str(user_id),)
    #         )
    #         last_session = cur.fetchone()

    #         session_id_to_update = None
    #         if last_session:
    #             last_time = last_session['created_at'].replace(tzinfo=timezone.utc)
    #             if (now - last_time) < timedelta(minutes=SESSION_TIMEOUT_MINUTES):
    #                 session_id_to_update = last_session['id']

    #         if session_id_to_update:
    #             # 30분 내 대화가 있으면 UPDATE (기록 덮어쓰기)
    #             cur.execute(
    #                 "UPDATE chat_history SET title=%s, preview=%s, messages=%s, created_at=%s, expires_at=%s WHERE id=%s",
    #                 (title, preview, messages_json, now, expires_at, session_id_to_update)
    #             )
    #         else:
    #             # 새 대화는 INSERT (새 기록 생성)
    #             cur.execute(
    #                 "INSERT INTO chat_history (user_id, title, preview, messages, created_at, expires_at) VALUES (%s, %s, %s, %s, %s, %s)",
    #                 (str(user_id), title, preview, messages_json, now, expires_at)
    #             )
    #         conn.commit()
    # except Exception as e:
    #     conn.rollback()
    #     print(f"DB Error on save_history: {e}")
    #     return jsonify({"ok": False, "error": str(e)}), 500
    # finally:
    #     conn.close()

    # return jsonify({"ok": True}), 201

    try:
        with conn.cursor() as cur:
            
            # 💡 [수정 로직 시작]
            if history_id:
                # 1. history_id가 있으면 기존 대화에 추가 (UPDATE)
                # 클라이언트가 복원한 세션을 저장할 때 history_id를 보낸다고 가정합니다.
                cur.execute(
                    "UPDATE chat_history SET title=%s, preview=%s, messages=%s, created_at=%s, expires_at=%s WHERE id=%s AND user_id=%s",
                    (title, preview, messages_json, now, expires_at, history_id, str(user_id))
                )
                
                if cur.rowcount == 0:
                    # 해당 ID가 없거나 사용자 ID가 일치하지 않으면 새로 INSERT (예외 처리)
                    cur.execute(
                        "INSERT INTO chat_history (user_id, title, preview, messages, created_at, expires_at) VALUES (%s, %s, %s, %s, %s, %s)",
                        (str(user_id), title, preview, messages_json, now, expires_at)
                    )
                    
            else:
                # 2. history_id가 없으면 새로운 대화로 판단 (INSERT)
                # 새로운 대화를 시작할 때 클라이언트가 history_id를 보내지 않습니다.
                cur.execute(
                    "INSERT INTO chat_history (user_id, title, preview, messages, created_at, expires_at) VALUES (%s, %s, %s, %s, %s, %s)",
                    (str(user_id), title, preview, messages_json, now, expires_at)
                )
            # 💡 [수정 로직 끝]

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


# 추가: 특정 세션의 전체 대화 내용을 ID로 조회하는 API
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
