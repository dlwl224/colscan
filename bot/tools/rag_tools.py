# bot/tools/rag_tools.py
import os
import json
import re # 추가
from typing import List, Dict
from langchain.schema import Document
from langchain.text_splitter import RecursiveCharacterTextSplitter
from langchain.embeddings import HuggingFaceEmbeddings
from langchain.vectorstores import FAISS
from langchain.agents import Tool
from langchain.chains import RetrievalQA
from langchain_core.prompts import PromptTemplate # 추가

# RAG 프롬프트 템플릿 정의 (한국어 답변 명시)
RAG_PROMPT_TEMPLATE = """
당신은 한국어 보안 전문가 챗봇입니다. 다음 정보를 사용하여 질문에 답변하세요.
모든 답변은 친절하고 이해하기 쉬운 한국어 대화체로 작성해 주세요.
주어진 정보에서 답변을 찾을 수 없다면 "해당 정보는 문서에서 찾을 수 없습니다."라고 답하세요.

Context:
{context}

Question: {question}
Answer in Korean:""" # 한국어로 답변하라는 지시 추가

def build_rag_index_from_jsonl(
    jsonl_path: str,
    index_path: str, # save_path 대신 index_path 사용
    chunk_size: int = 800,
    chunk_overlap: int = 200,
    embedding_model: str = "jhgan/ko-sroberta-multitask",
    device: str = "cuda"
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

    # 수정: save_path 대신 index_path 사용
    if not os.path.exists(index_path):
        os.makedirs(index_path)
    
    # --- 3. 임베딩 및 FAISS 생성 ---
    embed = HuggingFaceEmbeddings(model_name=embedding_model, model_kwargs={"device": device}) # device 인자 전달
    db = FAISS.from_documents(docs, embed)
    
    # --- 4. 디스크에 저장 ---
    db.save_local(index_path)
    print(f"[build_rag_index] FAISS 인덱스 생성 완료: '{index_path}'")


def load_rag_tool(
    index_path: str,
    llm,
    embedding_model: str = "jhgan/ko-sroberta-multitask",
    device: str = "cuda"
) -> Tool:
    """
    FAISS 로컬 인덱스를 로드해서 LangChain RetrievalQA Tool로 감싸 반환합니다.
    runtime 에 이 함수를 호출만 하면 곧바로 RAG 가동 가능.
    """
    try:
        # 1) 임베딩 객체 생성
        embeddings = HuggingFaceEmbeddings(model_name=embedding_model, model_kwargs={"device": device})
        # 2) FAISS 인덱스 로드 (pickle 안전 옵션 활성화)
        faiss_index = FAISS.load_local(
            index_path,
            embeddings,
            allow_dangerous_deserialization=True   # ← 신뢰된 인덱스 로드를 허용
        )
        # 3) RetrievalQA 체인 생성
        retriever=faiss_index.as_retriever()
        
        # RAG 프롬프트 템플릿 적용
        rag_prompt = PromptTemplate(template=RAG_PROMPT_TEMPLATE, input_variables=["context", "question"])

        qa_chain = RetrievalQA.from_chain_type(
            llm=llm,
            chain_type="stuff",
            retriever=retriever,
            prompt=rag_prompt, # 정의한 RAG 프롬프트 적용
            return_source_documents=False # 소스 문서 반환 여부는 필요에 따라 설정
        )
        
        def rag_qa_function(query: str) -> str:
            """보안 문서에서 질문에 답변합니다. 피싱, SSL, 랜섬웨어, 포렌식, 인시던트, 취약점 등 보안 관련 개념 설명이나 문서 검색에 사용합니다."""
            result = qa_chain.invoke({"query": query})
            # LangChain 0.1.0 이후부터 invoke 결과는 딕셔너리이며, 'result' 또는 'answer' 키에 답변이 있음
            answer = result.get("result", result.get("answer", "죄송합니다. 해당 정보는 문서에서 찾을 수 없습니다."))
            
            # RAG 답변에 대한 추가적인 후처리 (불필요한 영어나 형식 제거)
            answer = answer.strip()
            # "Answer in Korean:"과 같은 프롬프트 지시어가 포함될 경우 제거
            answer = re.sub(r"^(Answer in Korean:)", "", answer, flags=re.MULTILINE).strip()
            # 불필요한 반복 문자열 제거
            answer = re.sub(r'\.{3,}', '.', answer).strip()
            answer = re.sub(r'\s*\.{2,}\s*', '.', answer).strip()
            
            return answer

        # 4) LangChain Tool로 감싸서 반환
        return Tool(
            name="SecurityDocsQA",
            func=rag_qa_function, # 함수 이름 변경
            description="보안 문서에서 질문에 답변합니다. 피싱, SSL, 랜섬웨어, 포렌식, 인시던트, 취약점 등 보안 관련 개념 설명이나 문서 검색에 사용합니다. 모든 답변은 한국어로 제공합니다."
        )
    except Exception as e:
        print(f"RAG Tool 로드 중 오류 발생: {e}")
        return Tool(
            name="SecurityDocsQA",
            func=lambda x: f"RAG 툴 로드 중 오류 발생: {e}. 기능을 사용할 수 없습니다.",
            description="보안 문서에서 질문에 답변합니다 (현재 비활성화됨)."
        )