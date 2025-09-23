# bot_main4.py
# 목적: GGUF(베이스) + GGUF-LoRA(행동결정)로 도구 선택만 로컬 LLaMA가 하고,
#       실행( URLBERT / RAG / Chat )은 기존 파이프라인(Gemini/URLBERT/RAG)을 그대로 사용.

import os
import sys
import re
import warnings

# 0) 환경/경고
os.environ.setdefault("TOKENIZERS_PARALLELISM", "false")
warnings.filterwarnings("ignore", category=FutureWarning, module="huggingface_hub.file_download")

# 1) 외부/프로젝트 의존성
from langchain.agents import Tool
from dotenv import load_dotenv
from langchain_google_genai import ChatGoogleGenerativeAI
from langchain_core.prompts import PromptTemplate
from langchain.memory import ConversationBufferMemory

load_dotenv('api.env')

project_root = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
if project_root not in sys.path:
    sys.path.insert(0, project_root)

urlbert_base = os.path.join(project_root, 'urlbert', 'urlbert2')
if urlbert_base not in sys.path:
    sys.path.insert(0, urlbert_base)

from bot.tools.urlbert_tool import load_urlbert_tool
from bot.tools.rag_tools import load_rag_tool, build_rag_index_from_jsonl
from urlbert.urlbert2.core.model_loader import GLOBAL_MODEL, GLOBAL_TOKENIZER
from bot.feature_extractor import build_raw_features, summarize_features_for_explanation

# 2) Gemini (콘텐츠 생성/요약 등 기존 역할) 초기화
if "GOOGLE_API_KEY" not in os.environ:
    raise ValueError("환경 변수에 'GOOGLE_API_KEY'가 설정되어 있지 않습니다.")

gemini = ChatGoogleGenerativeAI(model="gemini-2.0-flash", temperature=0.01)

def chat_fn(query: str) -> str:
    raw = gemini.invoke(query).content
    return raw.strip()

chat_tool = Tool(
    name="Chat",
    func=chat_fn,
    description="일반 대화 및 간단한 정보 답변용"
)

# 3) 보안 툴(URLBERT, RAG) 초기화
try:
    url_tool = load_urlbert_tool(GLOBAL_MODEL, GLOBAL_TOKENIZER)
except Exception as e:
    url_tool = Tool(
        name="URLBERT_ThreatAnalyzer",
        func=lambda x, _e=str(e): f"URL 분석 툴 로드 중 오류 발생: {_e}",
        description="URL 안전/위험 판단"
    )

RAG_INDEX_DIR = os.path.join(project_root, 'security_faiss_index')
RAG_DATA_PATH = os.path.join(project_root, 'data', 'rag_dataset.jsonl')
if not os.path.exists(RAG_INDEX_DIR):
    if os.path.exists(RAG_DATA_PATH):
        print(f"🔧 RAG 인덱스를 생성합니다: {RAG_DATA_PATH} -> {RAG_INDEX_DIR}")
        build_rag_index_from_jsonl(RAG_DATA_PATH, RAG_INDEX_DIR)
    else:
        print(f"⚠️ RAG 데이터 파일({RAG_DATA_PATH})이 없어 RAG 인덱스를 생성할 수 없습니다.")

try:
    rag_tool = load_rag_tool(RAG_INDEX_DIR, gemini)
except Exception as e:
    print(f"❌ RAG 툴 로드 중 오류 발생: {e}")
    rag_tool = Tool(
        name="SecurityDocsQA",
        func=lambda q: "RAG 툴 로드에 실패하여 문서 검색을 사용할 수 없습니다.",
        description="보안 문서 검색 (현재 비활성화됨)"
    )

# 4) 상세 URL 설명 프롬프트(기존 유지)
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
1. URL-BERT의 최종 판정(정상/악성)을 먼저 명확히 알려주세요.
2. '세부 특징 데이터'를 근거로 들어 왜 그렇게 판단했는지 2~3가지 핵심 이유를 설명해주세요.
3. 사용자가 어떻게 행동해야 할지 간단한 조치를 추천해주세요.
4. 모든 답변은 한국어 대화체로 작성해주세요.

