import re
from transformers import AutoTokenizer, AutoModelForCausalLM, pipeline
from langchain_community.llms import HuggingFacePipeline
from langchain_community.embeddings import HuggingFaceEmbeddings
from langchain_community.vectorstores import FAISS

from langchain_core.agents import initialize_agent, AgentType
from template import general_template, expert_template
from sQanAR.bot.tool import lookup_db_url_tool, analyze_url_tool

# ───────────────────────────────────────────────────────────────────────────────
# 1) 사용할 LLM 설정: 로컬 Llama3 Korean 모델
model_dir = "/home/injeolmi/myproject/sQanAR/llama_cache/models--Bllossom--llama-3.2-Korean-Bllossom-3B/snapshots/e68fbb0d9c2a4031b0d61b14014eac1a4810ac2e"
tokenizer = AutoTokenizer.from_pretrained(model_dir, trust_remote_code=True)
model = AutoModelForCausalLM.from_pretrained(
    model_dir,
    torch_dtype="auto",
    device_map="auto",
    trust_remote_code=True
)
text_gen = pipeline(
    "text-generation",
    model=model,
    tokenizer=tokenizer,
    max_new_tokens=512,
    do_sample=False
)
llm = HuggingFacePipeline(pipeline=text_gen)

# ───────────────────────────────────────────────────────────────────────────────
# 2) FAISS 기반 RAG 설정
embeddings = HuggingFaceEmbeddings(model_name="sentence-transformers/all-MiniLM-L6-v2")
vectorstore = FAISS.load_local(
    "/home/injeolmi/myproject/sQanAR/bot/faiss_index",
    embeddings,
    allow_dangerous_deserialization=True
)
retriever = vectorstore.as_retriever()

# ───────────────────────────────────────────────────────────────────────────────
# 3) LangChain Agent 초기화 (Zero-shot React Description)
tools_list = [lookup_db_url_tool, analyze_url_tool]
agent = initialize_agent(
    tools_list,
    llm,
    agent=AgentType.ZERO_SHOT_REACT_DESCRIPTION,
    verbose=True
)

# ───────────────────────────────────────────────────────────────────────────────
# 4) Agent 실행 함수
def run_agent(question: str, mode: str = "general") -> str:
    # 4-1) URL 추출
    m = re.search(r"https?://[^\s]+", question)
    if not m:
        return "분석할 URL을 포함한 질문을 입력해주세요."
    url = m.group(0)

    # 4-2) 캐시 우선 조회
    cache_json = lookup_db_url_tool.invoke({"url": url})
    if "캐시된 분석 결과가 없습니다" in cache_json:
        cache_json = analyze_url_tool.invoke({"url": url})

    # 4-3) RAG 컨텍스트 생성
    docs = retriever.get_relevant_documents(question)
    context = "\n".join(d.page_content for d in docs[:3]) if docs else ""

    # 4-4) PromptTemplate 적용
    tpl = general_template if mode == "general" else expert_template
    prompt = tpl.format(
        query=question,
        context_documents=context,
        tool_result=cache_json
    )

    # 4-5) 최종 LLM 호출
    return llm(prompt)

# ───────────────────────────────────────────────────────────────────────────────
# 5) CLI 테스트 진입점
if __name__ == "__main__":
    q = input("질문 입력> ")
    print(run_agent(q, mode="general"))
