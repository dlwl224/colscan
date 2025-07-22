# bot/bot_main.py

import re
import os
import sys
import torch # LlamaCpp에서 GPU 사용을 위해 필요할 수 있음

from langchain.agents import initialize_agent, Tool, AgentOutputParser
from langchain.memory import ConversationBufferMemory
from langchain_community.llms import LlamaCpp
from langchain.callbacks.manager import CallbackManager
from langchain.callbacks.streaming_stdout import StreamingStdOutCallbackHandler
from langchain_core.prompts import PromptTemplate 
from langchain_core.agents import AgentAction, AgentFinish
from langchain_core.exceptions import OutputParserException

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
    # Chat 툴은 단순 LLM 호출이므로, 여기서 바로 응답을 생성하도록 합니다.
    # LLM이 직접 Final Answer를 생성하도록 유도하기 위해 짧고 명확한 응답을 기대합니다.
    # 여기서는 LLM이 직접 대답하므로, LLM의 raw 출력을 반환합니다.
    return llm.invoke(query)

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
    max_tokens=128,  # 256 -> 128으로 추가 조정 (반복성 극단적으로 감소 시도)
    temperature=0.0, # 0.7 -> 0.0으로 변경 (모델의 '무작위성'을 최소화하여 ReAct 패턴을 잘 따르도록 함)
    top_p=0.9,       # 상위 p 확률 분포 내에서 샘플링
    callback_manager=CallbackManager([StreamingStdOutCallbackHandler()]),
    verbose=True,    # 자세한 로그 출력 (에이전트의 사고 과정 확인에 유용)
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
    url_tool = None 


# RAG 인덱스 경로 및 생성 로직
RAG_INDEX_PATH = os.path.join(project_root, "security_faiss_index")
RAG_DATA_JSONL_PATH = os.path.join(project_root, "data", "rag_dataset.jsonl") # project_root를 기준으로 경로 설정

if not os.path.exists(RAG_INDEX_PATH):
    print(f"RAG 인덱스 폴더가 다음 경로에 없습니다: {RAG_INDEX_PATH}")
    print("RAG 인덱스 생성을 시도합니다...")
    if os.path.exists(RAG_DATA_JSONL_PATH):
        try:
            print(f"RAG 인덱스 생성 시작 (JSONL 파일: {RAG_DATA_JSONL_PATH})...")
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
    rag_tool = None 

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
system_prompt = """
<|begin_of_text|>
너는 사용자에게 보안 관련 질문에 답변하고, URL의 위험성을 분석해주는 친절하고 정확한 인공지능 챗봇이야.
다음은 네가 사용할 수 있는 도구 목록이야. 각 도구의 이름과 설명, 그리고 **정확한 사용 형식**을 숙지해야 해.

1.  **URLAnalyzer**: 사용자가 URL의 위험성을 분석해달라고 요청할 때 사용해. 특정 URL 주소가 포함된 질문에 사용해야 해.
    **사용 형식 (정확히 이 형식대로만 출력):**
    Thought: <URL 분석이 필요하다고 판단한 이유.>
    Action: URLAnalyzer
    Action Input: <분석할 URL 주소>

2.  **SecurityDocsQA**: 보안 개념, 정의, 공격 유형, 예방 및 대응 방법 등 보안 관련 지식이나 문서 검색이 필요한 질문에 사용해.
    **사용 형식 (정확히 이 형식대로만 출력):**
    Thought: <보안 문서 검색이 필요하다고 판단한 이유.>
    Action: SecurityDocsQA
    Action Input: <검색할 질문>

3.  **Chat**: 위에 명시된 두 도구(URLAnalyzer, SecurityDocsQA)에 해당하지 않는 일반적인 대화, 인사, 잡담, 간단한 정보 질문에 답변할 때 사용해.
    **사용 형식 (정확히 이 형식대로만 출력):**
    Thought: <일반 대화라고 판단한 이유.>
    Action: Chat
    Action Input: <사용자 질문>

너는 사용자의 질문을 가장 주의 깊게 분석하고, 위에 제시된 도구 사용 형식에 **정확히 일치하도록** `Action:`과 `Action Input:`을 출력해야 해.
도구를 사용한 후에는 다음 형식으로 결과를 보고해야 해:
Observation: <도구 실행 결과>
그리고 마지막으로, 사용자의 **원래 질문의 의도**에 맞춰 친절하고 완전한 한국어 문장으로 최종 답변을 한 번만 제공해.

--- 중요한 규칙 ---
- 'Action:' 뒤에는 오직 도구 이름만 와야 해. 절대 괄호나 다른 문자열(예: 'Use', '(url: str)')을 붙이지 마.
- 'Action Input:' 뒤에는 도구에 전달할 순수한 입력 값만 와야 해.
- 'Final Answer:'는 사용자가 이해하기 쉬운 완전한 한국어 문장으로 한 번만 제공하고, 절대로 반복하지 마. 다른 언어를 섞지 말고 한국어로만 답해.
- 만약 도구 사용 중 오류가 발생하면, 즉시 사용자에게 '현재 도구 사용에 문제가 있습니다. 다른 방법으로 시도하거나 잠시 후 다시 시도해주세요.'와 같이 명확하게 안내하고 최종 답변을 마무리해. 불필요한 추론을 반복하지 마.

대화 기록:
{chat_history}

사용자 질문: {input}
{agent_scratchpad}
<|eot_id|>
"""

