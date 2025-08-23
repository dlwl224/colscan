import os
import sys
import re
import json

from langchain.agents import initialize_agent, AgentType, Tool
from langchain.memory import ConversationBufferMemory
from langchain_core.prompts import PromptTemplate

# Gemini API를 사용하기 위한 임포트
from langchain_google_genai import ChatGoogleGenerativeAI
from langchain_community.callbacks import get_openai_callback
from dotenv import load_dotenv

# .env 파일 로드
load_dotenv('api.env')

# 프로젝트 루트 및 경로 설정
project_root = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
if project_root not in sys.path:
    sys.path.insert(0, project_root)
# URL-BERT 경로 추가
urlbert_base = os.path.join(project_root, 'urlbert', 'urlbert2')
if urlbert_base not in sys.path:
    sys.path.insert(0, urlbert_base)


# 1. LLM 세팅 
# 환경 변수에서 Gemini API 키를 가져옵니다.
if "GOOGLE_API_KEY" not in os.environ:
    raise ValueError("환경 변수에 'GOOGLE_API_KEY'가 설정되어 있지 않습니다.")

llm = ChatGoogleGenerativeAI(
    model="gemini-2.0-flash",
    temperature=0.01
)

# 툴 로드 함수 임포트
from bot.tools.urlbert_tool import load_urlbert_tool
from bot.tools.rag_tools import load_rag_tool, build_rag_index_from_jsonl
from urlbert.urlbert2.core.model_loader import load_inference_model

# 2. 툴 인스턴스 생성
# URL-BERT Tool
try:
    urlbert_model, urlbert_tokenizer = load_inference_model()
    url_tool = load_urlbert_tool(urlbert_model, urlbert_tokenizer)
except Exception as e:
    url_tool = Tool(
        name="URLBERT_ThreatAnalyzer",
        func=lambda x: f"URL 분석 툴 로드 중 오류 발생: {e}",
        description="URL 안전/위험 판단"
    )

# RAG Tool (인덱스 없으면 생성)
RAG_INDEX_DIR = os.path.join(project_root, 'security_faiss_index')
RAG_DATA_PATH = os.path.join(project_root, 'data', 'rag_dataset.jsonl')
if not os.path.exists(RAG_INDEX_DIR):
    build_rag_index_from_jsonl(RAG_DATA_PATH, RAG_INDEX_DIR)
rag_tool = load_rag_tool(RAG_INDEX_DIR, llm)

# Chat 툴 (일반 대화)
def chat_fn(query: str) -> str:
    raw = llm.invoke(query).content
    cleaned = raw.strip()
    return cleaned
chat_tool = Tool(
    name="Chat",
    func=chat_fn,
    description="일반 대화 및 간단한 정보 답변용"
)


# 4. 시스템 프롬프트
system_prompt_for_agent = """
<|begin_of_text|><|start_header_id|>system<|end_header_id|>
너는 한국어로 작동하는 보안 전문 챗봇이야. 사용자 입력에 따라 적절한 툴을 호출해 정보를 제공해.

[도구 선택 규칙]
- 입력에 URL(https:// 포함 또는 도메인 형태)이 있으면 → Action: URLBERT_ThreatAnalyzer
- 사용자가 보안 관련 용어나 개념(예: 피싱, 큐싱, SSL, 도메인)에 대해 묻는 질문이면 → Action: SecurityDocsQA
- 그 외, 개인적인 질문, 인사말, 또는 SecurityDocsQA로 해결할 수 없는 일반적인 대화 질문이면 → Action: Chat

[형식 규칙]
- 반드시 Thought → Action → Action Input → Observation → Final Answer 순서로 응답할 것
- Action에는 툴 이름만 정확히 쓸 것 (예: Action: SecurityDocsQA)
- Action Input은 사용자 질문을 그대로 순수 문자열로 입력
- Observation 이후에는 추가 분석 없이 Final Answer로 바로 끝내기
- Final Answer는 반드시 "Final Answer: ..." 형식으로 시작하고, 그 뒤에 문장 1~3개 이내 한국어 응답만 작성
- Final Answer 이후에는 절대 다른 문장 출력 금지 (ex. 반복 금지)
<|eot_id|>"""

final_agent_prompt = PromptTemplate.from_template(
    system_prompt_for_agent + "<|start_header_id|>user<|end_header_id|>\n{input}<|eot_id|><|start_header_id|>assistant<|end_header_id|>\n{agent_scratchpad}"
)
tools = [url_tool, rag_tool, chat_tool]
memory = ConversationBufferMemory(memory_key="chat_history", return_messages=True)

agent_executor = initialize_agent(
    tools=tools,
    llm=llm,
    agent=AgentType.ZERO_SHOT_REACT_DESCRIPTION,
    memory=memory,
    verbose=True,
    agent_kwargs={
        "prompt": final_agent_prompt,
        "stop": ["\nFinal Answer:", "<|eot_id|>"]
    }
)


# URL 탐지 정규식 (http/https URL 및 도메인 형태 모두 감지)
URL_PATTERN = re.compile(
    r'(https?://\S+|(?:[A-Za-z0-9-]+\.)+[A-Za-z]{2,}\S*)'
)

# 5. 대화 루프
if __name__ == '__main__':
    print("--- 챗봇 시작 (종료: '종료') ---")
    while True:
        text = input("You ▶ ").strip()
        if text.lower() in {"종료", "exit"}:
            break

        # 문장 내 URL 감지 및 툴 직접 호출
        match = URL_PATTERN.search(text)
        if match:
            url = match.group(1)
            result = url_tool.func(url)
            print(f"Bot ▶ Final Answer: {result}")
            continue
        # URL이 아니면 RAG 먼저
        rag_out = rag_tool.func(text)

        # 문자열로 반환된 경우 처리
        if isinstance(rag_out, str):
            # print("🔎 [RAG 오류 또는 메시지]")
            print(f"Bot ▶ Final Answer: {rag_out}")
            continue

        if rag_out.get("found") and rag_out.get("answer"):
            # print("🔎 [RAG 검색 결과]")
            print(f"Bot ▶ Final Answer: {rag_out['answer']}")
        else:
            chat_out = chat_tool.func(text)
            # print("🔎 [일반 대화]")
            print(f"Bot ▶ Final Answer: {chat_out}")

        # 에이전트 호출
        out = agent_executor.invoke({"input": text}).get('output', '')
        print("Bot ▶", out)