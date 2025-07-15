# bot_main.py

import re
from langchain.llms import LlamaCpp
from langchain.agents import initialize_agent, Tool
from langchain.memory import ConversationBufferMemory

# 1) URL-BERT 분석 툴
from bot.tools.urlbert_tool import load_urlbert_tool  
# 2) RAG 보안 문서 검색 툴
from bot.tools.rag_tools    import load_rag_tool     
# 3) (옵션) 일반 채팅용 툴: LLM을 그대로 래핑
def chat_tool_fn(query: str) -> str:
    return llm(query)

# ───────────────────────────────────────────────────────────────────────────────
# 0) 모델 로드 (한 번만)
llm = LlamaCpp(
    model_path="/content/drive/MyDrive/models/llama.bin",
    n_ctx=2048,
    temperature=0.2,
)
# 툴 로드
url_tool   = load_urlbert_tool((llm, None))  # urlbert_tool 내부에서 tokenizer가 필요 없으면 None
rag_tool   = load_rag_tool("security_faiss_index", llm)
chat_tool  = Tool(
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
)

# 3) 인터랙티브 채팅 함수
def chat(query: str) -> str:
    """
    Agent가 내부적으로:
    - URL 패턴 감지 → URLAnalyzer 호출
    - 보안 개념 질문 감지 → SecurityDocsQA 호출
    - 그 외 → Chat 툴 (LLM 직접 응답)
    """
    return agent.run(query)

if __name__ == "__main__":
    print("▶ Security Chatbot 시작 (종료: Ctrl+C)")
    try:
        while True:
            q = input("You ▶ ").strip()
            if not q:
                continue
            if q.lower() in {"quit", "exit"}:
                print("Bye 👋")
                break
            resp = chat(q)
            print("Bot ▶", resp)
    except KeyboardInterrupt:
        print("\nBye 👋")
