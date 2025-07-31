# bot/bot_main.py
import os
import sys
import re
import json

# LangChain 관련 임포트
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
from bot.tools.rag_tools import load_rag_tool, build_rag_index_from_jsonl # rag_tools.py의 변경 반영

# 1. LLM 세팅
MODEL_PATH = os.path.join(project_root, 'models', 'gguf', 'llama-3-Korean-Bllossom-8B-Q4_K_M.gguf')

print(f"DEBUG: project_root = {project_root}")
print(f"DEBUG: Expected MODEL_PATH = {MODEL_PATH}")

if not os.path.exists(MODEL_PATH):
    raise FileNotFoundError(
        f"GGUF 모델을 찾을 수 없습니다: '{MODEL_PATH}'. "
        f"프로젝트 루트 '{project_root}' 아래의 'models/gguf/' 폴더에 모델 파일을 넣어주세요."
    )

print(f"Bllossom-8B GGUF 모델 로드 중: {MODEL_PATH}")
llm = LlamaCpp(
    model_path=MODEL_PATH,
    n_gpu_layers=-1,
    n_ctx=8192,
    max_tokens=512,  # 생성 토큰 수 다시 512로 조정
    temperature=0.01, # 답변의 일관성을 위해 temperature를 더 낮춤
    top_p=0.9,
    callback_manager=CallbackManager([StreamingStdOutCallbackHandler()]),
    verbose=True,
)
print("LLM 로드 완료.")

# 2. 툴 인스턴스 생성
print("툴 로드 중...")
# URL-BERT Tool
try:
    from urlbert.urlbert2.core.model_loader import load_inference_model
    urlbert_model, urlbert_tokenizer = load_inference_model()
    url_tool = load_urlbert_tool(urlbert_model, urlbert_tokenizer)
    print("URLBERT_ThreatAnalyzer 툴 로드 완료.")
except ImportError as e:
    print(f"⚠️ URLBERT_ThreatAnalyzer 툴 로드 실패: {e}. URL 관련 기능은 동작하지 않습니다.")
    url_tool = Tool(
        name="URLBERT_ThreatAnalyzer",
        func=lambda x: "URL 분석 툴을 로드할 수 없어 기능을 사용할 수 없습니다.",
        description="URL의 안전성/위험성 분석 기능 (현재 비활성화됨)."
    )
except Exception as e:
    print(f"⚠️ URLBERT_ThreatAnalyzer 모델 로드 중 예외 발생: {e}. URL 관련 기능은 동작하지 않습니다.")
    url_tool = Tool(
        name="URLBERT_ThreatAnalyzer",
        func=lambda x: f"URL 분석 툴 로드 중 오류 발생: {e}. 기능을 사용할 수 없습니다.",
        description="URL의 안전성/위험성 분석 기능 (현재 비활성화됨)."
    )


# RAG Tool (인덱스 없으면 생성)
RAG_INDEX_DIR = os.path.join(project_root, 'security_faiss_index')
RAG_DATA_PATH = os.path.join(project_root, 'data', 'rag_dataset.jsonl')

if not os.path.exists(RAG_INDEX_DIR):
    print(f"RAG 인덱스 '{RAG_INDEX_DIR}'를 찾을 수 없습니다. 데이터 '{RAG_DATA_PATH}'로부터 새로 생성합니다...")
    if not os.path.exists(RAG_DATA_PATH):
        raise FileNotFoundError(f"RAG 데이터셋 '{RAG_DATA_PATH}'를 찾을 수 없습니다. RAG 인덱스 생성에 실패했습니다.")
    build_rag_index_from_jsonl(RAG_DATA_PATH, RAG_INDEX_DIR)
    print("RAG 인덱스 생성 완료.")

rag_tool = load_rag_tool(RAG_INDEX_DIR, llm)
print("SecurityDocsQA 툴 로드 완료.")

# Chat 툴
def chat_fn(query: str) -> str:
    """일반적인 질문에 LLM을 사용하여 답변합니다."""
    # LLM을 직접 호출할 때도 stop 토큰을 명시하여 불필요한 생성을 막습니다.
    # Llama-3 모델은 <|eot_id|>를 종료 토큰으로 인식합니다.
    raw_response = llm.invoke(query, stop=["\nFinal Answer:", "<|eot_id|>", "\n", "\n\n", "Action:", "Thought:"])

    # 모델이 불필요하게 Action/Thought 등을 포함할 경우를 대비한 후처리 (보험성 코드)
    cleaned_response = raw_response.strip()
    cleaned_response = re.sub(r"^(Action:|Action Input:|Observation:|Thought:)", "", cleaned_response, flags=re.MULTILINE).strip()
    
    # 모델이 질문을 반복하는 경우를 대비한 후처리
    if cleaned_response.lower().startswith(query.lower()):
        cleaned_response = cleaned_response[len(query):].strip()

    # 불필요한 반복 문자열(. 등)을 제거하는 후처리
    cleaned_response = re.sub(r'\.{3,}', '.', cleaned_response).strip() # 3개 이상의 점을 하나의 점으로
    cleaned_response = re.sub(r'\s*\.{2,}\s*', '.', cleaned_response).strip() # 2개 이상의 점과 공백 제거

    return cleaned_response

chat_tool = Tool(
    name="Chat",
    func=chat_fn,
    description="일반 대화 및 간단한 정보 답변용으로 사용합니다."
)
print("Chat 툴 로드 완료.")

tools = [url_tool, rag_tool, chat_tool]
print("모든 툴 로드 완료.")

# 3. 메모리
memory = ConversationBufferMemory(
    memory_key="chat_history",
    return_messages=True
)
print("메모리 초기화 완료.")

