# bot/bot_main.py

import re
import os
import sys
import torch # LlamaCpp에서 GPU 사용을 위해 필요할 수 있음

from langchain.agents import initialize_agent, Tool
from langchain.memory import ConversationBufferMemory
from langchain_community.llms import LlamaCpp
from langchain.callbacks.manager import CallbackManager
from langchain.callbacks.streaming_stdout import StreamingStdOutCallbackHandler

# project_root는 이제 colscan의 절대 경로를 직접 지정합니다.
project_root = "/content/drive/MyDrive/sQanAR/colscan"
if project_root not in sys.path:
    sys.path.insert(0, project_root)

# urlbert/urlbert2/ 이 sys.path 에 있어야 urlbert.urlbert2.core.model_loader 등 임포트 가능
urlbert_base_path = os.path.join(project_root, 'urlbert', 'urlbert2')
if urlbert_base_path not in sys.path:
    sys.path.insert(0, urlbert_base_path)

# 1) URL-BERT 분석 툴
from bot.tools.urlbert_tool import load_urlbert_tool
# 2) RAG 보안 문서 검색 툴 (인덱스 생성 함수 포함)
from bot.tools.rag_tools import load_rag_tool, build_rag_index_from_jsonl # ⭐ 인덱스 생성 함수 임포트 추가

def chat_tool_fn(query: str) -> str:
    return llm(query)

# ───────────────────────────────────────────────────────────────────────────────

# GGUF 모델 경로
MODEL_GGUF_PATH = "/content/drive/MyDrive/sQanAR/colscan/models/gguf/llama-3-Korean-Bllossom-8B-Q4_K_M.gguf"

if not os.path.exists(MODEL_GGUF_PATH):
    print(f"❌ 오류: GGUF 모델 파일이 다음 경로에 없습니다: {MODEL_GGUF_PATH}")
    print("이전 Colab 셀에서 GGUF 모델 다운로드를 먼저 성공적으로 완료했는지 확인해주세요.")
    sys.exit(1) # 파일이 없으면 스크립트 종료

print("Llama GGUF 모델 로드 시작...")
llm = LlamaCpp(
    model_path=MODEL_GGUF_PATH,
    n_gpu_layers=-1, # -1은 가능한 모든 레이어를 GPU에 로드 (GPU 메모리가 허용하는 한)
    n_ctx=8192,      # Llama-3의 최대 컨텍스트 길이
    max_tokens=1024, # 생성할 최대 토큰 수
    temperature=0.7, # 창의성 조절
    top_p=0.9,
    callback_manager=CallbackManager([StreamingStdOutCallbackHandler()]),
    verbose=True, # 자세한 로그 출력
)
print("✅ Llama GGUF 모델 로드 및 LangChain LLM 객체 생성 완료.")

# 툴 로드
from urlbert.urlbert2.core.model_loader import load_inference_model as load_urlbert_inference_model
urlbert_model, urlbert_tokenizer = load_urlbert_inference_model()
url_tool = load_urlbert_tool(urlbert_model, urlbert_tokenizer)
print("✅ URL-BERT Tool 로드 완료.")

# RAG 인덱스 경로 및 생성 로직
# security_faiss_index는 colscan 바로 아래에 있다고 가정합니다.
RAG_INDEX_PATH = os.path.join(project_root, "security_faiss_index")

# RAG 데이터 JSONL 파일 경로를 절대 경로로 명시합니다.
# 사용자님의 답변에 따라 rag_dataset.jsonl은 /content/drive/MyDrive/sQanAR/colscan/data 안에 있습니다.
RAG_DATA_JSONL_PATH = "/content/drive/MyDrive/sQanAR/colscan/data/rag_dataset.jsonl"


if not os.path.exists(RAG_INDEX_PATH):
    print(f"RAG 인덱스 폴더가 다음 경로에 없습니다: {RAG_INDEX_PATH}")
    print("RAG 인덱스 생성을 시도합니다...")
    if os.path.exists(RAG_DATA_JSONL_PATH):
        try:
            print(f"RAG 인덱스 생성 시작 (JSONL 파일: {RAG_DATA_JSONL_PATH})...")
            # build_rag_index_from_jsonl 함수는 임베딩 모델도 필요합니다.
            # 여기서는 LangChain의 기본 임베딩 모델 로딩 방식을 사용한다고 가정합니다.
            # 만약 특정 임베딩 모델 로딩이 필요하면 rag_tools.py 또는 여기서 추가 로직 필요.
            build_rag_index_from_jsonl(jsonl_path=RAG_DATA_JSONL_PATH, index_path=RAG_INDEX_PATH)
            print("✅ RAG 인덱스 생성 완료.")
        except Exception as e:
            print(f"❌ RAG 인덱스 생성 중 오류 발생: {e}")
            print("FAISS 인덱스 생성에 필요한 데이터나 라이브러리 문제를 확인해주세요.")
            sys.exit(1)
    else:
        print(f"❌ 오류: RAG 데이터 JSONL 파일이 없습니다: {RAG_DATA_JSONL_PATH}")
        print("FAISS 인덱스를 생성할 수 없습니다. 챗봇이 제대로 작동하지 않을 수 있습니다.")
        sys.exit(1) # 파일이 없으면 스크립트 종료

rag_tool = load_rag_tool(RAG_INDEX_PATH, llm)
print("✅ RAG Tool 로드 완료.")

chat_tool = Tool(
    name="Chat",
    func=chat_tool_fn,
    description="일반 대화 및 추가 정보 검색에 사용되는 툴입니다. URL 분석이나 보안 문서 검색이 필요 없을 때 LLM 자체 답변용."
)

tools = [url_tool, rag_tool, chat_tool]

# 1) 메모리(대화 기록)
memory = ConversationBufferMemory(memory_key="chat_history")

# 2) Agent 초기화: zero-shot tool routing
agent = initialize_agent(
    tools=tools,
    llm=llm,
    agent="zero-shot-react-description",
    verbose=True,
    memory=memory,
    handle_parsing_errors=True # 파싱 오류 발생 시 에이전트가 더 잘 처리하도록
)

# 3) 인터랙티브 채팅 함수
def chat(query: str) -> str:
    """
    Agent가 내부적으로:
    - URL 패턴 감지 → URLAnalyzer 호출
    - 보안 개념 질문 감지 → SecurityDocsQA 호출
    - 그 외 → Chat 툴 (LLM 직접 응답)
    """
    try:
        response = agent.run(query)
        return response
    except Exception as e:
        # 오류 발생 시 사용자에게 메시지 반환
        return f"❌ 챗봇 처리 중 오류 발생: {e}"

if __name__ == "__main__":
    print("\n--- 챗봇 테스트 시작 ---")
    print("'종료'를 입력하면 챗봇을 종료합니다.")
    try:
        while True:
            q = input("You ▶ ").strip()
            if not q:
                continue
            if q.lower() in {"quit", "exit", "종료"}:
                print("챗봇을 종료합니다. 👋")
                break
            resp = chat(q)
            print("Bot ▶", resp)
    except KeyboardInterrupt:
        print("\n챗봇을 강제 종료합니다. 👋")