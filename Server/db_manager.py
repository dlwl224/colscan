import json
import hashlib
from Server.DB_conn import get_connection


def get_url_info_from_db(url: str) -> dict | None:
    """
    url_analysis 테이블에서 풀 분석 결과가 있으면 dict 반환, 없으면 None.
    반환 dict 키:
      - url:str
      - is_malicious:int
      - legitimate_probability:float
      - malicious_probability:float
      - reasons:list
      - mapped_features:dict
      - analysis_date:datetime
    """
    sql = """
    SELECT
      url,
      is_malicious,
      legitimate_probability,
      malicious_probability,
      reasons,
      mapped_features,
      analysis_date
    FROM url_analysis
    WHERE url = %s;
    """
    conn = get_connection()
    with conn.cursor() as cur:
        cur.execute(sql, (url,))
        return cur.fetchone()


def get_raw_summary_from_db(url: str) -> dict | None:
    """
    UrlFeatureRaw 테이블에서 URL이 존재하면,
    원시 피처 중 일부를 요약하여 dict 반환, 없으면 None.
    반환 dict 키:
      - url:str
      - type:str
      - url_length:int
      - domain_age_days:int
    """
    sql = """
    SELECT
      url,
      type,
      url_length,
      domain_age_days
    FROM UrlFeatureRaw
    WHERE url = %s;
    """
    conn = get_connection()
    with conn.cursor() as cur:
        cur.execute(sql, (url,))
        row = cur.fetchone()
    if not row:
        return None
    return {
        "url": row["url"],
        "type": row["type"],
        "url_length": row["url_length"],
        "domain_age_days": row["domain_age_days"]
    }


def save_raw_features_to_db(features: dict):
    """
    UrlFeatureRaw 테이블에 raw feature dict를 INSERT 또는 UPDATE.
    features dict의 키는 UrlFeatureRaw 컬럼명과 일치해야 합니다.
    """
    cols = [
        "url","type","domain","created_date","expiry_date",
        "domain_age_days","days_since_creation","registrar","whois_available",
        "is_punycode","url_length","domain_length","tld_length",
        "path_length","query_length","subdomain_count","char_ratio",
        "digit_ratio","dot_count","hyphen_count","slash_count",
        "question_count","has_hash","has_at_symbol","is_https",
        "cert_total_days","cert_issuer","encoding","contains_port",
        "file_extension","contains_ip","phishing_keywords","free_domain",
        "shortened_url","typosquatting"
    ]
    placeholders = ", ".join(["%s"] * len(cols))
    update_clause = ", ".join([f"{c}=VALUES({c})" for c in cols])
    sql = f"""
    INSERT INTO UrlFeatureRaw ({', '.join(cols)})
    VALUES ({placeholders})
    ON DUPLICATE KEY UPDATE
      {update_clause};
    """
    params = []
    for c in cols:
        v = features.get(c)
        # 'Unknown' 문자열은 NULL로 바꾸기 (DATE 컬럼 처리용)
        if isinstance(v, str) and v == "Unknown":
            v = None
        # datetime → ISO 문자열
        if hasattr(v, "isoformat"):
            v = v.isoformat()
        # bool → 0 또는 1
        if isinstance(v, bool):
            v = int(v)
        params.append(v)


    # Log before save
    print(f"▶ save_raw_features_to_db 호출됨: URL={features.get('url')}")
    conn = get_connection()
    with conn.cursor() as cur:
        cur.execute(sql, params)
        # Log after save
        print(f"✅ UrlFeatureRaw 삽입/업데이트 완료: URL={features.get('url')}")
    conn.commit()