[최종 답변]
"""
url_prompt = PromptTemplate.from_template(URL_PROMPT_TEMPLATE)

# 5) 메모리
memory = ConversationBufferMemory(memory_key="chat_history", return_messages=True)

# 6) llama-cpp 기반 "행동 결정기" 초기화 (GGUF + GGUF-LoRA)# 6) llama-cpp 기반 "행동 결정기" 초기화 (GGUF + GGUF-LoRA)
from llama_cpp import Llama

# 기본 경로 (환경변수로 오버라이드 가능)
LLM_GGUF = os.getenv(
    "LLM_GGUF",
    "/home/injeolmi/project/models/gguf/llama-3-Korean-Bllossom-8B-Q4_K_M.gguf"  # 베이스 GGUF
)
LORA_GGUF = os.getenv(
    "LORA_GGUF",
    "/home/injeolmi/project/models/gguf/bllossom_agent_lora.gguf"                # 변환 완료된 LoRA GGUF
)

try:
    llm_decider = Llama(
        model_path=LLM_GGUF,          # 베이스 모델 GGUF
        lora_path=LORA_GGUF,          # LoRA 어댑터 GGUF (convert_lora_to_gguf.py 결과물)
        # 대부분의 빌드에선 lora_base 없이도 잘 적용됩니다.
        # 혹시 런타임에 base path None 관련 메시지가 계속 뜨면 아래 주석을 해제해서 사용하세요.
        # lora_base=LLM_GGUF,

        n_ctx=4096,
        n_threads=int(os.getenv("LLAMA_THREADS", "8")),
        n_gpu_layers=0,               # GPU 안 쓸 경우 명시적으로 0
        chat_format="llama-3",        # Llama-3 계열(Bllossom) 채팅 템플릿
        verbose=True
    )
    print(f"✅ llama.cpp(결정기) loaded: base={LLM_GGUF}, lora={LORA_GGUF}")
except Exception as e:
    llm_decider = None
    print(f"❌ llama.cpp 로드 실패: {e}  (규칙기반 폴백 사용)")


# ─────────────────────────────────────────────────────────────────────────────────
# 7) 행동 결정 유틸(반복/환각 방지 포함)
STOP_WORDS = ["\n\n", "\nAction Result", "\nAction Logic", "\nAction Reference", "assistant\n", "assistant"]
VALID_ACTIONS = {"URLBERT_ThreatAnalyzer", "SecurityDocsQA", "Chat"}
ACT_PAT = re.compile(r"Action:\s*(?P<act>[A-Za-z_]+)\s*\nAction Input:\s*(?P<input>.+)", re.S)
URL_PAT = re.compile(r'(https?://\S+|(?:[A-Za-z0-9-]+\.)+[A-Za-z]{2,}\S*)', re.I)

def _truncate_on_stops(s: str) -> str:
    cut = len(s)
    for w in STOP_WORDS:
        i = s.find(w)
        if i != -1:
            cut = min(cut, i)
    return s[:cut]

def _first_url(text: str):
    m = URL_PAT.search(text or "")
    return m.group(0) if m else None

def decide_action_with_llm(user_query: str):
    # 1) 시스템 지시: 오직 형식만 출력
    sys_prompt = (
        "너는 보안 분석 챗봇이야. 질문에 맞춰 오직 다음 형식만 출력해.\n"
        "Action: <URLBERT_ThreatAnalyzer|SecurityDocsQA|Chat>\n"
        "Action Input: <텍스트>"
    )

    if llm_decider is not None:
        out = llm_decider.create_chat_completion(
            messages=[
                {"role": "system", "content": sys_prompt},
                {"role": "user", "content": user_query},
            ],
            temperature=0.0, top_p=1.0, repeat_penalty=1.2, max_tokens=64
        )
        raw = out["choices"][0]["message"]["content"]
        raw = _truncate_on_stops(raw)
        m = ACT_PAT.search(raw)
        if m and m.group("act") in VALID_ACTIONS:
            action = m.group("act").strip()
            action_input = _truncate_on_stops(m.group("input").strip()).splitlines()[0].strip()
            # URL 액션이면 입력 정리
            if action == "URLBERT_ThreatAnalyzer":
                url = _first_url(action_input) or _first_url(user_query)
                action_input = url if url else user_query
            return action, action_input, raw

    # 2) 폴백(규칙 기반)
    why_tokens = ["왜", "이유", "근거", "자세히", "어디가", "무엇 때문에", "설명"]
    why = any(k in user_query for k in why_tokens)
    url = _first_url(user_query)
    if url:
        action = "SecurityDocsQA" if why else "URLBERT_ThreatAnalyzer"
        action_input = (f"{url} 위험 근거 설명" if why else url)
    else:
        action = "SecurityDocsQA"
        action_input = user_query
    return action, action_input, "(fallback-rules)"

# ─────────────────────────────────────────────────────────────────────────────────
# 8) 보조 함수: URLBERT 결과에서 판정 추정
def _infer_verdict_from_text(bert_text: str) -> str:
    t = (bert_text or "").lower()
    bad = ["malicious", "phishing", "suspicious", "악성", "위험", "유해"]
    good = ["benign", "legitimate", "safe", "정상", "안전"]
    if any(tok in t for tok in bad) and not any(tok in t for tok in good):
        return "악성"
    if any(tok in t for tok in good) and not any(tok in t for tok in bad):
        return "정상"
    return "정상"

# ─────────────────────────────────────────────────────────────────────────────────
# 9) 최종 라우팅(핵심): LLaMA가 고른 Action을 실행
def get_chatbot_response(user_text: str) -> dict:
    text = user_text.strip()

    # ① LLaMA에게 도구 선택을 맡긴다
    action, action_input, raw_llm = decide_action_with_llm(text)

    # ② 실행 분기
    if action == "URLBERT_ThreatAnalyzer":
        # 간단 URL 분석
        bert_result_text = url_tool.func(action_input)
        return {"answer": bert_result_text, "mode": "url_analysis_simple", "url": action_input,
                "action": action, "action_input": action_input, "raw_llm": raw_llm}

    elif action == "SecurityDocsQA":
        url_in_input = _first_url(action_input)
        if url_in_input:
            # 상세 URL 분석(설명 프롬프트 사용)
            bert_result_text = url_tool.func(url_in_input)
            try:
                raw_features_df = build_raw_features(url_in_input)
                if not raw_features_df.empty:
                    verdict = _infer_verdict_from_text(bert_result_text)
                    reasons = summarize_features_for_explanation(raw_features_df, verdict, top_k=3)
                    feature_details = "\n".join(f"- {r}" for r in reasons) if reasons else "세부 특징을 추출하지 못했습니다."
                else:
                    feature_details = "세부 특징을 추출하지 못했습니다."
            except Exception as e:
                feature_details = f"세부 특징 추출 중 오류 발생: {e}"

            final_prompt = url_prompt.format(
                user_query=text,
                bert_result=bert_result_text,
                feature_details=feature_details
            )
            final_answer = chat_tool.func(final_prompt)  # Gemini로 자연어 설명 생성
            return {"answer": final_answer, "mode": "url_analysis_detailed", "url": url_in_input,
                    "action": action, "action_input": action_input, "raw_llm": raw_llm}
        else:
            # 일반 보안 지식/문서 검색
            rag_out = rag_tool.func(text)
            rag_answer = rag_out.get("answer", "")
            sources = rag_out.get("sources", [])
            return {"answer": rag_answer, "mode": "rag", "sources": sources[:5],
                    "action": action, "action_input": action_input, "raw_llm": raw_llm}

    else:
        # Chat
        chat_answer = chat_tool.func(text)
        return {"answer": chat_answer, "mode": "chat",
                "action": action, "action_input": action_input, "raw_llm": raw_llm}

# ─────────────────────────────────────────────────────────────────────────────────
# 10) 인터랙티브 루프(테스트)
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

        # 메모리 기록
        memory.save_context({"input": text}, {"output": answer})

        if mode == "rag":
            print("🔍 [RAG 문서 기반 응답]")
        elif mode == "chat":
            print("💬 [일반 Chat 응답]")
        elif mode == "url_analysis_detailed":
            print("🔗 [URL 상세 분석]")
            if response.get("url"):
                print(f"   대상: {response['url']}")
        elif mode == "url_analysis_simple":
            print("🔗 [URL 간단 분석]")
            if response.get("url"):
                print(f"   대상: {response['url']}")

        print(f"Bot ▶ Final Answer: {answer}")

        if response.get("sources"):
            print("📚 [출처]")
            for s in response["sources"]:
                print(" -", s)

        # 디버깅 원하면 주석 해제
        # print("[LLM raw]\n", response.get("raw_llm"))
