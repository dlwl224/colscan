import pandas as pd
from Server.DB_conn import get_connection


# 1. CSV 파일 경로
csv_path = "/home/injeolmi/myproject/sQanAR/Server/url_final_enum.csv"

# 2. CSV 읽고 전처리
df = pd.read_csv(csv_path)
df.columns = df.columns.str.strip()  # 컬럼 공백 제거

# 날짜 "Unknown" → None 처리
df["Created Date"] = df["Created Date"].replace("Unknown", None)
df["Expiry Date"] = df["Expiry Date"].replace("Unknown", None)

# 컬럼명 DB 컬럼에 맞게 정리
df.rename(columns={
    "Domain": "domain",
    "Created Date": "created_date",
    "Expiry Date": "expiry_date",
    "Registrar": "registrar",
    "WHOIS Available": "whois_available"
}, inplace=True)

# NaN → None 처리
df = df.where(pd.notnull(df), None)

# 3. DB 연결 및 삽입
conn = get_connection()
try:
    with conn.cursor() as cursor:
        insert_query = """
            INSERT INTO UrlAnalysis (
                url, type, domain, created_date, expiry_date,
                domain_age_days, days_since_creation, registrar, whois_available,
                is_punycode, url_length, domain_length, tld_length, path_length,
                query_length, subdomain_count, char_ratio, digit_ratio, dot_count,
                hyphen_count, slash_count, question_count, has_hash, has_at_symbol,
                https_cert_risk, encoding, contains_port, file_extension, contains_ip,
                phishing_keywords, free_domain, shortened_url, typosquatting, label
            ) VALUES (
                %s, %s, %s, %s, %s,
                %s, %s, %s, %s,
                %s, %s, %s, %s, %s,
                %s, %s, %s, %s, %s,
                %s, %s, %s, %s, %s,
                %s, %s, %s, %s, %s,
                %s, %s, %s, %s, %s
            )
        """
        for row in df.itertuples(index=False):
            try:
                cursor.execute(insert_query, tuple(row))
            except Exception as row_error:
                print("❌ 개별 행 삽입 오류:", row)
                print("⛔ 오류 내용:", row_error)
        conn.commit()
        print("✅ 전체 데이터 삽입 완료")
except Exception as e:
    print("❌ 전체 삽입 중 오류 발생:", e)
finally:
    conn.close()