def save_url_analysis_to_db(analysis: dict):
    """
    url_analysis 테이블에 analysis dict를 INSERT 또는 UPDATE.
    analysis dict 키:
      - url (str)
      - is_malicious (bool or int)
      - legitimate_probability (float)
      - malicious_probability (float)
      - reasons (list)
      - mapped_features (dict)
    """
    url = analysis["url"]
    is_mal = int(analysis["is_malicious"])
    leg_p  = float(analysis.get("legitimate_probability", 0.0))
    mal_p  = float(analysis.get("malicious_probability", 0.0))
    reasons_json      = json.dumps(analysis["reasons"], ensure_ascii=False)
    mapped_json       = json.dumps(analysis["mapped_features"], ensure_ascii=False)

    # Log before save
    print(f"▶ save_url_analysis_to_db 호출됨: URL={url}")
    sql = """
    INSERT INTO url_analysis
      (url, is_malicious, legitimate_probability, malicious_probability, reasons, mapped_features)
    VALUES (%s, %s, %s, %s, %s, %s)
    ON DUPLICATE KEY UPDATE
      is_malicious = VALUES(is_malicious),
      legitimate_probability = VALUES(legitimate_probability),
      malicious_probability = VALUES(malicious_probability),
      reasons = VALUES(reasons),
      mapped_features = VALUES(mapped_features),
      analysis_date = CURRENT_TIMESTAMP;
    """
    params = (url, is_mal, leg_p, mal_p, reasons_json, mapped_json)
    conn = get_connection()
    with conn.cursor() as cur:
        cur.execute(sql, params)
        # Log after save
        print(f"✅ url_analysis 삽입/업데이트 완료: URL={url}")
    conn.commit()




def get_urlbert_info_from_db(url: str) -> dict | None:
    """
    urlbert_analysis 테이블에서 해당 URL이 있으면 row dict 반환, 없으면 None.
    반환 dict 키:
      - url (str)
      - header_info (str|None)
      - is_malicious (int)
      - confidence (float|None)
      - true_label (int|None)
      - reason_summary (str|None)
      - detailed_explanation (str|None)
      - analysis_date (datetime)
    """
    sql = """
    SELECT
      url,
      header_info,
      is_malicious,
      confidence,
      true_label,
      reason_summary,
      detailed_explanation,
      analysis_date
    FROM urlbert_analysis
    WHERE url_hash = MD5(%s)
    """
    conn = get_connection()
    with conn.cursor() as cur:
        cur.execute(sql, (url,))
        return cur.fetchone()


# ② urlbert 전용 저장 함수
def save_urlbert_to_db(record: dict):
    """
    urlbert_analysis 테이블에 INSERT 또는 UPDATE.
    record dict 키:
      - url (str)
      - header_info (str|None)
      - is_malicious (int)
      - confidence (float|None)
      - true_label (int|None)
      - reason_summary (str|None)
      - detailed_explanation (str|None)
    """
    url         = record["url"]
    url_hash    = hashlib.md5(url.encode("utf-8")).hexdigest()
    header_info = record.get("header_info")
    is_mal      = int(record["is_malicious"])
    conf        = record.get("confidence")
    true_lbl    = record.get("true_label")
    summary     = record.get("reason_summary")
    detail      = record.get("detailed_explanation")

    sql = """
    INSERT INTO urlbert_analysis
      (url, url_hash, header_info, is_malicious, confidence, true_label,
       reason_summary, detailed_explanation)
    VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
    ON DUPLICATE KEY UPDATE
      header_info          = VALUES(header_info),
      is_malicious         = VALUES(is_malicious),
      confidence           = VALUES(confidence),
      true_label           = VALUES(true_label),
      reason_summary       = VALUES(reason_summary),
      detailed_explanation = VALUES(detailed_explanation),
      analysis_date        = CURRENT_TIMESTAMP
    """
    params = (
        url, url_hash, header_info, is_mal, conf, true_lbl, summary, detail
    )

    conn = get_connection()
    with conn.cursor() as cur:
        cur.execute(sql, params)
    conn.commit()
    print(f"✅ urlbert_analysis 저장/업데이트 완료: {url}")

