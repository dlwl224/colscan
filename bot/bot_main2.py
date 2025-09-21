# import os
# import sys
# import re
# import warnings

# # GPU 완전 차단(WSL 등에서 안전) 및 경고 메시지 비활성화
# os.environ.setdefault("CUDA_VISIBLE_DEVICES", "")
# os.environ.setdefault("TOKENIZERS_PARALLELISM", "false")
# warnings.filterwarnings("ignore", category=FutureWarning, module="huggingface_hub.file_download")

# from langchain.agents import Tool
# from dotenv import load_dotenv
# from langchain_google_genai import ChatGoogleGenerativeAI
# from langchain_core.prompts import PromptTemplate
# from langchain.memory import ConversationBufferMemory

# # .env 로드
# load_dotenv('api.env')

# # 프로젝트 경로 설정
# project_root = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
# if project_root not in sys.path:
#     sys.path.insert(0, project_root)

# # URL-BERT 경로 설정
# urlbert_base = os.path.join(project_root, 'urlbert', 'urlbert2')
# if urlbert_base not in sys.path:
#     sys.path.insert(0, urlbert_base)

# # 1) LLM 초기화
# if "GOOGLE_API_KEY" not in os.environ:
#     raise ValueError("환경 변수에 'GOOGLE_API_KEY'가 설정되어 있지 않습니다.")

# llm = ChatGoogleGenerativeAI(
#     model="gemini-pro",
#     temperature=0.1
# )

# # 2) 툴 및 필요 함수 로드
# from bot.tools.urlbert_tool import load_urlbert_tool
# from bot.tools.rag_tools import load_rag_tool, build_rag_index_from_jsonl
# from urlbert.urlbert2.core.model_loader import load_inference_model
# from bot.extract_features import build_raw_features

# # URL-BERT 툴 초기화
# try:
#     urlbert_model, urlbert_tokenizer = load_inference_model()
#     url_tool = load_urlbert_tool(urlbert_model, urlbert_tokenizer)
# except Exception as e:
#     url_tool = Tool(
#         name="URLBERT_ThreatAnalyzer",
#         func=lambda x, _e=str(e): f"URL 분석 툴 로드 중 오류 발생: {_e}",
#         description="URL 안전/위험 판단"
#     )

# # RAG 인덱스 및 툴 초기화

# RAG_INDEX_DIR = os.path.join(project_root, 'security_faiss_index')
# RAG_DATA_PATH = os.path.join(project_root, 'data', 'rag_dataset.jsonl')
# if not os.path.exists(RAG_INDEX_DIR):
#     if os.path.exists(RAG_DATA_PATH):
#         print(f"RAG 인덱스를 생성합니다: {RAG_DATA_PATH} -> {RAG_INDEX_DIR}")
#         build_rag_index_from_jsonl(RAG_DATA_PATH, RAG_INDEX_DIR)
#     else:
#         print(f"RAG 데이터 파일({RAG_DATA_PATH})이 없어 RAG 인덱스를 생성할 수 없습니다.")

# try:
#     rag_tool = load_rag_tool(RAG_INDEX_DIR, llm)
# except Exception as e:
#     print(f"RAG 툴 로드 중 오류 발생: {e}")
#     rag_tool = Tool(
#         name="SecurityDocsQA",
#         func=lambda q: "RAG 툴 로드에 실패하여 문서 검색을 사용할 수 없습니다.",
#         description="보안 문서 검색 (현재 비활성화됨)"
#     )
    

# # 일반 대화 툴 초기화
# def chat_fn(query: str) -> str:
#     raw = llm.invoke(query).content
#     return raw.strip()

# chat_tool = Tool(
#     name="Chat",
#     func=chat_fn,
#     description="일반 대화 및 간단한 정보 답변용"
# )

# # 3) 메모리 및 프롬프트 설정
# memory = ConversationBufferMemory(memory_key="chat_history", return_messages=True)

# URL_PATTERN = re.compile(
#     r'(https?://\S+|(?:[A-Za-z0-9-]+\.)+[A-Za-z]{2,}\S*)'
# )
# WHY_KEYWORDS = ["왜", "어디가", "뭐 때문에", "이유", "근거", "자세히", "어떤 점"]
# MEMORY_KEYWORDS = ["방금", "내가", "뭐였지", "기억해", "누구", "이름"]

# # 상세 URL 분석용 프롬프트 (불필요한 하드코드 URL 제거)
# URL_PROMPT_TEMPLATE = """
# 당신은 URL 보안 분석 전문가입니다. 사용자 질문과 함께 제공된 URL 분석 결과 및 세부 특징 데이터를 바탕으로,
# 왜 해당 URL이 위험하거나 안전한지 친절하고 상세하게 설명해주세요.

# [사용자 질문]
# {user_query}

