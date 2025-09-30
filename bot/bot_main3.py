import os
import sys
import re
import warnings

# GPU 완전 차단(WSL 등에서 안전) 및 경고 메시지 비활성화
os.environ.setdefault("CUDA_VISIBLE_DEVICES", "")
os.environ.setdefault("TOKENIZERS_PARALLELISM", "false")
warnings.filterwarnings("ignore", category=FutureWarning, module="huggingface_hub.file_download")

from langchain.agents import Tool
from dotenv import load_dotenv
from langchain_google_genai import ChatGoogleGenerativeAI
from langchain_core.prompts import PromptTemplate
from langchain.memory import ConversationBufferMemory

# .env 로드
load_dotenv('api.env')

# 프로젝트 경로 설정
# 이 스크립트가 'bot' 폴더 안에 있다고 가정합니다.
project_root = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
if project_root not in sys.path:
    sys.path.insert(0, project_root)

# URL-BERT 경로 설정
urlbert_base = os.path.join(project_root, 'urlbert', 'urlbert2')
if urlbert_base not in sys.path:
    sys.path.insert(0, urlbert_base)

# 1) LLM 초기화
if "GOOGLE_API_KEY" not in os.environ:
    raise ValueError("환경 변수에 'GOOGLE_API_KEY'가 설정되어 있지 않습니다.")

llm = ChatGoogleGenerativeAI(
    model="gemini-2.0-flash",
    temperature=0.01
)

# 2) 툴 및 필요 함수 로드

from bot.tools.urlbert_tool import load_urlbert_tool
from bot.tools.rag_tools import load_rag_tool, build_rag_index_from_jsonl
from urlbert.urlbert2.core.model_loader import GLOBAL_MODEL, GLOBAL_TOKENIZER
from bot.feature_extractor import build_raw_features, summarize_features_for_explanation

# URL-BERT 툴 초기화
try:
    url_tool = load_urlbert_tool(GLOBAL_MODEL, GLOBAL_TOKENIZER)
except Exception as e:
    url_tool = Tool(
        name="URLBERT_ThreatAnalyzer",
        func=lambda x, _e=str(e): f"URL 분석 툴 로드 중 오류 발생: {_e}",
        description="URL 안전/위험 판단"
    )

# RAG 인덱스 및 툴 초기화
RAG_INDEX_DIR = os.path.join(project_root, 'security_faiss_index')
RAG_DATA_PATH = os.path.join(project_root, 'data', 'rag_dataset.jsonl')
if not os.path.exists(RAG_INDEX_DIR):
    if os.path.exists(RAG_DATA_PATH):
        print(f"🔧 RAG 인덱스를 생성합니다: {RAG_DATA_PATH} -> {RAG_INDEX_DIR}")
        build_rag_index_from_jsonl(RAG_DATA_PATH, RAG_INDEX_DIR)
    else:
        print(f"⚠️ RAG 데이터 파일({RAG_DATA_PATH})이 없어 RAG 인덱스를 생성할 수 없습니다.")

try:
    rag_tool = load_rag_tool(RAG_INDEX_DIR, llm)
except Exception as e:
    print(f"❌ RAG 툴 로드 중 오류 발생: {e}")
    rag_tool = Tool(
        name="SecurityDocsQA",
        func=lambda q: "RAG 툴 로드에 실패하여 문서 검색을 사용할 수 없습니다.",
        description="보안 문서 검색 (현재 비활성화됨)"
    )

# 일반 대화 툴 초기화
def chat_fn(query: str) -> str:
    raw = llm.invoke(query).content
    return raw.strip()

chat_tool = Tool(
    name="Chat",
    func=chat_fn,
    description="일반 대화 및 간단한 정보 답변용"
)

# 3) 메모리 및 프롬프트 설정
memory = ConversationBufferMemory(memory_key="chat_history", return_messages=True)

URL_PATTERN = re.compile(
    r'(https?://\S+|(?:[A-Za-z0-9-]+\.)+[A-Za-z]{2,}\S*)'
)
WHY_KEYWORDS = ["왜", "어디가", "뭐 때문에", "이유", "근거", "자세히", "어떤 점"]
MEMORY_KEYWORDS = ["방금", "내가", "뭐였지", "기억해", "누구", "이름"]

