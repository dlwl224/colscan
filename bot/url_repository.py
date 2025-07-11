import os
import pymysql
from pathlib import Path
from dotenv import load_dotenv

# ─── 환경 변수 로드 ───
project_root = Path(__file__).parent
load_dotenv(project_root / "db.env")

DB_HOST     = os.getenv("DB_HOST")
DB_USER     = os.getenv("DB_USER")
DB_PASSWORD = os.getenv("DB_PASSWORD")
DB_NAME     = os.getenv("DB_NAME")

def get_db_connection():
    return pymysql.connect(
        host=DB_HOST, user=DB_USER, password=DB_PASSWORD,
        db=DB_NAME, charset="utf8mb4",
        cursorclass=pymysql.cursors.DictCursor
    )

def bool_to_int(v):
    if v is True:  return 1
    if v is False: return 0
    return None

# ─── 1) 캐시된 분석 결과 조회 ───
def lookup_db_url(url: str) -> dict | None:
    """
    UrlAnalysis에서 가장 최근 분석 결과 한 건을 가져옵니다.
    반환 dict 키는 테이블 컬럼명과 동일합니다.
    """
    conn = get_db_connection()
    try:
        with conn.cursor() as cur:
            sql = """
            SELECT *
              FROM UrlAnalysis
             WHERE url = %s
             ORDER BY id DESC
             LIMIT 1;
            """
            cur.execute(sql, (url,))
            return cur.fetchone()
    finally:
        conn.close()

# ─── 2) 원시 피처 저장(또는 업데이트) ───
def save_raw_features(raw: dict):
    """
    UrlFeatureRaw 테이블에 INSERT 하거나 URL이 이미 있으면 UPDATE 합니다.
    raw 딕셔너리 키는 컬럼명과 동일해야 합니다(ex: domain_age_days, whois_available 등).
    """
    conn = get_db_connection()
    try:
        cols = []
        vals = []
        placeholders = []
        updates = []
        for col, val in raw.items():
            cols.append(col)
            placeholders.append("%s")
            # boolean 컬럼 1/0 변환
            if isinstance(val, bool):
                vals.append(bool_to_int(val))
            else:
                vals.append(val)
            updates.append(f"{col}=VALUES({col})")

        sql = f"""
        INSERT INTO UrlFeatureRaw ({', '.join(cols)})
        VALUES ({', '.join(placeholders)})
        ON DUPLICATE KEY UPDATE
          {', '.join(updates)};
        """
        with conn.cursor() as cur:
            cur.execute(sql, vals)
        conn.commit()
    finally:
        conn.close()

# ─── 3) 분석 결과 저장 ───
def save_analysis(url: str, raw: dict, label: str,
                  proba_safe: float, proba_warn: float, proba_mal: float):
    """
    UrlAnalysis에 분석 로그를 저장합니다.
    raw 딕셔너리의 일부 컬럼들은 UrlAnalysis에도 중복 저장합니다.
    """
    # 우선 Raw features 저장
    save_raw_features(raw)

    conn = get_db_connection()
    try:
        with conn.cursor() as cur:
            sql = """
            INSERT INTO UrlAnalysis (
                url, type, domain, created_date, expiry_date,
                domain_age_days, days_since_creation, registrar, whois_available,
                is_punycode, url_length, domain_length, tld_length,
                path_length, query_length, subdomain_count, char_ratio,
                digit_ratio, dot_count, hyphen_count, slash_count,
                question_count, has_hash, has_at_symbol, is_https,
                cert_total_days, cert_issuer, encoding, contains_port,
                file_extension, contains_ip, phishing_keywords,
                free_domain, shortened_url, typosquatting,
                label, predicted_proba_safe, predicted_proba_warning, predicted_proba_malicious
            ) VALUES (
                %(url)s, %(type)s, %(domain)s, %(created_date)s, %(expiry_date)s,
                %(domain_age_days)s, %(days_since_creation)s, %(registrar)s, %(whois_available)s,
                %(is_punycode)s, %(url_length)s, %(domain_length)s, %(tld_length)s,
                %(path_length)s, %(query_length)s, %(subdomain_count)s, %(char_ratio)s,
                %(digit_ratio)s, %(dot_count)s, %(hyphen_count)s, %(slash_count)s,
                %(question_count)s, %(has_hash)s, %(has_at_symbol)s, %(is_https)s,
                %(cert_total_days)s, %(cert_issuer)s, %(encoding)s, %(contains_port)s,
                %(file_extension)s, %(contains_ip)s, %(phishing_keywords)s,
                %(free_domain)s, %(shortened_url)s, %(typosquatting)s,
                %(label)s, %(proba_safe)s, %(proba_warn)s, %(proba_mal)s
            );
            """
            params = raw.copy()
            params.update({
                "url": url,
                "label": label,
                "proba_safe": proba_safe,
                "proba_warn": proba_warn,
                "proba_mal": proba_mal,
            })
            # boolean 칼럼 재변환
            for bcol in ["whois_available","is_punycode","has_hash","has_at_symbol",
                         "is_https","contains_port","contains_ip","phishing_keywords",
                         "free_domain","shortened_url","typosquatting"]:
                if bcol in params:
                    params[bcol] = bool_to_int(params[bcol])
            cur.execute(sql, params)
        conn.commit()
    finally:
        conn.close()
