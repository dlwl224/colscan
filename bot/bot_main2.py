import os
import sys
import re
import warnings  # ✅

# ✅ GPU 완전 차단(WSL에서 안전)
os.environ.setdefault("CUDA_VISIBLE_DEVICES", "")
os.environ.setdefault("TOKENIZERS_PARALLELISM", "false")
warnings.filterwarnings("ignore", category=FutureWarning, module="huggingface_hub.file_download")

from langchain.agents import Tool
from dotenv import load_dotenv
from langchain_google_genai import ChatGoogleGenerativeAI

# .env 로드
load_dotenv('api.env')

# 프로젝트 경로
project_root = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
if project_root not in sys.path:
    sys.path.insert(0, project_root)

# URL-BERT 경로
urlbert_base = os.path.join(project_root, 'urlbert', 'urlbert2')
if urlbert_base not in sys.path:
    sys.path.insert(0, urlbert_base)

# 1) LLM
if "GOOGLE_API_KEY" not in os.environ:
    raise ValueError("환경 변수에 'GOOGLE_API_KEY'가 설정되어 있지 않습니다.")

llm = ChatGoogleGenerativeAI(
    model="gemini-2.0-flash",
    temperature=0.01
)
# 2) 툴 로드
from bot.tools.urlbert_tool import load_urlbert_tool
from bot.tools.rag_tools import load_rag_tool, build_rag_index_from_jsonl
from urlbert.urlbert2.core.model_loader import load_inference_model

# URL-BERT
try:
    urlbert_model, urlbert_tokenizer = load_inference_model()
    url_tool = load_urlbert_tool(urlbert_model, urlbert_tokenizer)
except Exception as e:
    url_tool = Tool(
        name="URLBERT_ThreatAnalyzer",
        func=lambda x, _e=str(e): f"URL 분석 툴 로드 중 오류 발생: {_e}",
        description="URL 안전/위험 판단"
    )

# RAG 인덱스
RAG_INDEX_DIR = os.path.join(project_root, 'security_faiss_index')
RAG_DATA_PATH = os.path.join(project_root, 'data', 'rag_dataset.jsonl')
# if not os.path.exists(RAG_INDEX_DIR):
#     # 인덱스가 없으면 생성
#     build_rag_index_from_jsonl(RAG_DATA_PATH, RAG_INDEX_DIR)

# rag_tool = load_rag_tool(RAG_INDEX_DIR, llm)

# # Chat (일반 대화)
# def chat_fn(query: str) -> str:
#     raw = llm.invoke(query).content
#     return raw.strip()

# chat_tool = Tool(
#     name="Chat",
#     func=chat_fn,
#     description="일반 대화 및 간단한 정보 답변용"
# )

# # URL 정규식
# URL_PATTERN = re.compile(
#     r'(https?://\S+|(?:[A-Za-z0-9-]+\.)+[A-Za-z]{2,}\S*)'
# )



# def get_chatbot_response(query: str) -> dict:
#     """
#     사용자 질문(query)을 받아, 상황에 맞는 챗봇 답변을 dict 형태로 반환합니다.
#     """
#     text = query.strip()
    
#     # 1) URL 포함 시 -> URLBERT 툴 사용
#     match = URL_PATTERN.search(text)
#     if match:
#         url = match.group(1)
#         analysis_text = url_tool.func(url)
#         # 답변과 함께 어떤 종류의 답변인지(mode)를 함께 반환
#         return {"answer": analysis_text, "mode": "url_analysis"}

#     # 2) RAG(문서 검색) 시도
#     rag_out = rag_tool.func(text)
#     rag_answer = rag_out.get("answer", "")
#     rag_found = rag_out.get("found", False)
#     not_found_message = "해당 정보는 문서에서 찾을 수 없습니다."

#     # 'found'가 True이고, 답변이 있으며, '못 찾았다'는 메시지가 아닐 때만 성공으로 간주
#     if rag_found and rag_answer and not_found_message not in rag_answer:
#         sources = []
#         if rag_out.get("sources"):
#             seen, uniq = set(), []
#             for s in rag_out["sources"]:
#                 if s not in seen:
#                     seen.add(s)
#                     uniq.append(s)
#             sources = uniq[:5]
#         return {"answer": rag_answer, "mode": "rag", "sources": sources}

#     # 3) 위 두 경우에 해당하지 않으면 일반 대화
#     chat_answer = chat_tool.func(text)
#     return {"answer": chat_answer, "mode": "chat"}




# # 3) 대화 루프: 직접 이 파일을 실행했을 때 테스트용으로만 사용되도록 변경
# if __name__ == '__main__':
#     print("--- 챗봇 시작 (종료: '종료') ---")
#     while True:
#         try:
#             text = input("You ▶ ").strip()
#         except (EOFError, KeyboardInterrupt):
#             break

#         if text.lower() in {"종료", "exit"}:
#             break
#         if not text:
#             continue

