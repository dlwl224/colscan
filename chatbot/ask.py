import os
import re
import sys
from typing import List, Optional, Literal, Any, Dict
from dotenv import load_dotenv
from datetime import datetime

# ==== 0) 환경 및 경로 설정 =====================================================
load_dotenv('api.env')

project_root = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
if project_root not in sys.path:
    sys.path.insert(0, project_root)

urlbert_base = os.path.join(project_root, 'urlbert', 'urlbert2')
if urlbert_base not in sys.path:
    sys.path.insert(0, urlbert_base)

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from urllib.parse import urlsplit, urlunsplit  # [ADD] URL 정규화용

# [ADD] 캐시용 DB 함수
from Server.db_manager import get_urlbert_info_from_db, save_urlbert_to_db
# URL 분류 함수 임포트 (네 함수가 들어있는 파일 경로에 맞춰 조정)
from urlbert.urlbert2.core.urlbert_analyzer import classify_url_and_explain
from urlbert.urlbert2.core.model_loader import load_inference_model

from langchain.agents import Tool
from langchain_google_genai import ChatGoogleGenerativeAI
from bot.tools.urlbert_tool import load_urlbert_tool
from bot.tools.rag_tools import load_rag_tool, build_rag_index_from_jsonl

GOOGLE_API_KEY = os.getenv("GOOGLE_API_KEY")
if not GOOGLE_API_KEY:
    raise RuntimeError("환경 변수 'GOOGLE_API_KEY'가 설정되어 있지 않습니다. api.env를 확인하세요.")

llm = ChatGoogleGenerativeAI(
    model="gemini-2.0-flash",
    temperature=0.01
)

try:
    urlbert_model, urlbert_tokenizer = load_inference_model()
    url_tool = load_urlbert_tool(urlbert_model, urlbert_tokenizer)
except Exception as e:
    url_tool = Tool(
        name="URLBERT_ThreatAnalyzer",
        func=lambda x, _e=str(e): f"[URLBERT 로드 오류] {_e}",
        description="URL 안전/위험 판단"
    )

RAG_INDEX_DIR = os.path.join(project_root, 'security_faiss_index')
RAG_DATA_PATH = os.path.join(project_root, 'data', 'rag_dataset.jsonl')
if not os.path.exists(RAG_INDEX_DIR):
    build_rag_index_from_jsonl(RAG_DATA_PATH, RAG_INDEX_DIR)

rag_tool = load_rag_tool(RAG_INDEX_DIR, llm)

def chat_fn(query: str) -> str:
    raw = llm.invoke(query).content
    return (raw or "").strip()

chat_tool = Tool(
    name="Chat",
    func=chat_fn,
    description="일반 대화 및 간단한 정보 답변용"
)

URL_PATTERN = re.compile(
    r'(https?://\S+|(?:[A-Za-z0-9-]+\.)+[A-Za-z]{2,}\S*)'
)

# [ADD] URL 정규화: http/https, 소문자 도메인, 끝 슬래시 일관화
def normalize_url(u: str) -> str:
    s = urlsplit(u.strip())
    scheme = s.scheme or "https"
    # "naver.com"처럼 scheme 없는 입력 대응
    netloc = s.netloc or s.path
    path = s.path if s.netloc else ""
    path = "/" if path in ("", "/") else path.rstrip("/")
    return urlunsplit((scheme, netloc.lower(), path, "", ""))

app = FastAPI(title="sQanAR Ask API", version="1.0.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

class AskRequest(BaseModel):
    query: str

class AskSource(BaseModel):
    title: Optional[str] = None
    link: Optional[str] = None
    score: Optional[float] = None
    meta: Optional[Dict[str, Any]] = None

# ✅ [추가] 구조화된 URL 분석 결과 모델
class UrlbertResult(BaseModel):  # <-- 여기 추가
    url: str
    header_info: Optional[str] = None
    is_malicious: int
    confidence: float
    true_label: Optional[str] = None
    analysis_date: Optional[datetime] = None   # ✅ [ADD]

# ✅ [변경] AskResponse에 urlbert 필드 추가
class AskResponse(BaseModel):
    mode: Literal["urlbert", "rag", "chat"]
    answer: str
    sources: Optional[List[AskSource]] = None
    detected_url: Optional[str] = None
    urlbert: Optional[UrlbertResult] = None   # <-- 여기 추가

def handle_ask(query: str) -> AskResponse:
    text = (query or "").strip()
    if not text:
        raise HTTPException(status_code=400, detail="query가 비어 있습니다.")

    match = URL_PATTERN.search(text)
    if match:
        raw_url = match.group(1)
        url = normalize_url(raw_url)  # [ADD] 정규화

        # [ADD] 1) 캐시 조회
        cached = get_urlbert_info_from_db(url)
        if cached:
            return AskResponse(
                mode="urlbert",
                answer="URL 분석(캐시)",
                detected_url=url,
                urlbert=UrlbertResult(**cached)
            )

        # [ADD] 2) 모델 실행
        try:
            result = classify_url_and_explain(url, urlbert_model, urlbert_tokenizer)
        except Exception as e:
            raise HTTPException(status_code=500, detail=f"URL 분석 중 오류: {e}")

        # [ADD] 3) DB 저장
        try:
            save_urlbert_to_db(result)
        except Exception as e:
            # 저장 실패해도 응답은 리턴(로그만 남기고 진행)
            print(f"[WARN] save_urlbert_to_db 실패: {e}")

        return AskResponse(
            mode="urlbert",
            answer="URL 분석 완료",
            detected_url=url,
            urlbert=UrlbertResult(**result)
        )

    rag_out = rag_tool.func(text)
    rag_answer = (rag_out or {}).get("answer", "") or ""
    rag_found = bool((rag_out or {}).get("found", False))
    not_found_message = "해당 정보는 문서에서 찾을 수 없습니다."

    if rag_found and rag_answer and not_found_message not in rag_answer:
        raw_sources = (rag_out or {}).get("sources") or []
        seen = set()
        uniq_sources: List[AskSource] = []
        for s in raw_sources:
            key = str(s)
            if key in seen:
                continue
            seen.add(key)
            if isinstance(s, dict):
                uniq_sources.append(AskSource(
                    title=s.get("title"),
                    link=s.get("link") or s.get("source") or s.get("url"),
                    score=s.get("score"),
                    meta={k: v for k, v in s.items() if k not in {"title", "link", "source", "url", "score"}}
                ))
            else:
                uniq_sources.append(AskSource(title=None, link=str(s)))

        return AskResponse(
            mode="rag",
            answer=rag_answer,
            sources=uniq_sources[:5] or None
        )

    chat_answer = chat_tool.func(text)
    return AskResponse(
        mode="chat",
        answer=chat_answer,
        sources=None
    )

@app.post("/ask", response_model=AskResponse, response_model_exclude_none=True)  # [CHANGE]
def ask(req: AskRequest):
    try:
        return handle_ask(req.query)
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"ask 처리 중 오류: {e}")

@app.get("/healthz")
def healthz():
    return {"status": "ok"}

@app.get("/")
def root():
    return {"service": "sQanAR Ask API", "status": "ok"}

