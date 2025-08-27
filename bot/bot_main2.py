import os
import sys
import re

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
if not os.path.exists(RAG_INDEX_DIR):
    # 인덱스가 없으면 생성
    build_rag_index_from_jsonl(RAG_DATA_PATH, RAG_INDEX_DIR)

rag_tool = load_rag_tool(RAG_INDEX_DIR, llm)

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

# 3) 대화 루프: URL → URLBERT / 아니면 RAG → 실패 시 Chat
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

        # 1) URL 포함 → URLBERT (규칙 1: 확실한 제어)
        match = URL_PATTERN.search(text)
        if match:
            url = match.group(1)
            result = url_tool.func(url)
            print(f"Bot ▶ Final Answer: {result}")
            continue

        # 2) RAG 우선 (규칙 2: 확실한 제어)
        rag_out = rag_tool.func(text)

        # RAG 실패 조건을 명확히 하여, 실패 시 Chat으로 넘어가도록 수정
        rag_answer = rag_out.get("answer", "")
        rag_found = rag_out.get("found", False)
        not_found_message = "해당 정보는 문서에서 찾을 수 없습니다."

        # 'found'가 True이고, 답변이 있으며, '못 찾았다'는 메시지가 아닐 때만 성공으로 간주
        if rag_found and rag_answer and not_found_message not in rag_answer:
            print("🔍 [RAG 문서 기반 응답]")
            print(f"Bot ▶ Final Answer: {rag_answer}")
            
            if rag_out.get("sources"):
                # (기존 소스 출력 코드)
                seen, uniq = set(), []
                for s in rag_out["sources"]:
                    if s not in seen:
                        seen.add(s)
                        uniq.append(s)
                if uniq:
                    print("📚 [출처]")
                    for s in uniq[:5]:
                        print(" -", s)
            continue

        # 3) RAG에서 못 찾으면 → Chat (규칙 3: 백업 플랜)
        print("💬 [일반 Chat 응답]")
        chat_out = chat_tool.func(text)
        print(f"Bot ▶ Final Answer: {chat_out}")