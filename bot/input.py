import csv
import hashlib
from Server.DB_conn import get_connection

INPUT_CSV = "/home/injeolmi/myproject/sQanAR/bot/urlbert_train.csv"

def ingest_csv(path: str):
    conn = get_connection()
    total = 0
    with open(path, newline="", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for row in reader:
            url        = row["url"].strip()
            header     = row["header_info"].strip() or None
            label_str  = row["label"].strip().lower()
            true_label = 1 if label_str == "malicious" else 0
            is_mal     = true_label

            # URL 해시 계산
            url_hash = hashlib.md5(url.encode("utf-8")).hexdigest()

            # 이미 존재하면 스킵
            with conn.cursor() as cur:
                cur.execute("SELECT 1 FROM urlbert_analysis WHERE url_hash=%s", (url_hash,))
                if cur.fetchone():
                    continue

            # INSERT
            with conn.cursor() as cur:
                sql = """
                INSERT INTO urlbert_analysis
                  (url, url_hash, header_info, is_malicious, confidence, true_label,
                   reason_summary, detailed_explanation)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
                """
                params = (
                    url,
                    url_hash,
                    header,
                    is_mal,     # 모델 예측값
                    None,       # confidence
                    true_label, # 실제 레이블
                    None,       # reason_summary
                    None        # detailed_explanation
                )
                cur.execute(sql, params)
            conn.commit()
            total += 1

    print(f"[완료] 총 {total}개 URL 삽입 완료")

if __name__ == "__main__":
    ingest_csv(INPUT_CSV)
