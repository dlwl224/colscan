# bot/tools/rag_tools.py

from langchain.agents import Tool
from langchain.embeddings import HuggingFaceEmbeddings
from langchain.vectorstores import FAISS
from langchain.chains import RetrievalQA

def load_rag_tool(index_path: str, llm) -> Tool:
    """
    FAISS 로컬 인덱스를 로드해서 LangChain RetrievalQA Tool로 감싸 반환합니다.
    :param index_path: build_index() 로 만든 인덱스 폴더 경로
    :param llm: LangChain LLM 인스턴스 (예: LlamaCpp)
    """
    embed = HuggingFaceEmbeddings(model_name="sentence-transformers/all-MiniLM-L6-v2")
    db    = FAISS.load_local(index_path, embed)
    qa    = RetrievalQA.from_chain_type(
        llm=llm,
        chain_type="stuff",
        retriever=db.as_retriever()
    )
    return Tool(
        name="SecurityDocsQA",
        func=lambda q: qa({"query": q}),
        description="수집된 보안 문서에서 질문을 검색해 요약해 줍니다."
    )
