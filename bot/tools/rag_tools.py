# bot/tools/rag_tools.py

import json
from typing import List, Dict
from langchain.schema import Document
from langchain.text_splitter import RecursiveCharacterTextSplitter
from langchain.embeddings import HuggingFaceEmbeddings
from langchain.vectorstores import FAISS
from langchain.agents import Tool
from langchain.chains import RetrievalQA

def build_rag_index_from_jsonl(
    jsonl_path: str,
    index_path: str,
    chunk_size: int = 800,
    chunk_overlap: int = 200,
    embedding_model: str = "sentence-transformers/all-MiniLM-L6-v2"
):
    """
    1) JSONL 파일을 읽어서  → 2) 텍스트 청크로 분할  → 3) Document 객체로 래핑  
    → 4) FAISS 인덱스 생성 및 디스크에 저장
    """
    # --- 1. JSONL 로드 ---
    entries: List[Dict] = []
    with open(jsonl_path, 'r', encoding='utf-8') as f:
        for line in f:
            entries.append(json.loads(line))
    
    # --- 2. 텍스트 분할 및 Document 생성 ---
    splitter = RecursiveCharacterTextSplitter(
        chunk_size=chunk_size,
        chunk_overlap=chunk_overlap
    )
    docs: List[Document] = []
    for e in entries:
        text = e.get("text", "")
        meta = {
            "title":    e.get("title"),
            "subtitle": e.get("subtitle"),
            "source":   e.get("source")
        }
        for chunk in splitter.split_text(text):
            docs.append(Document(page_content=chunk, metadata=meta))
    
    # --- 3. 임베딩 및 FAISS 생성 ---
    embed = HuggingFaceEmbeddings(model_name=embedding_model)
    db    = FAISS.from_documents(docs, embed)
    
    # --- 4. 디스크에 저장 ---
    db.save_local(index_path)
    print(f"[build_rag_index] FAISS 인덱스 생성 완료: '{index_path}'")


def load_rag_tool(
    index_path: str,
    llm,
    embedding_model: str = "sentence-transformers/all-MiniLM-L6-v2"
) -> Tool:
    """
    FAISS 로컬 인덱스를 로드해서 LangChain RetrievalQA Tool로 감싸 반환합니다.
    runtime 에 이 함수를 호출만 하면 곧바로 RAG 가동 가능.
    """
    # 1) 임베딩 객체 생성
    embed = HuggingFaceEmbeddings(model_name=embedding_model)
    # 2) FAISS 인덱스 로드 (pickle 안전 옵션 활성화)
    db = FAISS.load_local(
        index_path,
        embed,
        allow_dangerous_deserialization=True   # ← 신뢰된 인덱스 로드를 허용
    )
    # 3) RetrievalQA 체인 생성
    qa = RetrievalQA.from_chain_type(
        llm=llm,
        chain_type="stuff",
        retriever=db.as_retriever()
    )
    # 4) LangChain Tool로 감싸서 반환
    return Tool(
        name="SecurityDocsQA",
        func=lambda q: qa({"query": q})["result"],
        description="수집된 보안/큐싱 문서에서 질문을 검색해 요약해 줍니다."
    )