# PromptTemplate 생성
prompt_template = PromptTemplate.from_template(system_prompt)


# ✨ Custom Output Parser 정의 (이 부분이 핵심입니다!)
class CustomReActOutputParser(AgentOutputParser):
    def parse(self, text: str) -> AgentAction | AgentFinish:
        # Final Answer 패턴 매칭을 가장 먼저 시도.
        # 여러 'Final Answer:'가 있을 경우 첫 번째 유효한 것만 취함.
        final_answer_match = re.search(r"Final Answer:\s*(.*?)(?=(Final Answer:|$))", text, re.DOTALL)
        if final_answer_match:
            return AgentFinish(
                return_values={"output": final_answer_match.group(1).strip()},
                log=text,
            )

        # Action: ToolName(input) 패턴 처리
        # Llama-3이 선호하는 함수 호출 형태.
        action_function_call_match = re.search(r"Action:\s*(\w+)\((.*?)\)", text, re.DOTALL)
        if action_function_call_match:
            tool_name = action_function_call_match.group(1).strip()
            tool_input = action_function_call_match.group(2).strip()
            return AgentAction(tool=tool_name, tool_input=tool_input, log=text)
        
        # Action: ToolName \n Action Input: input 패턴 처리 (LangChain 표준)
        action_name_match = re.search(r"Action:\s*(\w+)", text)
        action_input_match = re.search(r"Action Input:\s*(.*)", text, re.DOTALL)

        if action_name_match and action_input_match:
            tool_name = action_name_match.group(1).strip()
            tool_input = action_input_match.group(1).strip()
            return AgentAction(tool=tool_name, tool_input=tool_input, log=text)

        # 'Action: Use ToolName' 또는 'Action: Try to use another tool' 같은 잘못된 패턴 처리
        # LLM이 'Use', 'Try' 같은 불필요한 단어를 붙이는 경우를 최대한 포괄적으로 처리.
        # 여기서 중요한 것은 `tool_name`만 정확히 뽑아내고, 나머지는 버려야 합니다.
        misparsed_action_match = re.search(r"Action:\s*(?:Use\s*|Try\s*to\s*use\s*another\s*tool\s*from\s*the\s*list\.|Try\s*to\s*use\s*another\s*tool\.|Try\s*|Use\s*)?(\w+)(?:\s*\(.*?\))?(?:\s*->\s*str)?", text, re.DOTALL)
        if misparsed_action_match:
            tool_name_candidate = misparsed_action_match.group(1).strip()
            # 유효한 툴 이름인지 확인
            valid_tool_names = [tool.name for tool in tools]
            if tool_name_candidate in valid_tool_names:
                # 유효한 툴 이름이라면, 해당 툴의 Action Input을 찾기 시도
                # 가장 가까운 Action Input을 찾도록 수정
                input_start_index = text.find(misparsed_action_match.group(0)) # Action 시작 지점
                next_action_input_match = re.search(r"Action Input:\s*(.*)", text[input_start_index:], re.DOTALL)
                
                if next_action_input_match:
                    tool_input = next_action_input_match.group(1).strip()
                    return AgentAction(tool=tool_name_candidate, tool_input=tool_input, log=text)
                else:
                    # Action Input이 없어도 일단 툴 액션으로 간주 (오류를 발생시키기보다 툴 호출 시도)
                    print(f"DEBUG: Found '{tool_name_candidate}' but no explicit 'Action Input:' in segment.")
                    # 최악의 경우, 프롬프트에서 'Action Input:' 줄이 없더라도 Action과 Tool Input이 붙어있을 수 있으므로
                    # 전체 텍스트에서 'Action Input:' 부분을 찾지 못했다면, Action 뒤의 첫 줄을 Input으로 가정하는 것도 고려
                    # 하지만 이는 매우 위험하므로, 일단은 None으로 처리하거나 예외 발생
                    raise OutputParserException(f"Could not parse Action Input after '{tool_name_candidate}' for misparsed action: `{text}`")
            
        # 아무 패턴도 매칭되지 않을 경우 파싱 오류
        # 모델이 반복적인 이상한 출력을 할 때 여기에 걸리도록 합니다.
        raise OutputParserException(f"Could not parse LLM output: `{text}`")