# [URL-BERT 1차 분석 결과]
# {bert_result}

# [세부 특징 데이터]
# {feature_details}

# [답변 가이드]
# 1. URL-BERT의 최종 판정(정상/악성)을 먼저 명확히 알려주세요.
# 2. '세부 특징 데이터'를 근거로 들어 왜 그렇게 판단했는지 2~3가지 핵심 이유를 설명해주세요.
# 3. 사용자가 어떻게 행동해야 할지 간단한 조치를 추천해주세요.
# 4. 모든 답변은 한국어 대화체로 작성해주세요.

# [최종 답변]
# """
# url_prompt = PromptTemplate.from_template(URL_PROMPT_TEMPLATE)

# # 메모리 기반 답변용 프롬프트
# MEMORY_PROMPT_TEMPLATE = """
# 당신은 사용자와의 대화를 기억하는 친절한 챗봇입니다. 아래 대화 기록을 바탕으로 사용자의 질문에 답변해주세요.

# [대화 기록]
# {chat_history}

# [사용자 질문]
# {user_query}

# [최종 답변]
# """
# memory_prompt = PromptTemplate.from_template(MEMORY_PROMPT_TEMPLATE)

# # 4) 챗봇 응답 생성 함수
# def get_chatbot_response(query: str) -> dict:
#     text = query.strip()
    
#     match = URL_PATTERN.search(text)
#     is_why_question = any(keyword in text for keyword in WHY_KEYWORDS)
#     is_memory_question = any(keyword in text for keyword in MEMORY_KEYWORDS)

#     # 메모리 참조 질문을 최우선으로 처리 (단, URL이 포함된 경우는 URL 분석이 우선)
#     if is_memory_question and not match:
#         history = memory.load_memory_variables({})['chat_history']
#         final_prompt = memory_prompt.format(chat_history=history, user_query=text)
#         final_answer = llm.invoke(final_prompt).content
#         return {"answer": final_answer, "mode": "memory"}
    
#     # URL이 포함된 경우
#     if match:
#         url = match.group(1)
        
#         if is_why_question: # 상세 분석 요청
#             bert_result_text = url_tool.func(url)
#             try:
#                 raw_features_df = build_raw_features(url)
#                 if not raw_features_df.empty:
#                     features = raw_features_df.iloc[0].dropna().to_dict()
#                     feature_details = "\n".join([f"- {key}: {value}" for key, value in features.items()])
#                 else:
#                     feature_details = "세부 특징을 추출하지 못했습니다."
#             except Exception as e:
#                 feature_details = f"세부 특징 추출 중 오류 발생: {e}"

#             final_prompt = url_prompt.format(
#                 user_query=text,
#                 bert_result=bert_result_text,
#                 feature_details=feature_details
#             )
#             final_answer = llm.invoke(final_prompt).content
#             return {"answer": final_answer, "mode": "url_analysis_detailed", "url": url}
        
#         else: # 간단 분석 요청
#             bert_result_text = url_tool.func(url)
#             return {"answer": bert_result_text, "mode": "url_analysis_simple", "url": url}

#     # RAG(문서 검색) 시도
#     rag_out = rag_tool.func(text)
#     rag_answer = rag_out.get("answer", "")
#     rag_found = rag_out.get("found", False)
#     not_found_message = "찾을 수 없습니다"

#     if rag_found and rag_answer and not_found_message not in rag_answer:
#         sources = rag_out.get("sources", [])
#         seen, uniq = set(), []
#         for s in sources:
#             if s not in seen:
#                 seen.add(s)
#                 uniq.append(s)
#         return {"answer": rag_answer, "mode": "rag", "sources": uniq[:5]}


#     # 위 모든 경우에 해당하지 않으면 일반 대화
#     chat_answer = chat_tool.func(text)
#     return {"answer": chat_answer, "mode": "chat"}

# # 5) 대화 루프 (테스트용)
# if __name__ == '__main__':
#     print("--- 챗봇 시작 (종료: '종료') ---")
#     while True:
#         try:
#             text = input("You ▶ ").strip()
#         except (EOFError, KeyboardInterrupt):
#             break

#         if text.lower() in {"종료", "exit"}:
#             break
#         if not text:
#             continue

#         response = get_chatbot_response(text)
        
#         answer = response.get("answer")
#         mode = response.get("mode")
        
#         # 대화 내용 메모리에 저장
#         memory.save_context({"input": text}, {"output": answer})
        
#         if mode == "rag":
#             print("🔍 [RAG 문서 기반 응답]")
#         elif mode == "chat":
#             print("💬 [일반 Chat 응답]")
#         elif mode == "url_analysis_detailed":
#             print("🔗 [URL 상세 분석]")
#             if response.get("url"):
#                 print(f"   대상: {response['url']}")
#         elif mode == "url_analysis_simple":
#             print("🔗 [URL 간단 분석]")
#             if response.get("url"):
#                 print(f"   대상: {response['url']}")
#         elif mode == "memory":
#             print("🧠 [메모리 기반 응답]")

