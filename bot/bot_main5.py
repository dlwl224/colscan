# bot/bot_main5.py
# -*- coding: utf-8 -*-
import traceback
import os
import sys
import re
import warnings
import logging
import joblib
import json
import numpy as np
from typing import List, Dict, Any, Optional
from sklearn.metrics.pairwise import cosine_similarity

# GPU 차단 및 경고 무시
os.environ.setdefault("CUDA_VISIBLE_DEVICES", "")
os.environ.setdefault("TOKENIZERS_PARALLELISM", "false")
warnings.filterwarnings("ignore", category=FutureWarning, module="huggingface_hub.file_download")

from langchain.agents import Tool
from dotenv import load_dotenv
from langchain_google_genai import ChatGoogleGenerativeAI
from langchain_core.prompts import PromptTemplate
from langchain.chains import ConversationalRetrievalChain
from langchain_community.vectorstores import FAISS
from langchain_community.embeddings import HuggingFaceEmbeddings
from langchain_core.messages import HumanMessage, AIMessage
# .env 로드
load_dotenv('api.env')

# 프로젝트 루트
project_root = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
if project_root not in sys.path:
    sys.path.insert(0, project_root)

# logging 설정
logging.basicConfig(level=os.environ.get("LOG_LEVEL", "INFO"))
log = logging.getLogger("bot_main5")

# Redis memory
try:
    from bot.memory_redis import append_message, get_history, new_session_id, clear_session, touch_session
    REDIS_AVAILABLE = True
except Exception:
    REDIS_AVAILABLE = False

# 1) LLM 초기화
if "GOOGLE_API_KEY" not in os.environ:
    raise ValueError("환경 변수에 'GOOGLE_API_KEY'가 설정되어 있지 않습니다.")
llm = ChatGoogleGenerativeAI(model="gemini-2.0-flash", temperature=0.01)

# 2) URL-BERT
from bot.tools.urlbert_tool import load_urlbert_tool
from urlbert.urlbert2.core.model_loader import GLOBAL_MODEL, GLOBAL_TOKENIZER
from bot.feature_extractor import build_raw_features, summarize_features_for_explanation

try:
    url_tool = load_urlbert_tool(GLOBAL_MODEL, GLOBAL_TOKENIZER)
    log.info("✅ URL-BERT 툴 로드 완료")
except Exception as e:
    log.error(f"❌ URL-BERT 툴 로드 실패: {e}")
    url_tool = Tool(
        name="URLBERT_ThreatAnalyzer",
        func=lambda x, _e=str(e): f"URL 분석 툴 로드 중 오류 발생: {_e}",
        description="URL 안전/위험 판단"
    )

# 3) RAG 인덱스 생성
RAG_INDEX_DIR = os.path.join(project_root, 'security_faiss_index')
RAG_DATA_PATH = os.path.join(project_root, 'data', 'rag_dataset.jsonl')
if not os.path.exists(RAG_INDEX_DIR) and os.path.exists(RAG_DATA_PATH):
    log.info(f"🔧 RAG 인덱스 생성: {RAG_DATA_PATH} -> {RAG_INDEX_DIR}")
    from bot.tools.rag_tools import build_rag_index_from_jsonl
    build_rag_index_from_jsonl(RAG_DATA_PATH, RAG_INDEX_DIR)

# 4) RAG 체인 구성
embeddings, vector_db, retriever, conversational_rag_chain = None, None, None, None
try:
    embeddings = HuggingFaceEmbeddings(model_name='jhgan/ko-sroberta-multitask')
    if os.path.exists(RAG_INDEX_DIR):
        vector_db = FAISS.load_local(RAG_INDEX_DIR, embeddings, allow_dangerous_deserialization=True)
        retriever = vector_db.as_retriever(search_type="mmr", search_kwargs={'k':5,'fetch_k':10})
        conversational_rag_chain = ConversationalRetrievalChain.from_llm(
            llm=llm, retriever=retriever, memory=None, return_source_documents=True, output_key='answer'
        )
        log.info("✅ RAG 체인 로드 완료")
except Exception as e:
    log.error(f"❌ RAG 체인 로드 실패: {e}")
    conversational_rag_chain = None

# 5) RAG/CHAT 라우터
RAG_ROUTER_PATH = os.path.join(project_root, 'models', 'rag_chat_router.pkl')
try:
    RAG_CHAT_ROUTER_MODEL = joblib.load(RAG_ROUTER_PATH) if os.path.exists(RAG_ROUTER_PATH) else None
    if RAG_CHAT_ROUTER_MODEL:
        log.info("✅ RAG-CHAT 라우터 로드 완료")
    else:
        log.warning("⚠️ RAG-CHAT 라우터 없음, 기본 CHAT 사용")
except Exception as e:
    log.error(f"❌ RAG-CHAT 라우터 로드 실패: {e}")
    RAG_CHAT_ROUTER_MODEL = None

