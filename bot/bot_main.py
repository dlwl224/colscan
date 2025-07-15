# bot/bot_main.py

import re

from langchain.agents import initialize_agent, Tool
from langchain.memory import ConversationBufferMemory


from transformers import AutoTokenizer, AutoModelForCausalLM, pipeline
from langchain.llms import HuggingFacePipeline
import torch
import os    
import sys   


project_root = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..')) # sQanAR 경로
if project_root not in sys.path:
    sys.path.insert(0, project_root)

# urlbert/urlbert2/ 이 sys.path 에 있어야 urlbert.urlbert2.core.model_loader 등 임포트 가능
urlbert_base_path = os.path.join(project_root, 'urlbert', 'urlbert2')
if urlbert_base_path not in sys.path:
    sys.path.insert(0, urlbert_base_path)


# 1) URL-BERT 분석 툴
from bot.tools.urlbert_tool import load_urlbert_tool
# 2) RAG 보안 문서 검색 툴
from bot.tools.rag_tools    import load_rag_tool

def chat_tool_fn(query: str) -> str:
    return llm(query)

# ───────────────────────────────────────────────────────────────────────────────

MODEL_DIR = "/content/drive/MyDrive/sQanAR/colscan/models/llama-3-Korean-Blossom-8B" 

print("Llama 모델 로드 시작...")
tokenizer = AutoTokenizer.from_pretrained(MODEL_DIR)
model     = AutoModelForCausalLM.from_pretrained(
    MODEL_DIR,
    torch_dtype=torch.float16, # Colab GPU (T4)에 적합
    device_map="auto" # 사용 가능한 GPU에 모델 자동 분산
)

# pad token 설정 (모델과 토크나이저 모두)
if tokenizer.pad_token is None:
    tokenizer.pad_token = tokenizer.eos_token
# 모델의 pad_token_id가 없을 경우 tokenizer의 pad_token_id로 설정
if model.config.pad_token_id is None:
    model.config.pad_token_id = tokenizer.pad_token_id


# HuggingFacePipeline으로 래핑하여 LangChain LLM 객체로 사용
pipe = pipeline(
    "text-generation",
    model=model,
    tokenizer=tokenizer,
    max_new_tokens=512, # 챗봇 응답 최대 길이
    temperature=0.2,    # 창의성 조절 (낮을수록 보수적)
    do_sample=True,     # 샘플링 방식 사용
    top_p=0.95,         # Top-p 샘플링 (확률 누적)
    pad_token_id=tokenizer.pad_token_id # 패딩 토큰 ID 설정
)
llm = HuggingFacePipeline(pipeline=pipe)
print("✅ Llama 모델 로드 및 LangChain LLM 객체 생성 완료.")

# 툴 로드
# urlbert_tool.py는 urlbert/urlbert2/core/model_loader.py의 load_inference_model()을 호출합니다.
# 이 모델은 Llama와 별개의 BERT 기반 모델이므로, 여기서 로드합니다.
from urlbert.urlbert2.core.model_loader import load_inference_model as load_urlbert_inference_model
urlbert_model, urlbert_tokenizer = load_urlbert_inference_model()
# urlbert_tool.py의 load_urlbert_tool 함수에 모델과 토크나이저를 전달
url_tool = load_urlbert_tool(urlbert_model, urlbert_tokenizer)
print("✅ URL-BERT Tool 로드 완료.")

# RAG는 새로 로드된 Llama LLM 사용
rag_tool = load_rag_tool("security_faiss_index", llm)
print("✅ RAG Tool 로드 완료.")

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
            if q.lower() in {"quit", "exit", "종료"}: # '종료' 추가
                print("챗봇을 종료합니다. 👋")
                break
            resp = chat(q)
            print("Bot ▶", resp)
    except KeyboardInterrupt:
        print("\n챗봇을 강제 종료합니다. 👋")