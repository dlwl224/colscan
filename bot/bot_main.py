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
from langchain_core.prompts import PromptTemplate 

project_root = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))


if project_root not in sys.path:
    sys.path.insert(0, project_root)

# URL-BERT 모듈 경로를 sys.path에 추가하여 임포트 가능하게 함
urlbert_base_path = os.path.join(project_root, 'urlbert', 'urlbert2')
if urlbert_base_path not in sys.path:
    sys.path.insert(0, urlbert_base_path)

# 1) URL-BERT 분석 툴 임포트
from bot.tools.urlbert_tool import load_urlbert_tool
# 2) RAG 보안 문서 검색 툴 (인덱스 생성 함수 포함) 임포트
from bot.tools.rag_tools import load_rag_tool, build_rag_index_from_jsonl

# 일반 대화를 처리할 LLM 호출 함수
def chat_tool_fn(query: str) -> str:
    return llm(query)

# ───────────────────────────────────────────────────────────────────────────────

# GGUF 모델 경로 (project_root를 기준으로 설정)
MODEL_GGUF_PATH = os.path.join(project_root, "models", "gguf", "llama-3-Korean-Bllossom-8B-Q4_K_M.gguf")

if not os.path.exists(MODEL_GGUF_PATH):
    print(f"❌ 오류: GGUF 모델 파일이 다음 경로에 없습니다: {MODEL_GGUF_PATH}")
    print("모델 파일을 로컬 'colscan/models/gguf/' 폴더에 올바르게 배치했는지 확인해주세요.")
    sys.exit(1)

print(f"Llama GGUF 모델 로드 시작: {MODEL_GGUF_PATH}")
llm = LlamaCpp(
    model_path=MODEL_GGUF_PATH,
    n_gpu_layers=-1, # -1은 가능한 모든 레이어를 GPU에 로드 (GPU 메모리가 허용하는 한)
    n_ctx=8192,      # Llama-3의 최대 컨텍스트 길이 (모델이 지원하는 최대값)
    max_tokens=1024, # 생성할 최대 토큰 수
    temperature=0.7, # 창의성 조절 (0.0에 가까울수록 보수적, 1.0에 가까울수록 창의적)
    top_p=0.9,       # 상위 p 확률 분포 내에서 샘플링
    callback_manager=CallbackManager([StreamingStdOutCallbackHandler()]),
    verbose=True, # 자세한 로그 출력 (에이전트의 사고 과정 확인에 유용)
)
print("✅ Llama GGUF 모델 로드 및 LangChain LLM 객체 생성 완료.")

# 툴 로드
from urlbert.urlbert2.core.model_loader import load_inference_model as load_urlbert_inference_model
try:
    urlbert_model, urlbert_tokenizer = load_urlbert_inference_model()
    url_tool = load_urlbert_tool(urlbert_model, urlbert_tokenizer)
    print("✅ URL-BERT Tool 로드 완료.")
except Exception as e:
    print(f"❌ URL-BERT Tool 로드 중 오류 발생: {e}")
    print("urlbert 모듈 경로 설정 및 종속성 (DB_Manager 등)을 확인해주세요.")
    url_tool = None # 오류 발생 시 툴을 None으로 설정하여 에이전트에서 제외될 수 있도록 함 (선택 사항)


# RAG 인덱스 경로 및 생성 로직
RAG_INDEX_PATH = os.path.join(project_root, "security_faiss_index")
RAG_DATA_JSONL_PATH = os.path.join(project_root, "data", "rag_dataset.jsonl") # project_root를 기준으로 경로 설정

if not os.path.exists(RAG_INDEX_PATH):
    print(f"RAG 인덱스 폴더가 다음 경로에 없습니다: {RAG_INDEX_PATH}")
    print("RAG 인덱스 생성을 시도합니다...")
    if os.path.exists(RAG_DATA_JSONL_PATH):
        try:
            print(f"RAG 인덱스 생성 시작 (JSONL 파일: {RAG_DATA_JSONL_PATH})...")
            # build_rag_index_from_jsonl 함수는 rag_tools.py에서 정의된 기본 임베딩 모델 사용.
            build_rag_index_from_jsonl(jsonl_path=RAG_DATA_JSONL_PATH, index_path=RAG_INDEX_PATH)
            print("✅ RAG 인덱스 생성 완료.")
        except Exception as e:
            print(f"❌ RAG 인덱스 생성 중 오류 발생: {e}")
            print("FAISS 인덱스 생성에 필요한 데이터나 라이브러리 문제를 확인해주세요.")
            sys.exit(1)
    else:
        print(f"❌ 오류: RAG 데이터 JSONL 파일이 없습니다: {RAG_DATA_JSONL_PATH}")
        print("FAISS 인덱스를 생성할 수 없어 RAG 기능이 작동하지 않습니다.")
        sys.exit(1)

