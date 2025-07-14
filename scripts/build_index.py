# scripts/build_index.py
from bot.tools.rag_tools import build_rag_index_from_jsonl

if __name__ == "__main__":
    JSONL      = "data/rag_dataset.jsonl"
    INDEX_DIR  = "security_faiss_index"
    CHUNK_SIZE = 800
    OVERLAP    = 200

    build_rag_index_from_jsonl(
        jsonl_path   = JSONL,
        index_path   = INDEX_DIR,
        chunk_size   = CHUNK_SIZE,
        chunk_overlap= OVERLAP
    )
    print(f"[완료] FAISS 인덱스가 '{INDEX_DIR}'에 생성되었습니다.")
