import os
import sys
import re
import json

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

# URL 탐지 정규식 (http/https URL 및 도메인 형태 모두 감지)
URL_PATTERN = re.compile(
    r'(https?://\S+|(?:[A-Za-z0-9-]+\.)+[A-Za-z]{2,}\S*)'
)

# 1. LLM 세팅
MODEL_PATH = os.path.join(project_root, 'models', 'gguf', 'llama-3-Korean-Bllossom-8B-Q4_K_M.gguf')
if not os.path.exists(MODEL_PATH):
    raise FileNotFoundError(f"GGUF 모델을 찾을 수 없습니다: {MODEL_PATH}")

llm = LlamaCpp(
    model_path=MODEL_PATH,
    n_gpu_layers=-1,
    n_ctx=8192,
    max_tokens=512,
    temperature=0.01,
    top_p=0.9,
    callback_manager=CallbackManager([StreamingStdOutCallbackHandler()]),
    verbose=True,
)

# 2. 툴 인스턴스 생성
# URL-BERT Tool
try:
    from urlbert.urlbert2.core.model_loader import load_inference_model
    urlbert_model, urlbert_tokenizer = load_inference_model()
    url_tool = load_urlbert_tool(urlbert_model, urlbert_tokenizer)
except Exception as e:
    url_tool = Tool(
        name="URLBERT_ThreatAnalyzer",
        func=lambda x: f"URL 분석 툴 로드 중 오류 발생: {e}",
        description="URL 안전성/위험성 분석"
    )

# RAG Tool (인덱스 없으면 생성)
RAG_INDEX_DIR = os.path.join(project_root, 'security_faiss_index')
RAG_DATA_PATH = os.path.join(project_root, 'data', 'rag_dataset.jsonl')
if not os.path.exists(RAG_INDEX_DIR):
    build_rag_index_from_jsonl(RAG_DATA_PATH, RAG_INDEX_DIR)
rag_tool = load_rag_tool(RAG_INDEX_DIR, llm)

# Chat 툴 (일반 대화)
def chat_fn(query: str) -> str:
    raw = llm.invoke(
        query,
        stop=["\nFinal Answer:", "<|eot_id|>", "\n", "\n\n", "Action:", "Thought:", "Observation:"]
    )
    cleaned = raw.strip()
    cleaned = re.sub(r"^(Action:|Action Input:|Observation:|Thought:)", "", cleaned, flags=re.MULTILINE).strip()
    if cleaned.lower().startswith(query.lower()):
        cleaned = cleaned[len(query):].strip()
    cleaned = re.sub(r'\.{3,}', '.', cleaned)
    cleaned = re.sub(r'\s*\.{2,}\s*', '.', cleaned)
    return cleaned
chat_tool = Tool(
    name="Chat",
    func=chat_fn,
    description="일반 대화 및 간단한 정보 답변용"
)

tools = [url_tool, rag_tool, chat_tool]
memory = ConversationBufferMemory(memory_key="chat_history", return_messages=True)

# 4. 시스템 프롬프트
system_prompt_for_agent = """
<|begin_of_text|><|start_header_id|>system<|end_header_id|>
너는 보안 전문가이자 URL 분석가인 한국어 챗봇이야.
- URL 언급(HTTP/HTTPS 포함 또는 도메인 형태)이면 즉시 URLBERT_ThreatAnalyzer 툴 호출
- 보안 개념 질문(피싱, SSL 등)이면 SecurityDocsQA 툴 호출 후 3문장 이내 한국어 요약
- 그 외 일반 대화는 Chat 툴 호출
마지막에는 'Final Answer:'만 붙이고, 즉시 종료해 추가 텍스트 금지
<|eot_id|>"""
final_agent_prompt = PromptTemplate.from_template(
    system_prompt_for_agent + "<|start_header_id|>user<|end_header_id|>\n{input}<|eot_id|><|start_header_id|>assistant<|end_header_id|>\n{agent_scratchpad}"
)

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

# 5. 대화 루프
if __name__ == '__main__':
    print("--- 챗봇 시작 (종료: '종료') ---")
    while True:
        text = input("You ▶ ").strip()
        if text.lower() in {"종료","exit"}: break

        # 문장 내 URL 감지 및 툴 직접 호출
        match = URL_PATTERN.search(text)
        if match:
            url = match.group(1)
            result = url_tool.func(url)
            print(f"Bot ▶ Final Answer: {result}")
            continue

        # 에이전트 호출
        out = agent_executor.invoke({"input": text}).get('output','')
        print("Bot ▶", out)
