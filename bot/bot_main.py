import os
import sys
import re
import json


from langchain.agents import initialize_agent, AgentType, Tool

#from langchain.agents import initialize_agent, Tool, AgentOutputParser

from langchain.memory import ConversationBufferMemory
from langchain_community.llms import LlamaCpp
from langchain.callbacks.manager import CallbackManager
from langchain.callbacks.streaming_stdout import StreamingStdOutCallbackHandler

from langchain_core.prompts import PromptTemplate

# from langchain_core.prompts import PromptTemplate 
# from langchain_core.agents import AgentAction, AgentFinish # ✨ 추가
# from langchain_core.exceptions import OutputParserException # ✨ 추가


# 프로젝트 루트 및 경로 설정
project_root = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
if project_root not in sys.path:
    sys.path.insert(0, project_root)
# URL-BERT 경로 추가
urlbert_base = os.path.join(project_root, 'urlbert', 'urlbert2')
if urlbert_base not in sys.path:
    sys.path.insert(0, urlbert_base)


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

# # 일반 대화를 처리할 LLM 호출 함수
# def chat_tool_fn(query: str) -> str:
#     return llm.invoke(query)

# # ───────────────────────────────────────────────────────────────────────────────

# # GGUF 모델 경로 (project_root를 기준으로 설정)
# MODEL_GGUF_PATH = os.path.join(project_root, "models", "gguf", "llama-3-Korean-Bllossom-8B-Q4_K_M.gguf")

# if not os.path.exists(MODEL_GGUF_PATH):
#     print(f"❌ 오류: GGUF 모델 파일이 다음 경로에 없습니다: {MODEL_GGUF_PATH}")
#     print("모델 파일을 로컬 'colscan/models/gguf/' 폴더에 올바르게 배치했는지 확인해주세요.")
#     sys.exit(1)

# print(f"Llama GGUF 모델 로드 시작: {MODEL_GGUF_PATH}")
# llm = LlamaCpp(
#     model_path=MODEL_GGUF_PATH,
#     n_gpu_layers=-1, # -1은 가능한 모든 레이어를 GPU에 로드 (GPU 메모리가 허용하는 한)
#     n_ctx=8192,      # Llama-3의 최대 컨텍스트 길이 (모델이 지원하는 최대값)
#     max_tokens=512,  # 1024 -> 512 (출력 반복 문제 해결을 위해 일시적으로 줄여봄)
#     temperature=0.0, # 0.7 -> 0.0으로 변경 (모델의 '무작위성'을 최소화하여 ReAct 패턴을 잘 따르도록 함)
#     top_p=0.9,       # 상위 p 확률 분포 내에서 샘플링
#     callback_manager=CallbackManager([StreamingStdOutCallbackHandler()]),
#     verbose=True,    # 자세한 로그 출력 (에이전트의 사고 과정 확인에 유용)
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

    # print(f"❌ URL-BERT Tool 로드 중 오류 발생: {e}")
    # print("urlbert 모듈 경로 설정 및 종속성 (DB_Manager 등)을 확인해주세요.")
    # url_tool = None 

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

# RAG 인덱스 경로 및 생성 로직
# RAG_INDEX_PATH = os.path.join(project_root, "security_faiss_index")
# RAG_DATA_JSONL_PATH = os.path.join(project_root, "data", "rag_dataset.jsonl") # project_root를 기준으로 경로 설정

# if not os.path.exists(RAG_INDEX_PATH):
#     print(f"RAG 인덱스 폴더가 다음 경로에 없습니다: {RAG_INDEX_PATH}")
#     print("RAG 인덱스 생성을 시도합니다...")
#     if os.path.exists(RAG_DATA_JSONL_PATH):
#         try:
#             print(f"RAG 인덱스 생성 시작 (JSONL 파일: {RAG_DATA_JSONL_PATH})...")
#             build_rag_index_from_jsonl(jsonl_path=RAG_DATA_JSONL_PATH, index_path=RAG_INDEX_PATH)
#             print("✅ RAG 인덱스 생성 완료.")
#         except Exception as e:
#             print(f"❌ RAG 인덱스 생성 중 오류 발생: {e}")
#             print("FAISS 인덱스 생성에 필요한 데이터나 라이브러리 문제를 확인해주세요.")
#             sys.exit(1)
#     else:
#         print(f"❌ 오류: RAG 데이터 JSONL 파일이 없습니다: {RAG_DATA_JSONL_PATH}")
#         print("FAISS 인덱스를 생성할 수 없어 RAG 기능이 작동하지 않습니다.")
#         sys.exit(1)

# try:
#     rag_tool = load_rag_tool(RAG_INDEX_PATH, llm)
#     print("✅ RAG Tool 로드 완료.")
# except Exception as e:
#     print(f"❌ RAG Tool 로드 중 오류 발생: {e}")
#     print("RAG 인덱스 파일이 손상되었거나 임베딩 모델 로드에 문제가 있을 수 있습니다.")
#     rag_tool = None 

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
- 피싱, 큐싱, SSL, 도메인 등 보안 개념 질문이면 → Action: SecurityDocsQA
- 그 외 일반 대화나 일상 질문이면 → Action: Chat


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

