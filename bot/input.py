#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
두 CSV(test/train) -> MySQL urlbert_analysis 적재
- CSV 컬럼: text, label
- text = "<url> [SEP] <header_info>"
- label -> true_label, is_malicious 에 저장
- url_hash = MD5(url); 충돌 시 url+"#i"로 재해시
"""

import os
import sys
import hashlib
import pandas as pd
from typing import Optional, Tuple

# ✅ project 루트(/home/injeolmi/project)를 sys.path에 추가
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from Server.DB_conn import get_connection

# === 설정 ===
CSV_PATHS = [
    "/home/injeolmi/project/bot/test_dataset.csv",
    "/home/injeolmi/project/bot/train_dataset.csv",
]
BATCH_SIZE = 500
TABLE = "urlbert_analysis"

def parse_text_field(text: str) -> Tuple[str, Optional[str]]:
    if text is None:
        return "", None
    parts = str(text).split("[SEP]")
    url = parts[0].strip() if parts else ""
    header = parts[1].strip() if len(parts) > 1 else None
    return url, header

def normalize_label(val) -> Optional[int]:
    if val is None:
        return None
    s = str(val).strip().lower()
    if s in {"0", "normal", "legitimate", "benign", "safe"}:
        return 0
    if s in {"1", "malicious", "phishing", "bad", "danger"}:
        return 1
    try:
        n = int(float(s))
        return 0 if n == 0 else 1 if n == 1 else None
    except:
        return None

def compute_noncolliding_hash(conn, url: str) -> str:
    """MD5(url) 충돌 시 url+'#i'로 재시도하여 유일한 hash 생성"""
    suffix = 0
    while True:
        base = url if suffix == 0 else f"{url}#{suffix}"
        url_hash = hashlib.md5(base.encode("utf-8")).hexdigest()
        with conn.cursor() as cur:
            cur.execute(f"SELECT url FROM {TABLE} WHERE url_hash=%s", (url_hash,))
            row = cur.fetchone()
        if not row:
            return url_hash
        # 동일 url이면 호출부에서 skip할 것이므로 해시 유니크 확보 위해 계속 시도
        if row["url"] == url:
            suffix += 1
            continue
        suffix += 1  # 다른 URL과 충돌 → 재시도

def insert_rows_from_csv(conn, csv_path: str, batch_size: int = 500):
    print(f"\n[LOAD] {csv_path}")
    if not os.path.exists(csv_path):
        print(f"  - 파일 없음: {csv_path} → 건너뜀")
        return

    df = pd.read_csv(csv_path)
    if "text" not in df.columns or "label" not in df.columns:
        raise ValueError(f"{csv_path}는 'text'와 'label' 컬럼이 필요합니다.")

    inserted = skipped_same = skipped_bad = collisions = 0
    batch = []

    for _, r in df.iterrows():
        url, header_info = parse_text_field(r["text"])
        tl = normalize_label(r["label"])

        if not url or tl is None:
            skipped_bad += 1
            continue

        raw_hash = hashlib.md5(url.encode("utf-8")).hexdigest()
        with conn.cursor() as cur:
            cur.execute(f"SELECT url FROM {TABLE} WHERE url_hash=%s", (raw_hash,))
            hit = cur.fetchone()

        if hit:
            if hit["url"] == url:
                skipped_same += 1
                continue
            # (희귀) 다른 URL과 해시 충돌
            collisions += 1
            url_hash = compute_noncolliding_hash(conn, url)
        else:
            url_hash = raw_hash

        # confidence는 NULL 유지
        batch.append((url, url_hash, header_info, tl, None, tl))

        if len(batch) >= batch_size:
            with conn.cursor() as cur:
                cur.executemany(
                    f"""
                    INSERT INTO {TABLE}
                      (url, url_hash, header_info, is_malicious, confidence, true_label)
                    VALUES (%s,  %s,       %s,          %s,           %s,        %s)
                    """,
                    batch
                )
            conn.commit()
            inserted += len(batch)
            print(f"  - 진행: inserted={inserted}, skipped_same={skipped_same}, skipped_bad={skipped_bad}, collisions={collisions}")
            batch.clear()

    if batch:
        with conn.cursor() as cur:
            cur.executemany(
                f"""
                INSERT INTO {TABLE}
                  (url, url_hash, header_info, is_malicious, confidence, true_label)
                VALUES (%s,  %s,       %s,          %s,           %s,        %s)
                """,
                batch
            )
        conn.commit()
        inserted += len(batch)

    print(f"[DONE] inserted={inserted}, skipped_same={skipped_same}, skipped_bad={skipped_bad}, collisions={collisions}")

def main():
    conn = get_connection()
    try:
        for p in CSV_PATHS:
            insert_rows_from_csv(conn, p, BATCH_SIZE)
    finally:
        try:
            conn.commit()
        except:
            pass
        conn.close()

if __name__ == "__main__":
    main()