# ✨ 커스텀 파서 인스턴스 생성
custom_parser = CustomReActOutputParser()


# Agent 초기화: zero-shot-react-description
agent = initialize_agent(
    tools=tools,
    llm=llm,
    agent="zero-shot-react-description", # ReAct 에이전트 타입 사용
    verbose=True, # 에이전트의 내부 사고 과정을 상세하게 출력
    memory=memory, # 대화 기록 유지를 위해 메모리 객체 전달
    handle_parsing_errors=True, # 파싱 오류 발생 시 에이전트가 더 잘 처리하도록
    agent_kwargs={
        "prompt": prompt_template,
        # Llama-3의 특성을 고려하여 stop 시퀀스를 더 강력하게 설정.
        # 특히 \nFinal Answer: 를 추가하여 Final Answer를 생성하면 즉시 멈추도록 유도
        "stop": ["\nObservation:", "\nThought:", "\nFinal Answer:", "<|eot_id|>"], 
        "output_parser": custom_parser, # ✨ 커스텀 파서 적용
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
        response_dict = agent.invoke({"input": query})
        raw_output = response_dict.get('output', "응답을 생성하는 데 문제가 발생했습니다.")
        
        # 'Final Answer:'로 시작하는 경우, 접두어를 제거하고 한 번만 반환
        if raw_output.strip().startswith("Final Answer:"):
            return raw_output.replace("Final Answer:", "").strip()
        
        # 그 외의 경우 (예: Chat 툴의 직접 출력)
        return raw_output

    except OutputParserException as e:
        # LLM이 파싱할 수 없는 출력을 생성했을 때
        print(f"⚠️ 파싱 오류 발생: {e}")
        return "죄송합니다. 현재 챗봇이 답변을 생성하는 데 문제가 발생했습니다. 질문을 명확하게 해주시면 감사하겠습니다."
    except Exception as e:
        # 기타 예외 처리
        return f"❌ 챗봇 처리 중 예측하지 못한 오류 발생: {e}"

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