try:
    rag_tool = load_rag_tool(RAG_INDEX_PATH, llm)
    print("✅ RAG Tool 로드 완료.")
except Exception as e:
    print(f"❌ RAG Tool 로드 중 오류 발생: {e}")
    print("RAG 인덱스 파일이 손상되었거나 임베딩 모델 로드에 문제가 있을 수 있습니다.")
    rag_tool = None # 오류 발생 시 툴을 None으로 설정

chat_tool = Tool(
    name="Chat",
    func=chat_tool_fn,
    description="일반 대화 및 추가 정보 검색에 사용되는 툴입니다. URL 분석이나 보안 문서 검색이 필요 없을 때 LLM 자체 답변용."
)

# 유효한 툴만 리스트에 추가 (로드 실패한 툴은 제외)
tools = [tool for tool in [url_tool, rag_tool, chat_tool] if tool is not None]

# 1) 메모리(대화 기록)
memory = ConversationBufferMemory(memory_key="chat_history")

# ───────────────────────────────────────────────────────────────────────────────
# ⭐ LLM이 툴을 잘 인식하고 원하는 대로 말하도록 하는 핵심 부분 (프롬프트 템플릿) ⭐
# ───────────────────────────────────────────────────────────────────────────────
# Llama-3 모델의 Instructional Format을 고려한 시스템 프롬프트.
# 모델에게 명확한 역할과 툴 사용 규칙을 제시합니다.
# Llama-3은 <|begin_of_text|> ... <|eot_id|> 형식을 따릅니다.
# 에이전트는 내부적으로 이를 처리하므로, 여기서는 {input}과 {agent_scratchpad}만 넣어줍니다.

system_prompt = """
<|begin_of_text|>
너는 사용자에게 보안 관련 질문에 답변하고, URL의 위험성을 분석해주는 친절한 인공지능 챗봇이야.
너에게는 다음 세 가지 도구가 주어져:
1. URLAnalyzer: 사용자가 URL의 위험성을 분석해달라고 요청할 때 사용해. 특정 URL 주소가 포함된 질문에 사용해야 해. `URLAnalyzer(url: str)` 형식으로 호출해.
2. SecurityDocsQA: 보안 개념, 정의, 공격 유형, 예방 및 대응 방법 등 보안 관련 지식이나 문서 검색이 필요한 질문에 사용해. `SecurityDocsQA(q: str)` 형식으로 호출해.
3. Chat: 위 두 도구에 해당하지 않는 일반적인 대화, 인사, 잡담, 또는 간단한 정보 질문에 답변할 때 사용해. `Chat(query: str)` 형식으로 호출해.

사용자의 질문을 주의 깊게 분석하고, 가장 적합한 도구를 선택해야 해.
도구를 사용하기 전에 어떤 도구를 왜 선택했는지 'Thought:'에 명확히 설명해줘.
도구를 사용한 후에는 'Action:'과 'Action Input:'을 명확히 제시해줘.
도구의 결과를 'Observation:'에서 확인하고, 이를 바탕으로 최종 답변을 'Final Answer:'에 제공해줘.

대화 기록:
{chat_history}

사용자 질문: {input}
{agent_scratchpad}
<|eot_id|>
"""

# PromptTemplate 생성
prompt_template = PromptTemplate.from_template(system_prompt)

# Agent 초기화: zero-shot-react-description
# agent_kwargs에 커스텀 프롬프트 템플릿과 stop_sequence를 지정합니다.
agent = initialize_agent(
    tools=tools,
    llm=llm,
    agent="zero-shot-react-description", # ReAct 에이전트 타입 사용
    verbose=True, # 에이전트의 내부 사고 과정을 상세하게 출력
    memory=memory, # 대화 기록 유지를 위해 메모리 객체 전달
    handle_parsing_errors=True, # 파싱 오류 발생 시 에이전트가 더 잘 처리하도록
    agent_kwargs={
        "prompt": prompt_template,
        # LLM이 특정 문자열을 생성하면 답변 생성을 멈추도록 지시합니다.
        # 이것이 없으면 LLM이 툴 호출 패턴을 계속 반복할 수 있습니다.
        "stop_sequence": ["Observation:", "Thought:"],
    }
)
print("✅ LangChain Agent 초기화 완료.")

# 3) 인터랙티브 채팅 함수
def chat(query: str) -> str:
    """
    Agent가 내부적으로:
    - URL 패턴 감지 → URLAnalyzer 호출
    - 보안 개념 질문 감지 → SecurityDocsQA 호출
    - 그 외 → Chat 툴 (LLM 직접 응답)
    """
    try:
        # 에이전트 실행 시 invoke 대신 run 사용 (이전 버전 호환성)
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