# 간단 URL 분석 결과 요약용 프롬프트
SIMPLE_URL_PROMPT_TEMPLATE = """
당신은 URL 분석 결과를 일반 사용자가 이해하기 쉽게 요약해주는 AI 비서입니다.
아래의 기술적인 분석 결과를 바탕으로, 사용자에게 친절한 말투로 최종 결론을 알려주세요.

[기술적 분석 결과]
{bert_result}

[답변 가이드]
1. 분석 결과를 바탕으로 "안전", "위험", "주의" 등 명확한 결론을 내리고, 이모지(✅, ❌, ⚠️)와 함께 가장 먼저 보여주세요.
2. 신뢰도(%) 정보를 강조해서 언급해주세요. (예: "99.99%의 신뢰도로 안전한 사이트로 확인되었어요.")
3. 불필요한 헤더 정보나 기술적인 용어는 모두 제외하고, 최종 판정과 신뢰도만 간결하게 전달하세요.
4. 사용자가 원하면 더 자세한 분석도 가능하다는 점을 안내해주세요. (예: "더 자세한 이유가 궁금하시면 '왜 안전해?'라고 물어보세요!")
5. 전체 답변은 1~2문장의 짧고 친절한 한국어 대화체로 작성해주세요.

[최종 요약 답변]
"""
simple_url_prompt = PromptTemplate.from_template(SIMPLE_URL_PROMPT_TEMPLATE)


# 상세 URL 분석용 프롬프트
URL_PROMPT_TEMPLATE = """
당신은 URL 보안 분석 전문가입니다. 사용자 질문과 함께 제공된 URL 분석 결과 및 세부 특징 데이터를 바탕으로,
왜 해당 URL이 위험하거나 안전한지 친절하고 상세하게 설명해주세요.

[사용자 질문]
{user_query}

[URL-BERT 1차 분석 결과]
{bert_result}

[세부 특징 데이터]
{feature_details}

[답변 가이드]
1. **결론부터 명확하게**: URL-BERT의 최종 판정(예: "✅ 안전한 웹사이트입니다!")과 신뢰도를 한 문장으로 요약해서 가장 먼저 보여주세요.

2. **핵심 요약 (Summary)**:
   - 사용자가 긴 글을 읽지 않아도 되도록, 판단의 핵심 근거 1~2가지를 매우 간결하게 요약해주세요.
   - (예: "SSL 인증서가 오랫동안 유지되고 있고, 외부 리소스 의존도가 낮아 안전성이 높습니다.")

3. **상세 설명 (Details)**:
   - 요약 아래에, '세부 특징 데이터'를 근거로 들어 왜 그렇게 판단했는지 2~3가지 핵심 이유를 구체적으로 설명해주세요.
   - 각 이유를 번호를 붙여 명확하게 구분해주세요.

4. **사용자 행동 요령**:
   - 사용자가 어떻게 행동해야 할지 간단한 조치를 추천해주세요. (예: "안심하고 사용하셔도 좋습니다. 다만, 항상...")

5. **작성 스타일**:
   - 모든 답변은 일반 사용자가 이해하기 쉬운 한국어 대화체로 작성하고, 이모지를 적절히 사용해 가독성을 높여주세요.

[최종 답변]
"""
url_prompt = PromptTemplate.from_template(URL_PROMPT_TEMPLATE)

# 메모리 기반 답변용 프롬프트
MEMORY_PROMPT_TEMPLATE = """
당신은 사용자와의 대화를 기억하는 친절한 챗봇입니다. 아래 대화 기록을 바탕으로 사용자의 질문에 답변해주세요.

[대화 기록]
{chat_history}

[사용자 질문]
{user_query}

[최종 답변]
"""
memory_prompt = PromptTemplate.from_template(MEMORY_PROMPT_TEMPLATE)

