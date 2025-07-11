
import os
import pandas as pd
from typing import List, Tuple, Dict, Iterable

from langchain.embeddings import HuggingFaceEmbeddings
from langchain.vectorstores import FAISS
from langchain.docstore.document import Document


def read_documents(
    csv_path: str,
    content_col: str = "content",
    topic_col: str = "topic",
    source_col: str = "source"
) -> List[Tuple[str, Dict[str, str]]]:
    """
    CSV 파일에서 문서를 읽어 (text, metadata) 튜플 리스트로 변환합니다.

    :param csv_path: 문서가 저장된 CSV 파일 경로
    :param content_col: 본문 텍스트 컬럼명
    :param topic_col: 소주제 키 컬럼명
    :param source_col: 문서 출처 컬럼명
    :return: [(text, {"topic":..., "source":...}), ...]
    """
    df = pd.read_csv(csv_path)
    docs: List[Tuple[str, Dict[str, str]]] = []
    for _, row in df.iterrows():
        text = row[content_col]
        meta = {"topic": row[topic_col], "source": row[source_col]}
        docs.append((text, meta))
    return docs


def chunk_text(
    text: str,
    chunk_size: int = 1000,
    chunk_overlap: int = 200
) -> List[str]:
    """
    긴 텍스트를 chunk_size 길이로 분할하고, chunk_overlap 만큼 중첩하여 슬라이딩합니다.
    """
    chunks: List[str] = []
    start = 0
    length = len(text)
    while start < length:
        end = min(start + chunk_size, length)
        chunks.append(text[start:end])
        start = max(end - chunk_overlap, 0)
    return chunks


def get_embedding_model(
    model_name: str = "sentence-transformers/all-MiniLM-L6-v2",
    device: str = "cpu"
) -> HuggingFaceEmbeddings:
    """
    HuggingFaceEmbeddings 래퍼를 생성합니다.
    로컬 transformers 사용 (login/토큰 불필요).
    """
    return HuggingFaceEmbeddings(
        model_name=model_name,
        model_kwargs={"device": device}
    )


def build_index(
    csv_path: str,
    index_path: str,
    model_name: str = "sentence-transformers/all-MiniLM-L6-v2",
    chunk_size: int = 1000,
    chunk_overlap: int = 200,
    device: str = "cpu"
) -> None:
    """
    1) CSV에서 문서 읽기
    2) 텍스트 청크 분할 → Document 객체 생성
    3) Embedding → FAISS 인덱스 생성
    4) 로컬에 인덱스 저장

    :param csv_path: 소스 CSV 경로
    :param index_path: 저장할 FAISS 인덱스 디렉터리
    """
    # 1) 문서 로드
    docs = read_documents(csv_path)

    # 2) 청크화 & Document 생성
    docs_chunks: List[Document] = []
    for text, meta in docs:
        for i, chunk in enumerate(chunk_text(text, chunk_size, chunk_overlap)):
            m = meta.copy()
            m["chunk_index"] = i
            docs_chunks.append(Document(page_content=chunk, metadata=m))

    # 3) Embedding 모델 준비
    embed_model = get_embedding_model(model_name=model_name, device=device)

    # 4) FAISS 인덱스 생성 및 저장
    store = FAISS.from_documents(docs_chunks, embed_model)
    os.makedirs(index_path, exist_ok=True)
    store.save_local(index_path)
    print(f"✅ FAISS 인덱스가 '{index_path}'에 저장되었습니다.")


if __name__ == "__main__":
    # 예시: security_docs.csv → 'security_faiss_index' 폴더에 인덱스 저장
    build_index(
        csv_path="security_docs.csv",
        index_path="security_faiss_index",
        model_name="sentence-transformers/all-MiniLM-L6-v2",
        chunk_size=800,
        chunk_overlap=200,
        device="cpu"
    )

