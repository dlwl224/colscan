# test_whois.py

import pandas as pd
import whois
import time
import concurrent.futures
from urllib.parse import urlparse
from datetime import datetime

# 날짜 형식을 YYYY-MM-DD로 변환하는 함수
def format_date(date):
    if date in ('Unknown', 'Error', None):
        return 'Unknown'
    if isinstance(date, list):
        date = date[0]
    if isinstance(date, datetime):
        return date.strftime('%Y-%m-%d')
    for fmt in ('%Y-%m-%d', '%Y/%m/%d'):
        try:
            return datetime.strptime(str(date).split()[0], fmt).strftime('%Y-%m-%d')
        except ValueError:
            pass
    return 'Unknown'

# WHOIS 데이터 조회 함수
def get_whois_info(domain):
    """WHOIS 정보를 조회하고 실패 시 재시도 (최대 3회)"""
    for _ in range(3):
        try:
            w = whois.whois(domain)
            return (
                w.creation_date,
                w.expiration_date,
                w.registrar,
                True
            )
        except Exception as e:
            time.sleep(2)
    return None, None, None, False

# 단일 URL에서 WHOIS 피처 추출 함수
def extract_whois_features(url: str) -> dict:
    """
    URL 하나를 받아서 WHOIS 관련 피처를 dict 로 반환합니다.
    """
    parsed = urlparse(url)
    domain = parsed.netloc.split(':')[0].lstrip("www.")
    created, expiry, registrar, available = get_whois_info(domain)
    return {
        "Domain": domain,
        "Created Date": format_date(created),
        "Expiry Date": format_date(expiry),
        "Registrar": registrar,
        "WHOIS Available": available
    }

# ---- 아래부터는 "대량 처리" 스크립트로만 사용할 코드 ----
if __name__ == "__main__":
    input_file  = "/home/injeolmi/myproject/sQanAR/whois_data/output/chunk_10.csv"
    output_file = "/home/injeolmi/myproject/sQanAR/whois_data/dataset/whois_10.csv"

    df = pd.read_csv(input_file)
    if "url" not in df.columns:
        raise ValueError("CSV에 'url' 컬럼이 없습니다.")
    urls = df["url"].tolist()

    with concurrent.futures.ThreadPoolExecutor(max_workers=5) as executor:
        feature_data = list(executor.map(extract_whois_features, urls))

    feature_df = pd.DataFrame(feature_data)
    merged_df  = pd.concat([df, feature_df], axis=1)
    merged_df.to_csv(output_file, index=False)
    print(f"✅ WHOIS 분석 완료 → {output_file}")