# 6) Security centroid
SECURITY_CENTROID_PATH = os.path.join(project_root, 'models', 'security_centroid.npy')
try:
    SECURITY_CENTROID = np.load(SECURITY_CENTROID_PATH) if os.path.exists(SECURITY_CENTROID_PATH) else None
    if SECURITY_CENTROID is not None and SECURITY_CENTROID.ndim == 2 and SECURITY_CENTROID.shape[0] == 1:
        SECURITY_CENTROID = SECURITY_CENTROID.reshape(-1)
    log.info("✅ Security centroid 로드 완료")
except Exception as e:
    log.error(f"❌ Security centroid 로드 실패: {e}")
    SECURITY_CENTROID = None

# 7) Prompts / Keywords
from bot.prompts import SIMPLE_URL_PROMPT, URL_PROMPT, WHY_KEYWORDS, MEMORY_KEYWORDS
simple_url_prompt = SIMPLE_URL_PROMPT
url_prompt = URL_PROMPT

# 8) 정규식
URL_PATTERN = re.compile(r'(https?://\S+|(?:[A-Za-z0-9-]+\.)+[A-Za-z]{2,}\S*)')

# 9) verdict 추출
def _infer_verdict_from_text(bert_text: str) -> str:
    t = (bert_text or "").lower()
    bad_tokens = ["malicious", "phishing", "suspicious", "악성", "위험", "유해"]
    good_tokens = ["benign", "legitimate", "safe", "정상", "안전"]
    if any(tok in t for tok in bad_tokens) and not any(tok in t for tok in good_tokens):
        return "악성"
    if any(tok in t for tok in good_tokens) and not any(tok in t for tok in bad_tokens):
        return "정상"
    return "정상"

# 10) security embedding 판단
def is_security_related_by_embedding(query: str, embedding_model, centroid, threshold=0.6) -> bool:
    q = (query or "").strip()
    if not q: return False
    try:
        if centroid is not None and embedding_model is not None:
            emb = embedding_model.embed_query(q)
            sim = cosine_similarity(np.array(emb).reshape(1,-1), np.array(centroid).reshape(1,-1))[0][0]
            return sim >= threshold
    except Exception:
        pass
    fallback = ["보안","해킹","취약점","피싱","랜섬웨어","악성","CVE"]
    return any(k in q for k in fallback)

# 11) history → text
def history_to_text(chat_history: Optional[Any]) -> str:
    if not chat_history: return ""
    out = []
    if isinstance(chat_history, list):
        for m in chat_history:
            role = m.get("role","user") if isinstance(m, dict) else getattr(m,"role","user")
            content = m.get("text","") if isinstance(m, dict) else getattr(m,"content",None) or getattr(m,"text","")
            out.append(f"{role.upper()}: {content}")
    return "\n".join(out)


def format_history_for_langchain(chat_history: Optional[Any]) -> list:
    """
    [{'role': 'user', 'text': '...'}, ...] 형식의 기록을
    [HumanMessage(...), AIMessage(...)] 형식으로 변환합니다.
    """
    if not chat_history:
        return []
    
    formatted_history = []
    for message in chat_history:
        role = message.get("role", "user")
        text = message.get("text", "")
        if role == "user":
            formatted_history.append(HumanMessage(content=text))
        else: # 'assistant', 'bot', 'ai' 등 user가 아닌 모든 경우
            formatted_history.append(AIMessage(content=text))
            
    return formatted_history
