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
    max_tokens=256,  # 256 유지
    temperature=0.0, # 0.0 유지 (모델의 '무작위성'을 최소화하여 ReAct 패턴을 잘 따르도록 함)
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
    print("✅ URLBERT_ThreatAnalyzer Tool 로드 완료.")
except Exception as e:
    print(f"❌ URLBERT_ThreatAnalyzer Tool 로드 중 오류 발생: {e}")
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
    print("✅ SecurityDocsQA Tool 로드 완료.")
except Exception as e:
    print(f"❌ SecurityDocsQA Tool 로드 중 오류 발생: {e}")
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
모든 답변은 한국어로 해야 해.

다음은 네가 사용할 수 있는 도구 목록이야. 각 도구의 이름과 설명을 정확히 이해하고, 사용자의 질문 내용에 따라 가장 적절한 도구를 선택해야 해.

1.  **URLBERT_ThreatAnalyzer**: 사용자가 **명시적으로 URL 주소를 제공하며 해당 URL의 안전성이나 위험성 분석을 요청할 때만** 사용해. 예를 들어, "이 URL 안전한가요? https://malicious.com" 과 같은 질문일 때 사용해. 다른 종류의 질문(예: 특정 공격 유형 설명 요청)에는 이 도구를 사용하지 마.
    **사용 형식 (정확히 이 형식대로만 출력하고, 'Action Input:' 뒤에는 오직 URL만 넣어야 해):**
    Thought: 사용자가 특정 URL의 분석을 요청했으므로 URLBERT_ThreatAnalyzer를 사용합니다.
    Action: URLBERT_ThreatAnalyzer
    Action Input: <분석할 URL 주소 (예: https://example.com)>

2.  **SecurityDocsQA**: 보안 개념, 정의, 공격 유형 (예: 피싱, 스미싱, 큐싱, 랜섬웨어), 예방 및 대응 방법 등 **특정 URL 분석과 관련 없는 일반적인 보안 지식이나 문서 검색**이 필요한 질문에 사용해.
    **사용 형식 (정확히 이 형식대로만 출력하고, 'Action Input:' 뒤에는 오직 검색할 질문만 넣어야 해):**
    Thought: 사용자가 보안 관련 지식이나 개념에 대해 질문했으므로 SecurityDocsQA를 사용합니다.
    Action: SecurityDocsQA
    Action Input: <검색할 질문 (예: 피싱이란?, 스미싱과 피싱의 차이)>

3.  **Chat**: 위에 명시된 두 도구(URLBERT_ThreatAnalyzer, SecurityDocsQA)에 **명백히 해당하지 않는 일반적인 대화, 인사, 잡담, 간단한 정보 질문**에 답변할 때 사용해. 이 도구를 사용할 때는 간결하고 자연스러운 대화 형식으로 답변해야 해.
    **사용 형식 (정확히 이 형식대로만 출력하고, 'Action Input:' 뒤에는 오직 사용자 질문만 넣어야 해):**
    Thought: 사용자가 일반적인 대화나 간단한 질문을 했으므로 Chat 도구를 사용합니다.
    Action: Chat
    Action Input: <사용자 질문 전체 또는 대화에 적합한 요약된 질문 (예: 안녕하세요?, 오늘 날씨 어때요?)>

너는 사용자의 질문을 가장 주의 깊게 분석하고, 위에 제시된 도구 사용 형식에 **정확히 일치하도록** `Action:`과 `Action Input:`을 출력해야 해.
특히 `Action Input:`에는 **사용자 질문에서 추출한 구체적인 값만** 들어가야 해. 절대로 플레이스홀더(`url: str`)나 일반적인 설명 (`The suspicious URL...`)을 넣지 마.

도구를 사용한 후에는 다음 형식으로 결과를 보고해야 해:
Observation: <도구 실행 결과>
그리고 마지막으로, 사용자의 **원래 질문의 의도**에 맞춰 친절하고 완전한 한국어 문장으로 최종 답변을 한 번만 제공해.

--- 중요한 규칙 ---
- 'Action:' 뒤에는 오직 도구 이름만 와야 해. 'Use'나 다른 불필요한 단어를 붙이지 마.
- 'Action Input:' 뒤에는 도구에 전달할 순수한 입력 값만 와야 해.
- 'Final Answer:'는 사용자가 이해하기 쉬운 완전한 한국어 문장으로 한 번만 제공하고, 절대로 반복하지 마. 다른 언어를 섞지 말고 한국어로만 답해. 불필요한 백틱(```)이나 추가적인 'Final Answer:' 접두사도 포함하지 마.
- 만약 도구 사용 중 오류가 발생하면, 즉시 사용자에게 '현재 도구 사용에 문제가 있습니다. 다른 방법으로 시도하거나 잠시 후 다시 시도해주세요.'와 같이 명확하게 안내하고 최종 답변을 마무리해. 불필요한 추론을 반복하지 마.
- 최종 답변(Final Answer)은 반드시 한국어로만 해.

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
        final_answer_match = re.search(r"Final Answer:\s*(.*?)(?:```|$|Final Answer:)", text, re.DOTALL)
        if final_answer_match:
            # 추출된 답변에서 모든 'Final Answer:' 접두사와 불필요한 백틱을 제거
            cleaned_answer = final_answer_match.group(1).replace("Final Answer:", "").replace("```", "").strip()
            return AgentFinish(
                return_values={"output": cleaned_answer},
                log=text,
            )

        # Action 파싱 로직 강화: 'Use ' 같은 접두어를 무시하고 실제 툴 이름만 추출
        # 'Action:' 뒤에 오는 가장 첫 번째 단어를 툴 이름으로 간주하고,
        # Action Input을 찾아야 합니다.
        action_match = re.search(r"Action:\s*(?:Use\s*)?(\w+)\s*(?:\((.*?)\))?\s*(?:\nAction Input:\s*(.*))?", text, re.DOTALL)
        
        if action_match:
            tool_name = action_match.group(1).strip()
            # 괄호 안의 입력 (group 2) 또는 Action Input: 뒤의 입력 (group 3)
            tool_input_from_paren = action_match.group(2)
            tool_input_from_newline = action_match.group(3)

            tool_input = None
            if tool_input_from_paren is not None:
                tool_input = tool_input_from_paren.strip()
            elif tool_input_from_newline is not None:
                tool_input = tool_input_from_newline.strip()

            # 유효한 툴 이름인지 확인
            valid_tool_names = [tool.name for tool in tools]
            if tool_name not in valid_tool_names:
                raise OutputParserException(f"Invalid tool name found: '{tool_name}'. Expected one of {valid_tool_names}. Full text: `{text}`")
            
            # Action Input이 비어있으면 파싱 오류 (프롬프트에서 Action Input이 필수임을 강조했기 때문)
            if tool_input is None or not tool_input:
                raise OutputParserException(f"Action Input is missing or empty for tool '{tool_name}'. Full text: `{text}`")

            print(f"DEBUG: Parsed Action - Tool: '{tool_name}', Input: '{tool_input}'")
            return AgentAction(tool=tool_name, tool_input=tool_input, log=text)
        
        # 아무 패턴도 매칭되지 않을 경우 파싱 오류
        raise OutputParserException(f"Could not parse LLM output (no valid Action or Final Answer found): `{text}`")

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
        # \nObservation: 다음 Thought로 넘어가기 전에 멈춤
        # \nFinal Answer: 를 생성하면 즉시 멈추도록 유도
        # <|eot_id|>는 Llama-3의 End Of Turn 토큰. 모델이 이걸 생성하면 멈춤.
        "stop": ["\nObservation:", "\nFinal Answer:", "<|eot_id|>"],
        "output_parser": custom_parser, # ✨ 커스텀 파서 적용
    }
)
print("✅ LangChain Agent 초기화 완료.")

