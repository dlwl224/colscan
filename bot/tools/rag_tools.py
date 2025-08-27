# bot/tools/rag_tools.py
import os
import json
import re
from typing import List, Dict

from langchain.schema import Document
from langchain.text_splitter import RecursiveCharacterTextSplitter
from langchain.embeddings import HuggingFaceEmbeddings
from langchain.vectorstores import FAISS
from langchain.agents import Tool
from langchain.chains import RetrievalQA
from langchain_core.prompts import PromptTemplate

# (선택) FAISS 차원 점검용
try:
    import faiss  # type: ignore
    _HAS_FAISS = True
except Exception:
    _HAS_FAISS = False

# RAG 프롬프트 템플릿 (한국어)
RAG_PROMPT_TEMPLATE = """
당신은 한국어 보안 전문가 챗봇입니다. 다음 정보를 사용하여 질문에 답변하세요.
모든 답변은 친절하고 이해하기 쉬운 한국어 대화체로 작성해 주세요.
주어진 정보에서 답변을 찾을 수 없다면 "해당 정보는 문서에서 찾을 수 없습니다."라고 답하세요.

Context:
{context}

Question: {question}
Answer in Korean:
"""

def build_rag_index_from_jsonl(
    jsonl_path: str,
    index_path: str,
    chunk_size: int = 800,
    chunk_overlap: int = 200,
    embedding_model: str = "jhgan/ko-sroberta-multitask",
    device: str = "cuda",
):
    """
    1) JSONL 로드 → 2) 텍스트 청크 분할 → 3) Document 생성 → 4) FAISS 인덱스 저장
    """
    entries: List[Dict] = []
    with open(jsonl_path, "r", encoding="utf-8") as f:
        for line in f:
            if line.strip():
                entries.append(json.loads(line))

    splitter = RecursiveCharacterTextSplitter(
        chunk_size=chunk_size, chunk_overlap=chunk_overlap
    )

    docs: List[Document] = []
    for e in entries:
        text = e.get("text", "") or ""
        meta = {
            "title": e.get("title"),
            "subtitle": e.get("subtitle"),
            "source": e.get("source"),
        }
        for chunk in splitter.split_text(text):
            docs.append(Document(page_content=chunk, metadata=meta))

    os.makedirs(index_path, exist_ok=True)

    embed = HuggingFaceEmbeddings(
        model_name=embedding_model, model_kwargs={"device": device}
    )
    db = FAISS.from_documents(docs, embed)
    db.save_local(index_path)
    print(f"[build_rag_index] FAISS 인덱스 생성 완료: '{index_path}'")


def load_rag_tool(
    index_path: str,
    llm,
    embedding_model: str = "jhgan/ko-sroberta-multitask",
    device: str = "cuda",
) -> Tool:
    """
    로컬 FAISS 인덱스를 로드해 RetrievalQA 체인을 만들고,
    Tool.func이 {"answer","sources","found"} 딕셔너리를 반환하도록 구성.
    """
    try:
        embeddings = HuggingFaceEmbeddings(
            model_name=embedding_model, model_kwargs={"device": device}
        )

        faiss_index = FAISS.load_local(
            index_path,
            embeddings,
            allow_dangerous_deserialization=True,
        )

        # (선택) 인덱스 차원-모델 차원 점검
        if _HAS_FAISS and hasattr(faiss_index, "index"):
            try:
                idx_dim = faiss_index.index.d
                # sentence-transformers 기반이면 아래 속성이 존재
                emb_dim = embeddings.client.get_sentence_embedding_dimension()
                if idx_dim != emb_dim:
                    raise ValueError(
                        f"FAISS index dim({idx_dim}) != embedding model dim({emb_dim}). "
                        f"현재 임베딩 모델({embedding_model})로 인덱스를 재생성하세요."
                    )
            except Exception:
                # 모델 유형에 따라 get_sentence_embedding_dimension 없을 수 있음 → 스킵
                pass

        retriever = faiss_index.as_retriever()
        rag_prompt = PromptTemplate(
            template=RAG_PROMPT_TEMPLATE, input_variables=["context", "question"]
        )

        qa_chain = RetrievalQA.from_chain_type(
            llm=llm,
            chain_type="stuff",
            retriever=retriever,
            return_source_documents=True,
            chain_type_kwargs={"prompt": rag_prompt},
        )

        def rag_qa_function(query: str) -> Dict:
            """
            보안 문서 기반 질의응답.
            반환: {"answer": str, "sources": List[str], "found": bool}
            """
            result = qa_chain.invoke({"query": query})  # {'result','source_documents',...}
            answer = (
                result.get("result")
                or result.get("answer")
                or ""
            ).strip()

            # 불필요한 프롬프트 잔여 문자열/중복 구두점 정리
            answer = re.sub(r"^(Answer in Korean:)", "", answer, flags=re.MULTILINE).strip()
            answer = re.sub(r"\s*\.{2,}\s*", ".", answer).strip()

            sources: List[str] = []
            for d in (result.get("source_documents") or []):
                meta = getattr(d, "metadata", {}) or {}
                s = meta.get("source") or ""
                if s:
                    sources.append(s)

            found = bool(answer)
            return {"answer": answer, "sources": sources, "found": found}

        return Tool(
            name="SecurityDocsQA",
            func=rag_qa_function,
            description="보안 문서에서 질문에 답변합니다. 큐싱, 피싱, SSL 등 보안 개념/사례/가이드를 검색해 한국어로 제공합니다.",
        )

    except Exception as e:
        err_msg = str(e)
        print(f"❌ RAG Tool 로드 중 오류 발생: {err_msg}")
        return Tool(
            name="SecurityDocsQA",
            func=lambda x, _err=err_msg: {
                "found": False,
                "answer": f"RAG 툴 로드 중 오류 발생: {_err}. 기능을 사용할 수 없습니다.",
                "sources": [],
            },
            description="보안 문서에서 질문에 답변합니다 (현재 비활성화됨).",
        )
