import os
import sys
import re

from langchain.agents import initialize_agent, AgentType, Tool
from langchain.memory import ConversationBufferMemory
from langchain_community.llms import LlamaCpp
from langchain.callbacks.manager import CallbackManager
from langchain.callbacks.streaming_stdout import StreamingStdOutCallbackHandler
from langchain_core.prompts import PromptTemplate
from langchain_core.exceptions import OutputParserException
from langchain_core.agents import AgentAction, AgentFinish

# 프로젝트 루트 및 경로 설정
project_root = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
if project_root not in sys.path:
    sys.path.insert(0, project_root)
# URL-BERT 경로 추가
urlbert_base = os.path.join(project_root, 'urlbert', 'urlbert2')
if urlbert_base not in sys.path:
    sys.path.insert(0, urlbert_base)

# 툴 로드 함수 임포트
from bot.tools.urlbert_tool import load_urlbert_tool
from bot.tools.rag_tools import load_rag_tool, build_rag_index_from_jsonl

# 1. LLM 세팅
MODEL_PATH = os.path.join(project_root, 'models', 'gguf', 'llama-3-Korean-Bllossom-8B-Q4_K_M.gguf')
if not os.path.exists(MODEL_PATH):
    raise FileNotFoundError(f"GGUF 모델을 찾을 수 없습니다: {MODEL_PATH}")

llm = LlamaCpp(
    model_path=MODEL_PATH,
    n_gpu_layers=-1,
    n_ctx=8192,
    max_tokens=256,
    temperature=0.2,
    top_p=0.9,
    callback_manager=CallbackManager([StreamingStdOutCallbackHandler()]),
    verbose=True,
)

# 2. 툴 인스턴스 생성
# URL-BERT Tool
from urlbert.urlbert2.core.model_loader import load_inference_model
urlbert_model, urlbert_tokenizer = load_inference_model()
url_tool = load_urlbert_tool(urlbert_model, urlbert_tokenizer)

# RAG Tool (인덱스 없으면 생성)
RAG_INDEX = os.path.join(project_root, 'security_faiss_index')
RAG_DATA  = os.path.join(project_root, 'data', 'rag_dataset.jsonl')
if not os.path.exists(RAG_INDEX):
    build_rag_index_from_jsonl(RAG_DATA, RAG_INDEX)
rag_tool = load_rag_tool(RAG_INDEX, llm)

# Chat Tool
def chat_fn(query: str) -> str:
    return llm.invoke(query)
chat_tool = Tool(
    name="Chat",
    func=chat_fn,
    description="일반 대화 및 간단한 정보 답변용"
)

tools = [url_tool, rag_tool, chat_tool]

# 3. 메모리
memory = ConversationBufferMemory(memory_key="chat_history")

# 4. 시스템 프롬프트 정의
system_prompt = """
<|begin_of_text|>
너는 보안 전문가이자 URL 분석가인 한국어 챗봇이야.
다음 도구를 활용하여 사용자 질문에 응답해:

1. URLBERT_ThreatAnalyzer: 사용자가 URL의 안전성/위험성을 물어볼 때만 사용.
2. SecurityDocsQA: 보안 개념 설명이나 문서 검색이 필요할 때 사용.
3. Chat: 나머지 일반 대화용.

모두 한국어로 답변하고, `Action:`과 `Action Input:` 형식은 반드시 지켜야 해.
도구 사용 후 Observation을 보고, 마지막에 자연스러운 한국어 문장으로 최종 답변을 해줘.
"""

prompt_template = PromptTemplate.from_template(
    system_prompt + "\n{chat_history}\n사용자: {input}\n{agent_scratchpad}"
)

# 5. 에이전트 초기화 (ZERO_SHOT_REACT_DESCRIPTION)
agent = initialize_agent(
    tools=tools,
    llm=llm,
    agent=AgentType.ZERO_SHOT_REACT_DESCRIPTION,
    memory=memory,
    verbose=True,
    agent_kwargs={
        "prompt": prompt_template,
        "stop": ["\nObservation:", "\nThought:", "<|eot_id|>"],
    }
)

# 6. 채팅 함수

def chat(query: str) -> str:
    try:
        return agent.run(query)
    except Exception as e:
        return f"❌ 오류 발생: {e}"

# 7. 인터랙티브 루프
if __name__ == "__main__":
    print("--- 챗봇 시작 (종료하려면 '종료' 입력) ---")
    while True:
        text = input("You ▶ ").strip()
        if not text:
            continue
        if text.lower() in {"종료", "exit", "quit"}:
            print("챗봇을 종료합니다.")
            break
        response = chat(text)
        print("Bot ▶", response)