#         print(f"Bot ▶ Final Answer: {answer}")
        
#         if response.get("sources"):
#             print("📚 [출처]")
#             for s in response["sources"]:
#                 print(" -", s)


import os
import sys
import re
import warnings 

#  GPU 완전 차단(WSL에서 안전)
os.environ.setdefault("CUDA_VISIBLE_DEVICES", "")
os.environ.setdefault("TOKENIZERS_PARALLELISM", "false")
warnings.filterwarnings("ignore", category=FutureWarning, module="huggingface_hub.file_download")

from langchain.agents import Tool
from dotenv import load_dotenv
from langchain_google_genai import ChatGoogleGenerativeAI

# .env 로드
load_dotenv('api.env')

# 프로젝트 경로
project_root = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
if project_root not in sys.path:
    sys.path.insert(0, project_root)

# URL-BERT 경로
urlbert_base = os.path.join(project_root, 'urlbert', 'urlbert2')
if urlbert_base not in sys.path:
    sys.path.insert(0, urlbert_base)

# 1) LLM
if "GOOGLE_API_KEY" not in os.environ:
    raise ValueError("환경 변수에 'GOOGLE_API_KEY'가 설정되어 있지 않습니다.")

llm = ChatGoogleGenerativeAI(
    model="gemini-2.0-flash",
    temperature=0.01
)
# 2) 툴 로드
from bot.tools.urlbert_tool import load_urlbert_tool
from bot.tools.rag_tools import load_rag_tool, build_rag_index_from_jsonl
from urlbert.urlbert2.core.model_loader import load_inference_model

# URL-BERT
try:
    urlbert_model, urlbert_tokenizer = load_inference_model()
    url_tool = load_urlbert_tool(urlbert_model, urlbert_tokenizer)
except Exception as e:
    url_tool = Tool(
        name="URLBERT_ThreatAnalyzer",
        func=lambda x, _e=str(e): f"URL 분석 툴 로드 중 오류 발생: {_e}",
        description="URL 안전/위험 판단"
    )

# RAG 인덱스
RAG_INDEX_DIR = os.path.join(project_root, 'security_faiss_index')
RAG_DATA_PATH = os.path.join(project_root, 'data', 'rag_dataset.jsonl')
# if not os.path.exists(RAG_INDEX_DIR):
#     # 인덱스가 없으면 생성
#     build_rag_index_from_jsonl(RAG_DATA_PATH, RAG_INDEX_DIR)

# rag_tool = load_rag_tool(RAG_INDEX_DIR, llm)

# # Chat (일반 대화)
# def chat_fn(query: str) -> str:
#     raw = llm.invoke(query).content
#     return raw.strip()

# chat_tool = Tool(
#     name="Chat",
#     func=chat_fn,
#     description="일반 대화 및 간단한 정보 답변용"
# )

# # URL 정규식
# URL_PATTERN = re.compile(
#     r'(https?://\S+|(?:[A-Za-z0-9-]+\.)+[A-Za-z]{2,}\S*)'
# )



# def get_chatbot_response(query: str) -> dict:
#     """
#     사용자 질문(query)을 받아, 상황에 맞는 챗봇 답변을 dict 형태로 반환합니다.
#     """
#     text = query.strip()
    
#     # 1) URL 포함 시 -> URLBERT 툴 사용
#     match = URL_PATTERN.search(text)
#     if match:
#         url = match.group(1)
#         analysis_text = url_tool.func(url)
#         # 답변과 함께 어떤 종류의 답변인지(mode)를 함께 반환
#         return {"answer": analysis_text, "mode": "url_analysis"}

#     # 2) RAG(문서 검색) 시도
#     rag_out = rag_tool.func(text)
#     rag_answer = rag_out.get("answer", "")
#     rag_found = rag_out.get("found", False)
#     not_found_message = "해당 정보는 문서에서 찾을 수 없습니다."

#     # 'found'가 True이고, 답변이 있으며, '못 찾았다'는 메시지가 아닐 때만 성공으로 간주
#     if rag_found and rag_answer and not_found_message not in rag_answer:
#         sources = []
#         if rag_out.get("sources"):
#             seen, uniq = set(), []
#             for s in rag_out["sources"]:
#                 if s not in seen:
#                     seen.add(s)
#                     uniq.append(s)
#             sources = uniq[:5]
#         return {"answer": rag_answer, "mode": "rag", "sources": sources}

#     # 3) 위 두 경우에 해당하지 않으면 일반 대화
#     chat_answer = chat_tool.func(text)
#     return {"answer": chat_answer, "mode": "chat"}