#  URLBERT 결과 텍스트에서 판정을 추정하는 헬퍼
def _infer_verdict_from_text(bert_text: str) -> str:
    t = (bert_text or "").lower()
    bad_tokens = ["malicious", "phishing", "suspicious", "악성", "위험", "유해"]
    good_tokens = ["benign", "legitimate", "safe", "정상", "안전"]
    if any(tok in t for tok in bad_tokens) and not any(tok in t for tok in good_tokens):
        return "악성"
    if any(tok in t for tok in good_tokens) and not any(tok in t for tok in bad_tokens):
        return "정상"
    return "정상"

# 4) 챗봇 응답 생성 함수
def get_chatbot_response(query: str) -> dict:
    text = query.strip()
    
    match = URL_PATTERN.search(text)
    is_why_question = any(keyword in text for keyword in WHY_KEYWORDS)
    is_memory_question = any(keyword in text for keyword in MEMORY_KEYWORDS)

    # 메모리 참조 질문 (URL 없으면)
    if is_memory_question and not match:
        history = memory.load_memory_variables({})['chat_history']
        final_prompt = memory_prompt.format(chat_history=history, user_query=text)
        final_answer = llm.invoke(final_prompt).content
        return {"answer": final_answer, "mode": "memory"}
    
    # URL 포함된 경우
    if match:
        url = match.group(1)
        
        # URL-BERT의 기술적 결과를 먼저 받아옵니다.
        bert_result_text = url_tool.func(url)

        if is_why_question:  # 상세 분석 요청
            try:
                raw_features_df = build_raw_features(url)
                if not raw_features_df.empty:
                    verdict = _infer_verdict_from_text(bert_result_text)
                    reasons = summarize_features_for_explanation(raw_features_df, verdict, top_k=3)
                    feature_details = "\n".join(f"- {r}" for r in reasons)
                else:
                    feature_details = "세부 특징을 추출하지 못했습니다."
            except Exception as e:
                feature_details = f"세부 특징 추출 중 오류 발생: {e}"

            final_prompt = url_prompt.format(
                user_query=text,
                bert_result=bert_result_text,
                feature_details=feature_details
            )
            final_answer = llm.invoke(final_prompt).content
            return {"answer": final_answer, "mode": "url_analysis_detailed", "url": url}
        
        else:  # 간단 분석 요청 시에도 LLM으로 사용자 친화적 답변 생성
            final_prompt = simple_url_prompt.format(bert_result=bert_result_text)
            final_answer = llm.invoke(final_prompt).content
            return {"answer": final_answer, "mode": "url_analysis_simple", "url": url}

    # RAG(문서 검색) 시도
    rag_out = rag_tool.func(text)
    rag_answer = rag_out.get("answer", "")
    rag_found = rag_out.get("found", False)
    not_found_message = "찾을 수 없습니다"

    if rag_found and rag_answer and not_found_message not in rag_answer:
        sources = rag_out.get("sources", [])
        seen, uniq = set(), []
        for s in sources:
            if s not in seen:
                seen.add(s)
                uniq.append(s)
        return {"answer": rag_answer, "mode": "rag", "sources": uniq[:5]}

    # 일반 대화
    chat_answer = chat_tool.func(text)
    return {"answer": chat_answer, "mode": "chat"}

# 5) 대화 루프 
if __name__ == '__main__':
    print("--- 챗봇 시작 (종료: '종료') ---")
    while True:
        try:
            text = input("You ▶ ").strip()
        except (EOFError, KeyboardInterrupt):
            break

        if text.lower() in {"종료", "exit"}:
            break
        if not text:
            continue

        response = get_chatbot_response(text)
        
        answer = response.get("answer")
        mode = response.get("mode")
        
        # 대화 내용 메모리에 저장
        memory.save_context({"input": text}, {"output": answer})
        
        if mode == "rag":
            print("🔍 [RAG 문서 기반 응답]")
        elif mode == "chat":
            print("💬 [일반 Chat 응답]")
        elif mode == "url_analysis_detailed":
            if response.get("url"):
                print(f"   대상: {response['url']}")
        elif mode == "url_analysis_simple":
            if response.get("url"):
                print(f"   대상: {response['url']}")
        elif mode == "memory":
            print("🧠 [메모리 기반 응답]")

        print(f"Bot ▶ Final Answer: \n{answer}")
        
        if response.get("sources"):
            print("📚 [출처]")
            for s in response["sources"]:
                print(" -", s)