# 12) 핵심 함수
def get_chatbot_response(query: str, chat_history: Optional[Any]=None, session_id: Optional[str]=None) -> Dict[str, Any]:
    text = (query or "").strip()
    if not text: return {"answer": "", "mode": "empty"}

    # Redis 세션
    if session_id and REDIS_AVAILABLE:
        try: touch_session(session_id)
        except Exception: pass

    history_text = history_to_text(chat_history)
    match = URL_PATTERN.search(text)
    is_why_question = any(k in text for k in WHY_KEYWORDS)
    is_memory_question = any(k in text for k in MEMORY_KEYWORDS)

    # 1) 메모리 질문
    if is_memory_question and chat_history:
        memory_prompt = f"당신은 사용자와의 대화를 기억하는 친절한 챗봇입니다.\n\n[대화 기록]\n{history_text}\n\n[질문]\n{text}\n\n[최종 답변]:"
        try: ans = llm.invoke(memory_prompt).content
        except Exception: ans = "메모리 조회 중 오류 발생"
        return {"answer": ans, "mode":"memory"}

    # 2) URL 분석
    if match:
        url = match.group(1)
        try: bert_result = url_tool.func(url)
        except Exception as e: bert_result = f"URL-BERT 오류: {e}"

        if is_why_question:
            try:
                df = build_raw_features(url)
                verdict = _infer_verdict_from_text(bert_result)
                reasons = summarize_features_for_explanation(df, verdict, top_k=3) if not df.empty else ["세부 특징 추출 실패"]
                feature_details = "\n".join(f"- {r}" for r in reasons)
            except Exception as e:
                feature_details = f"세부 특징 추출 오류: {e}"

            prompt = url_prompt.format(user_query=text, bert_result=bert_result, feature_details=feature_details)
            try: ans = llm.invoke(prompt).content
            except Exception: ans = "상세 분석 생성 실패"
            return {"answer": ans, "mode":"url_analysis_detailed","url":url}
        else:
            prompt = simple_url_prompt.format(bert_result=bert_result)
            try: ans = llm.invoke(prompt).content
            except Exception: ans = "간단 분석 생성 실패"
            return {"answer": ans, "mode":"url_analysis_simple","url":url}

    # 3) RAG vs CHAT 라우터
    action = "CHAT"
    if RAG_CHAT_ROUTER_MODEL:
        try:
            action = RAG_CHAT_ROUTER_MODEL.predict([text])[0]
            log.info(f"RAG_ROUTER predict -> {action} for text: {text!r}")
        except Exception as e:
            log.exception(f"RAG router predict 실패: {e}")
            action = "CHAT"

    # === 새로 추가한 부분: retriever / FAISS 상태 점검 로깅 ===
    try:
        # FAISS 인덱스 총 문서 수 출력 (가능하면)
        if vector_db is not None:
            try:
                idx = getattr(vector_db, "index", None)
                if idx is not None and hasattr(idx, "ntotal"):
                    log.info(f"FAISS index ntotal: {idx.ntotal}")
                else:
                    log.info("vector_db.index 또는 ntotal 속성 없음")
            except Exception:
                log.exception("FAISS ntotal 조회 중 오류")

        # retriever 테스트 검색
        if retriever is not None:
            try:
                sample_docs = retriever.get_relevant_documents(text)
                log.info(f"retriever.get_relevant_documents -> {len(sample_docs)} docs")
                for i, d in enumerate(sample_docs[:3]):
                    meta = getattr(d, "metadata", {})
                    snippet = (getattr(d, "page_content", "") or "")[:200]
                    log.info(f"doc[{i}] source={meta.get('source')} snippet={snippet!r}")
            except Exception:
                log.exception("retriever.get_relevant_documents 호출 실패")
    except Exception:
        log.exception("retriever/FAISS 상태 점검 중 예외")

    # RAG 호출 블록 (예외 시 스택트레이스 로깅 + 개발시 상세 반환)
    if action == "RAG" and conversational_rag_chain:
        try:
            log.info(f"RAG 호출 시도: text={text!r}")
            # LangChain이 이해할 수 있는 형식으로 대화 기록 변환
            langchain_chat_history = format_history_for_langchain(chat_history)
            
            # invoke 메서드를 사용하여 체인 호출
            res = conversational_rag_chain.invoke({
                "question": text,
                "chat_history": langchain_chat_history
            })
            log.info("RAG 체인 호출 성공")
            sources = []
            for doc in res.get("source_documents", []):
                try: src = getattr(doc, "metadata", {}).get("source")
                except Exception: src = None
                if src and src not in sources: sources.append(src)
            return {"answer": res.get("answer",""), "mode":"rag", "sources":sources}

        except Exception as e:
            tb = traceback.format_exc()
            log.error(f"RAG 체인 호출 실패: {e}\n{tb}")
            # 개발 환경이면 상세 에러 반환
            if os.environ.get("DEBUG", "").lower() in ("1", "true", "yes"):
                return {"answer": f"문서 검색 중 오류 (체인 호출 실패): {e}\n{tb}", "mode":"rag_error"}
            return {"answer":"문서 검색 중 오류 (체인 호출 실패)", "mode":"rag_error"}

    else:
        # RAG 분기로 안 가는 경우(일반 CHAT 또는 보안 플래그)
        sec_flag = False
        try: sec_flag = is_security_related_by_embedding(text, embeddings, SECURITY_CENTROID)
        except Exception:
            sec_flag = any(k in text for k in ["보안","해킹","취약점","피싱","랜섬웨어","CVE"])

        if sec_flag and conversational_rag_chain:
            try:
                # 안전하게 invoke 호출 시도
                try:
                    res = conversational_rag_chain.invoke({"question":text,"chat_history":chat_history})
                except Exception:
                    # 마지막 보루: __call__ 시도
                    res = conversational_rag_chain({"question":text,"chat_history":chat_history})
            except Exception as e:
                log.exception(f"sec_flag 상태에서 conversational_rag_chain 호출 실패: {e}")
                res = {"answer":"챗봇 오류"}
            return {"answer": res.get("answer",""), "mode":"chat"}
        else:
            try:
                ans = llm.invoke(f"[대화 기록]\n{history_text}\n{text}").content
            except Exception:
                ans = "내부 오류"
            return {"answer": "죄송합니다. 저는 보안 전문 챗봇으로, 보안 관련 질문에만 답변할 수 있습니다.", "mode":"chat_guardrail"}


if __name__=="__main__":
    print("--- 챗봇 시작 (종료: '종료') ---")
    while True:
        try: text=input("You ▶ ").strip()
        except (EOFError,KeyboardInterrupt): break
        if text.lower() in ["종료","exit"]: break
        if not text: continue
        res=get_chatbot_response(text)
        print(f"Bot ▶ {res.get('answer')}\n")