# # 3) 대화 루프: 직접 이 파일을 실행했을 때 테스트용으로만 사용되도록 변경
# if __name__ == '__main__':
#     print("--- 챗봇 시작 (종료: '종료') ---")
#     while True:
#         try:
#             text = input("You ▶ ").strip()
#         except (EOFError, KeyboardInterrupt):
#             break

#         if text.lower() in {"종료", "exit"}:
#             break
#         if not text:
#             continue

#         #  위에서 만든 함수를 호출하여 결과를 받도록 변경
#         response = get_chatbot_response(text)
        
#         # [수정] 응답 형식에 맞게 출력 변경
#         answer = response.get("answer")
#         mode = response.get("mode")
        
#         if mode == "rag":
#             print("🔍 [RAG 문서 기반 응답]")
#         elif mode == "chat":
#             print("💬 [일반 Chat 응답]")

#         print(f"Bot ▶ Final Answer: {answer}")
        
#         if response.get("sources"):
#             print("📚 [출처]")
#             for s in response["sources"]:
#                 print(" -", s)





#새로운거
if not os.path.exists(RAG_INDEX_DIR):
    try:
        if os.path.exists(RAG_DATA_PATH):
            print(f"RAG 인덱스 생성: {RAG_DATA_PATH} -> {RAG_INDEX_DIR}")
            build_rag_index_from_jsonl(RAG_DATA_PATH, RAG_INDEX_DIR)
        else:
            print(f"RAG 데이터 없음: {RAG_DATA_PATH}") 
    except Exception as e:
        print(f"RAG 인덱스 생성 실패: {e}") 

#  RAG 로더에 폴백 추가 (CPU 강제는 rag_tools.py에서 적용)
try:
    rag_tool = load_rag_tool(RAG_INDEX_DIR, llm)
    print(" RAG Tool 로드 완료") 
except Exception as e:
    print(f"RAG Tool 로드 중 오류 발생: {e}") 
    class _DummyRAG:
        def func(self, q):
            return {"answer": "", "found": False, "sources": [], "error": str(e)}
    rag_tool = _DummyRAG()

# Chat (일반 대화)
def chat_fn(query: str) -> str:
    raw = llm.invoke(query).content
    return raw.strip()

chat_tool = Tool(
    name="Chat",
    func=chat_fn,
    description="일반 대화 및 간단한 정보 답변용"
)

# URL 정규식
URL_PATTERN = re.compile(
    r'(https?://\S+|(?:[A-Za-z0-9-]+\.)+[A-Za-z]{2,}\S*)'
)

def get_chatbot_response(query: str) -> dict:
    """
    사용자 질문(query)을 받아, 상황에 맞는 챗봇 답변을 dict 형태로 반환합니다.
    """
    text = query.strip()

    # 1) URL 포함 시 -> URLBERT
    match = URL_PATTERN.search(text)
    if match:
        url = match.group(1)
        analysis_text = url_tool.func(url)
        return {"answer": analysis_text, "mode": "urlbert_analysis"}

    # 2) RAG 시도 (진단 로그 + 완화된 게이팅)
    try:
        rag_out = rag_tool.func(text)
    except Exception as e:
        print(f"[RAG] ERROR calling rag_tool: {e}") 
        rag_out = {}

    print(f"[RAG] raw out: {rag_out}") 
    rag_answer = (rag_out.get("answer") or "").strip() if isinstance(rag_out, dict) else ""
    rag_found  = bool(rag_out.get("found")) if isinstance(rag_out, dict) else False
    sources    = rag_out.get("sources") if isinstance(rag_out, dict) else []
    if sources is None: sources = []
    if not isinstance(sources, list): sources = [str(sources)]

    not_found_message = "찾을 수 없습니다"
    looks_ok = (
        bool(rag_answer) and
        (not_found_message not in rag_answer) and
        (len(sources) > 0 or rag_out.get("max_score", 0) >= 0.2)
    )

    if looks_ok or rag_found:
        # 중복 제거
        seen, uniq = set(), []
        for s in sources:
            if s not in seen:
                seen.add(s)
                uniq.append(s)
        print(f"[RAG] USE RAG, sources={len(uniq)}") 
        return {"answer": rag_answer, "mode": "rag", "sources": uniq[:5]}

    print("[RAG] FALLBACK -> chat") 

    # 3) 일반 대화
    chat_answer = chat_tool.func(text)
    return {"answer": chat_answer, "mode": "chat"}


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

        if mode == "rag":
            print("[RAG 문서 기반 응답]")
        elif mode == "chat":
            print("[일반 Chat 응답]")

        print(f"Bot ▶ Final Answer: {answer}")

        if response.get("sources"):
            print("[출처]")
            for s in response["sources"]:
                print(" -", s)