#         #  위에서 만든 함수를 호출하여 결과를 받도록 변경
#         response = get_chatbot_response(text)
        
#         # [수정] 응답 형식에 맞게 출력 변경
#         answer = response.get("answer")
#         mode = response.get("mode")
        
#         if mode == "rag":
#             print("🔍 [RAG 문서 기반 응답]")
#         elif mode == "chat":
#             print("💬 [일반 Chat 응답]")

#         print(f"Bot ▶ Final Answer: {answer}")
        
#         if response.get("sources"):
#             print("📚 [출처]")
#             for s in response["sources"]:
#                 print(" -", s)







#새로운거
if not os.path.exists(RAG_INDEX_DIR):
    try:
        if os.path.exists(RAG_DATA_PATH):
            print(f"🔧 RAG 인덱스 생성: {RAG_DATA_PATH} -> {RAG_INDEX_DIR}")  # ✅
            build_rag_index_from_jsonl(RAG_DATA_PATH, RAG_INDEX_DIR)
        else:
            print(f"⚠️ RAG 데이터 없음: {RAG_DATA_PATH}")  # ✅
    except Exception as e:
        print(f"❌ RAG 인덱스 생성 실패: {e}")  # ✅

# ✅ RAG 로더에 폴백 추가 (CPU 강제는 rag_tools.py에서 적용)
try:
    rag_tool = load_rag_tool(RAG_INDEX_DIR, llm)
    print("✅ RAG Tool 로드 완료")  # ✅
except Exception as e:
    print(f"❌ RAG Tool 로드 중 오류 발생: {e}")  # ✅
    class _DummyRAG:
        def func(self, q):
            return {"answer": "", "found": False, "sources": [], "error": str(e)}
    rag_tool = _DummyRAG()

# Chat (일반 대화)
def chat_fn(query: str) -> str:
    raw = llm.invoke(query).content
    return raw.strip()

chat_tool = Tool(
    name="Chat",
    func=chat_fn,
    description="일반 대화 및 간단한 정보 답변용"
)

# URL 정규식
URL_PATTERN = re.compile(
    r'(https?://\S+|(?:[A-Za-z0-9-]+\.)+[A-Za-z]{2,}\S*)'
)

def get_chatbot_response(query: str) -> dict:
    """
    사용자 질문(query)을 받아, 상황에 맞는 챗봇 답변을 dict 형태로 반환합니다.
    """
    text = query.strip()

    # 1) URL 포함 시 -> URLBERT
    match = URL_PATTERN.search(text)
    if match:
        url = match.group(1)
        analysis_text = url_tool.func(url)
        return {"answer": analysis_text, "mode": "urlbert_analysis"}

    # 2) RAG 시도 (진단 로그 + 완화된 게이팅)
    try:
        rag_out = rag_tool.func(text)
    except Exception as e:
        print(f"[RAG] ERROR calling rag_tool: {e}")  # ✅
        rag_out = {}

    print(f"[RAG] raw out: {rag_out}")  # ✅
    rag_answer = (rag_out.get("answer") or "").strip() if isinstance(rag_out, dict) else ""
    rag_found  = bool(rag_out.get("found")) if isinstance(rag_out, dict) else False
    sources    = rag_out.get("sources") if isinstance(rag_out, dict) else []
    if sources is None: sources = []
    if not isinstance(sources, list): sources = [str(sources)]

    not_found_message = "찾을 수 없습니다"
    looks_ok = (
        bool(rag_answer) and
        (not_found_message not in rag_answer) and
        (len(sources) > 0 or rag_out.get("max_score", 0) >= 0.2)
    )

    if looks_ok or rag_found:
        # 중복 제거
        seen, uniq = set(), []
        for s in sources:
            if s not in seen:
                seen.add(s)
                uniq.append(s)
        print(f"[RAG] USE RAG, sources={len(uniq)}")  # ✅
        return {"answer": rag_answer, "mode": "rag", "sources": uniq[:5]}

    print("[RAG] FALLBACK -> chat")  # ✅
    # 3) 일반 대화
    chat_answer = chat_tool.func(text)
    return {"answer": chat_answer, "mode": "chat"}


if __name__ == '__main__':
    print("--- 챗봇 시작 (종료: '종료') ---")
    while True:
        try:
            text = input("You ▶ ").strip()
        except (EOFError, KeyboardInterrupt):
            break

        if text.lower() in {"종료", "exit"}:
            break
        if not text:
            continue

        response = get_chatbot_response(text)
        answer = response.get("answer")
        mode = response.get("mode")

        if mode == "rag":
            print("🔍 [RAG 문서 기반 응답]")
        elif mode == "chat":
            print("💬 [일반 Chat 응답]")

        print(f"Bot ▶ Final Answer: {answer}")

        if response.get("sources"):
            print("📚 [출처]")
            for s in response["sources"]:
                print(" -", s)