# 4. **개선된 시스템 프롬프트 정의 (Llama-3/ChatML 형식 적용)**
system_prompt_for_agent = """<|begin_of_text|><|start_header_id|>system<|end_header_id|>
너는 보안 전문가이자 URL 분석가인 한국어 챗봇이야.
사용자의 질문에 따라 다음 도구 중 가장 적절한 것을 선택하여 답변해야 해.
도구 선택에 대한 너의 'Thought'는 명확하고 구체적이어야 해.

사용할 수 있는 도구는 다음과 같아:
- **URLBERT_ThreatAnalyzer**: 사용자가 특정 URL의 안전성/위험성 분석, 피싱 여부 등을 물어볼 때 사용해. 질문에 URL(예: http://, https://, www.google.com, .com, .net, .io 등)이 명확히 포함되어 있거나, 'URL', '도메인', '분석', '위험', '안전'과 같은 키워드가 있을 때 이 도구를 우선적으로 고려해야 해. **툴을 호출할 때는 'Action: URLBERT_ThreatAnalyzer' 라고만 쓰고, 'Action Input:'에 분석할 URL을 입력해줘.**
- **SecurityDocsQA**: 피싱, SSL, 랜섬웨어, 포렌식, 인시던트, 취약점 등 보안 관련 개념 설명이나 문서 검색이 필요할 때 사용해. 보안 관련 용어나 질문이 있을 때 이 도구를 사용해. **모든 답변은 한국어로 해줘.**
- **Chat**: 위에 명시된 두 가지 도구로 처리하기 어려운 일반 대화나 간단한 질문에 사용해. 예를 들어, '안녕', '오늘 날씨는?', '넌 누구니?'와 같은 질문에 답변할 때 사용해.

모든 답변은 친절하고 이해하기 쉬운 한국어 대화체로 해줘.
'Action:'과 'Action Input:' 형식은 반드시 지켜야 해.
도구 사용 후 Observation을 보고, 마지막에 **오직 하나의 'Final Answer:' 접두사만을 사용하여 최종 답변 내용을 한국어로 간결하게 작성해줘.** **Final Answer가 완성되면, 더 이상 추가적인 설명을 하지 말고 즉시 종료해.**
**'Final Answer:' 뒤에는 최종 답변 내용만 와야 하며, 추가적인 'Thought:'이나 'Final Answer:' 접두사의 반복 없이 즉시 종료해야 해.**
<|eot_id|>"""

final_agent_prompt = PromptTemplate.from_template(
    system_prompt_for_agent + "<|start_header_id|>user<|end_header_id|>\n{input}<|eot_id|><|start_header_id|>assistant<|end_header_id|>\n{agent_scratchpad}"
)

print("에이전트 프롬프트 템플릿 설정 완료.")

# 5. 에이전트 초기화 (ZERO_SHOT_REACT_DESCRIPTION)
agent_executor = initialize_agent(
    tools=tools,
    llm=llm,
    agent=AgentType.ZERO_SHOT_REACT_DESCRIPTION,
    memory=memory,
    verbose=True,
    agent_kwargs={
        "prompt": final_agent_prompt,
        # LLM이 'Final Answer:'를 생성하면 즉시 중단되도록 stop 시퀀스에 추가.
        # `<|eot_id|>`가 Llama-3의 종료 토큰임을 명시적으로 강조
        "stop": ["\nFinal Answer:", "<|eot_id|>", "\nObservation:", "\nThought:", "\nUser:", "Action: URLBERT_ThreatAnalyzer(url: str)"], # 잘못된 툴 호출 패턴도 stop에 추가
    },
    handle_parsing_errors=True
)
print("에이전트 초기화 완료.")

# 6. 챗봇의 핵심 로직
def chat(query: str) -> str:
    try:
        result = agent_executor.invoke({"input": query})
        final_output = result.get('output', "답변을 생성할 수 없습니다.")
        
        # 최종 출력에서도 불필요한 후행 문자열이나 반복을 제거
        final_output = final_output.strip()
        final_output = re.sub(r'\.{3,}', '.', final_output).strip()
        final_output = re.sub(r'\s*\.{2,}\s*', '.', final_output).strip()

        # Final Answer 뒤에 잘못된 에러 메시지가 붙는 경우 제거 (URLBERT 오류 후처리)
        if "is not a valid tool, try one of [" in final_output:
            final_output = final_output.split("is not a valid tool, try one of [")[0].strip()
            final_output = final_output.replace("The final answer to the original input question.", "").strip()
            final_output = final_output.replace("It seems that you need to use one of the available tools", "").strip()
            final_output = final_output.replace("- Final Answer:", "").strip() # 중복된 Final Answer 제거

        return final_output
    except OutputParserException as e:
        print(f"❌ 에이전트 출력 파싱 오류: {e}")
        return "죄송합니다. 답변을 처리하는 데 문제가 발생했습니다. 다시 시도해 주세요. (출력 형식 오류)"
    except Exception as e:
        print(f"❌ 오류 발생: {e}")
        return f"죄송합니다. 알 수 없는 오류가 발생했습니다: {e}"

# 7. 인터랙티브 루프
if __name__ == "__main__":
    print("--- 챗봇 시작 (종료하려면 '종료' 입력) ---")
    print("예시 질문:")
    print("- URL 분석: 'https://malicious.com' 분석해 줘")
    print("- RAG 질문: '피싱이 뭐야?'")
    print("- 일반 대화: '안녕?'")
    while True:
        text = input("You ▶ ").strip()
        if not text:
            continue
        if text.lower() in {"종료", "exit", "quit", "q"}:
            print("챗봇을 종료합니다.")
            break
        
        response = chat(text)
        print("Bot ▶", response)