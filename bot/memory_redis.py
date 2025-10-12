# memory_redis.py
import os
import json
import time
import uuid
from typing import List, Dict, Any, Optional

try:
    import redis
except Exception as e:
    raise RuntimeError("redis 패키지가 필요합니다. `pip install redis` 해주세요.") from e

REDIS_URL = os.environ.get("REDIS_URL", "redis://localhost:6379/0")
r = redis.from_url(REDIS_URL, decode_responses=True)

# 기본 세션 TTL: 초 단위 (환경변수로 조정 가능)
DEFAULT_SESSION_TTL = int(os.environ.get("SESSION_TTL", 60 * 60 * 2))  # 기본 2시간

def new_session_id() -> str:
    """새로운 세션 ID 생성 (UUID4)."""
    return str(uuid.uuid4())

def _session_key(session_id: str) -> str:
    return f"chat:session:{session_id}"

def append_message(session_id: str, role: str, text: str, ttl: int = DEFAULT_SESSION_TTL) -> None:
    """
    세션에 메시지를 추가하고 TTL을 갱신합니다.
    role: "user" 또는 "bot"
    """
    key = _session_key(session_id)
    entry = {"role": role, "text": text, "ts": int(time.time())}
    r.rpush(key, json.dumps(entry))
    # 메시지 추가 시 TTL 갱신 -> "사용 중이면 계속 유지"
    r.expire(key, ttl)

def get_history(session_id: str, max_items: Optional[int] = 200) -> List[Dict[str, Any]]:
    """
    세션의 최근 메시지(max_items)를 가져옵니다.
    반환 형식: [{"role":"user"|"bot","text": "...", "ts": epoch}, ...]
    """
    key = _session_key(session_id)
    length = r.llen(key)
    if length == 0:
        return []
    if max_items is None or max_items >= length:
        items = r.lrange(key, 0, -1)
    else:
        start = max(0, length - max_items)
        items = r.lrange(key, start, length - 1)
    out = []
    for it in items:
        try:
            out.append(json.loads(it))
        except Exception:
            out.append({"role": "unknown", "text": it})
    return out

def clear_session(session_id: str) -> None:
    """세션 전체 삭제 (새 채팅시 호출)."""
    r.delete(_session_key(session_id))

def touch_session(session_id: str, ttl: int = DEFAULT_SESSION_TTL) -> None:
    """세션 TTL 갱신만 수행."""
    r.expire(_session_key(session_id), ttl)