# system_prompt = """
# <|begin_of_text|>
# 너는 사용자에게 보안 관련 질문에 답변하고, URL의 위험성을 분석해주는 친절한 인공지능 챗봇이야.
# 너에게는 다음 세 가지 도구가 주어져:
# 1. URLAnalyzer: 사용자가 URL의 위험성을 분석해달라고 요청할 때 사용해. 특정 URL 주소가 포함된 질문에 사용해야 해.
#    사용 형식:
#    Thought: URL 분석이 필요하다고 판단한 이유.
#    Action: URLAnalyzer
#    Action Input: <분석할 URL 주소>
# 2. SecurityDocsQA: 보안 개념, 정의, 공격 유형, 예방 및 대응 방법 등 보안 관련 지식이나 문서 검색이 필요한 질문에 사용해.
#    사용 형식:
#    Thought: 보안 문서 검색이 필요하다고 판단한 이유.
#    Action: SecurityDocsQA
#    Action Input: <검색할 질문>
# 3. Chat: 위 두 도구에 해당하지 않는 일반적인 대화, 인사, 잡담, 또는 간단한 정보 질문에 답변할 때 사용해.
#    사용 형식:
#    Thought: 일반 대화라고 판단한 이유.
#    Action: Chat
#    Action Input: <사용자 질문>

# 사용자의 질문을 주의 깊게 분석하고, 가장 적합한 도구를 선택해야 해.
# 도구를 사용한 후에는 다음 형식으로 출력해야 해:
# Thought: <생각 과정>
# Action: <선택한 도구 이름>
# Action Input: <도구에 전달할 정확한 입력 값>
# Observation: <도구 실행 결과>
# Final Answer: <최종 답변>

# 대화 기록:
# {chat_history}

# 사용자 질문: {input}
# {agent_scratchpad}
# <|eot_id|>
# """

# # PromptTemplate 생성
# prompt_template = PromptTemplate.from_template(system_prompt)


# # ✨ Custom Output Parser 정의 (이 부분이 핵심입니다!)
# class CustomReActOutputParser(AgentOutputParser):
#     def parse(self, text: str) -> AgentAction | AgentFinish:
#         # Final Answer 패턴 매칭을 먼저 시도
#         final_answer_match = re.search(r"Final Answer:\s*(.*)", text, re.DOTALL)
#         if final_answer_match:
#             return AgentFinish(
#                 return_values={"output": final_answer_match.group(1).strip()},
#                 log=text,
#             )

#         # Action 패턴 매칭 (LLM이 'Action: ToolName(input)' 형태로 출력하는 것을 처리)
#         # 예: Action: URLAnalyzer(https://toss.im/)
#         action_match = re.search(r"Action:\s*(\w+)\((.*?)\)", text, re.DOTALL)
#         if action_match:
#             tool_name = action_match.group(1)
#             tool_input = action_match.group(2).strip()
#             return AgentAction(tool=tool_name, tool_input=tool_input, log=text)
        
#         # Action 패턴 매칭 (정규적인 'Action: ToolName\nAction Input: input' 형태도 처리)
#         # 예: Action: URLAnalyzer\nAction Input: https://toss.im/
#         action_name_match = re.search(r"Action:\s*(\w+)", text)
#         action_input_match = re.search(r"Action Input:\s*(.*)", text, re.DOTALL)

#         if action_name_match and action_input_match:
#             tool_name = action_name_match.group(1).strip()
#             tool_input = action_input_match.group(1).strip()
#             return AgentAction(tool=tool_name, tool_input=tool_input, log=text)

#         # 어떤 패턴도 매칭되지 않을 경우 파싱 오류
#         raise OutputParserException(f"Could not parse LLM output: `{text}`")

# # ✨ 커스텀 파서 인스턴스 생성
# custom_parser = CustomReActOutputParser()


# # Agent 초기화: zero-shot-react-description
# # agent_kwargs에 커스텀 프롬프트 템플릿과 stop_sequence를 지정합니다.
# agent = initialize_agent(

    tools=tools,
    llm=llm,
    agent=AgentType.ZERO_SHOT_REACT_DESCRIPTION,
    memory=memory,
    verbose=True,
    agent_kwargs={

        "prompt": final_agent_prompt,
        "stop": ["\nFinal Answer:", "<|eot_id|>"]

        # "prompt": prompt_template,
        # "stop": ["\nObservation:", "\nThought:", "\nFinal Answer:"],
        # "output_parser": custom_parser, # ✨ 커스텀 파서 적용
    }
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
        # agent.run(query) 대신 agent.invoke({"input": query}) 사용
        # invoke 호출 시 dictionary 형태로 input을 전달합니다.
        response_dict = agent.invoke({"input": query})
        # 최종 답변은 'output' 키에 저장됩니다.
        return response_dict.get('output', "응답을 생성하는 데 문제가 발생했습니다.")
    except Exception as e:
        # 오류 발생 시 사용자에게 메시지 반환
        return f"❌ 챗봇 처리 중 오류 발생: {e}"

# URL 탐지 정규식 (http/https URL 및 도메인 형태 모두 감지)
URL_PATTERN = re.compile(
    r'(https?://\S+|(?:[A-Za-z0-9-]+\.)+[A-Za-z]{2,}\S*)'
)

# 5. 대화 루프
if __name__ == '__main__':
    print("--- 챗봇 시작 (종료: '종료') ---")
    while True:
        text = input("You ▶ ").strip()
        if text.lower() in {"종료","exit"}:
            break

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