# 3) 인터랙티브 채팅 함수
def chat(query: str) -> str:
    """
    Agent가 내부적으로:
    - URL 패턴 감지 → URLBERT_ThreatAnalyzer 호출
    - 보안 개념 질문 감지 → SecurityDocsQA 호출
    - 그 외 → Chat 툴 (LLM 직접 응답)
    """
    try:
        response_dict = agent.invoke({"input": query})
        raw_output = response_dict.get('output', "응답을 생성하는 데 문제가 발생했습니다.")

        # Final Answer 후처리: 파서에서 대부분 처리되지만, 혹시 모를 경우를 대비
        raw_output = raw_output.replace("Final Answer:", "").replace("```", "").strip()
        
        # 마지막 문장이 반복되는 경우 제거 시도 (간단한 휴리스틱)
        # LLM이 반복적인 출력을 하는 경향이 있으므로, 최종 출력에서 한 번 더 정리
        sentences = re.split(r'(?<=[.?!])\s+', raw_output) # 문장 단위로 분리
        if len(sentences) > 1:
            # 마지막 문장이 이전 문장과 동일하거나 매우 유사하면 제거
            if sentences[-1].strip() == sentences[-2].strip():
                raw_output = " ".join(sentences[:-1]).strip()
            # 또는 마지막 문장이 불필요하게 반복되는 패턴 (예: "안전합니다. 안전합니다.")
            elif len(sentences[-1].strip()) < 10 and sentences[-1].strip() in sentences[-2].strip(): # 짧은 반복
                 raw_output = " ".join(sentences[:-1]).strip()
        
        # 한국어 답변이 아닌 경우 강제로 한국어 안내
        if any(char for char in raw_output if '\uAC00' <= char <= '\uD7A3'): # 한글이 포함되어 있는지 확인
            return raw_output.strip()
        else:
            return "죄송합니다. 답변이 명확하지 않습니다. 한국어로 다시 말씀해주시겠어요?"

    except OutputParserException as e:
        # LLM이 파싱할 수 없는 출력을 생성했을 때
        print(f"⚠️ 파싱 오류 발생: {e}")
        # LLM의 'Thought'를 통해 오류의 원인을 유추하고 사용자에게 안내
        return "죄송합니다. 챗봇이 답변을 이해하는 데 문제가 발생했습니다. 질문을 좀 더 명확하게 다시 해주시면 감사하겠습니다. (예: '이 URL 안전한가요? https://en.bab.la/dictionary/korean-english/%EC%A3%BC%EC%86%8C' 또는 '피싱이 뭔가요?')"
    except Exception as e:
        # 기타 예외 처리
        print(f"❌ 챗봇 처리 중 예측하지 못한 오류 발생: {e}")
        return f"죄송합니다. 챗봇 처리 중 내부 오류가 발생했습니다. 잠시 후 다시 시도해주세요."

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