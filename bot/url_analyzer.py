from bot.extract_features import build_raw_features, predict_url
from bot.reprocess import convert_to_risk_levels
import pandas as pd


def generate_reasons(raw_feats: dict, mapped_feats: dict) -> list[str]:
    """
    규칙 기반으로 '왜 위험한지' 설명 리스트를 생성합니다.
    각 피처의 실제 값을 포함해 구체적인 메시지를 생성할 수 있습니다.
    """
    reasons = []
    # 도메인 생성일
    domain_age = raw_feats.get("domain_age_days")
    if domain_age is not None:
        if domain_age < 30:
            reasons.append(f"도메인 생성 후 {domain_age}일 밖에 지나지 않아 신규 도메인입니다.")
        elif domain_age < 180:
            reasons.append(f"도메인 생성 후 {domain_age}일이 경과했지만, 아직 신규 도메인입니다.")
    # HTTPS 적용 여부
    is_https = raw_feats.get("is_https")
    if is_https is not None and is_https == 0:
        reasons.append("HTTPS가 적용되어 있지 않습니다. 안전한 통신이 보장되지 않습니다.")
    # 해시(#) 포함 횟수
    hash_count = raw_feats.get("has_hash")
    if isinstance(hash_count, int) and hash_count > 0:
        reasons.append(f"URL에 '#' 문자가 {hash_count}개 포함되어 있습니다. 피싱 URL에 자주 사용됩니다.")
    # URL 길이
    url_len = raw_feats.get("url_length")
    if isinstance(url_len, int) and url_len > 200:
        reasons.append(f"URL 길이가 {url_len}자로 매우 깁니다. 비정상적인 패턴일 수 있습니다.")
    # 단축 URL 여부
    shortened = raw_feats.get("shortened_url")
    if shortened is not None and shortened == 1:
        reasons.append("단축 URL 서비스를 사용하고 있습니다. 원본 URL 확인이 어렵습니다.")
    # 피싱 키워드
    if mapped_feats.get("phishing_keywords") == 1:
        reasons.append("피싱 의심 키워드가 포함되어 있습니다.")
    # 타이포스쿼팅
    if mapped_feats.get("typosquatting") == 1:
        reasons.append("타이포스쿼팅(오타 도메인) 가능성이 있습니다.")
    return reasons


def analyze_url_entrypoint(url: str) -> dict:
    """
    URL을 분석하여 dict 반환:
      - url, is_malicious, legitimate_probability,
        malicious_probability, reasons, raw_features, mapped_features
    """
    # 1. 원시 피처 추출
    df_raw = build_raw_features(url)
    raw_feats = df_raw.iloc[0].apply(lambda x: None if pd.isna(x) else x).to_dict()

    # 2. 리스크 매핑
    for col in ["domain_age_days", "days_since_creation", "cert_total_days"]:
        if col in df_raw:
            df_raw[col] = df_raw[col].fillna(0)
    df_mapped = convert_to_risk_levels(df_raw)
    mapped_feats = df_mapped.iloc[0].to_dict()

    # 3. 예측
    label, mal_prob, leg_prob, _ = predict_url(url)

    # 4. 판단 근거
    reasons = generate_reasons(raw_feats, mapped_feats)

    # 5. 결과 조립
    return {
        "url": url,
        "is_malicious": bool(label),
        "legitimate_probability": leg_prob,
        "malicious_probability": mal_prob,
        "reasons": reasons,
        "raw_features": raw_feats,
        "mapped_features": mapped_feats
    }


# Example
if __name__ == "__main__":
    import pprint
    res = analyze_url_entrypoint(input("URL> "))
    pprint.pprint(res)
