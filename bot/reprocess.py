import pandas as pd



# # 신뢰할 수 있는 인증 기관 리스트
# trusted_issuers = [
#     "Google Trust Services LLC", "DigiCert", "Microsoft Azure",
#     "Amazon", "Sectigo Limited", "GlobalSign", "GoDaddy.com", "Apple" 
# ]
#"Let's Encrypt"

def classify_https_security(row):
    is_https = row['is_https']
    days = row['cert_total_days']
    issuer = row['cert_issuer']
    
    if is_https == 0 or (is_https == 1 and (pd.isna(issuer) or issuer.strip() == '')):
        return 1 # 위험
    elif is_https == 1 and days <= 100:
        return 0  # 주의
    elif is_https == 1 and (issuer.strip() != '') and days > 100:
    # else:
        return -1  # 안전

# 4. 위험도 등급 변환 함수 정의
def convert_to_risk_levels(df_in:pd.DataFrame) -> pd.DataFrame:
    df = df_in.copy()
    
     # https_cert_risk 생성
    df['https_cert_risk'] = df.apply(classify_https_security, axis=1)

    # 이후 is_https, cert_total_days, cert_issuer 제거
    df = df.drop(columns=['is_https', 'cert_total_days', 'cert_issuer'])



    df['domain_age_days'] = df['domain_age_days'].apply(
        lambda x: 1 if x <= 365 else (0 if x <= 1095 else -1)
    )
    df['days_since_creation'] = df['days_since_creation'].apply(
        lambda x: 1 if x <= 365 else (0 if x <= 1095 else -1)
    )

    def registrar_risk(r):
        if pd.isna(r) or r.lower() in ["null", "unknown"]:
            return 1
        r = r.lower()
        risky = ['dominent', 'gname.com', 'webcc']
        trusted = ['markmonitor', 'godaddy', 'csc', 'com laude', 'amazon registrar',
                   'alibaba cloud', 'network solutions', 'cloudflare']
        if any(t in r for t in trusted):
            return -1
        elif any(w in r for w in risky):
            return 0
        return 0

    df['Registrar'] = df['Registrar'].apply(registrar_risk)
    df['WHOIS Available'] = df['WHOIS Available'].apply(lambda x: -1 if x else 1)
    df['extUrlRatio'] = df['extUrlRatio'].apply(lambda x: 0 if pd.isna(x) else (1 if x > 0.2 else -1))    
    df['externalAnchorRatio'] = df['externalAnchorRatio'].apply(lambda x: 0 if pd.isna(x) else (1 if x > 0.2 else -1))
    df['invalidAnchorRatio'] = df['invalidAnchorRatio'].apply(lambda x: 0 if pd.isna(x) else (1 if x > 0.2 else -1))
    df['is_punycode'] = df['is_punycode'].apply(lambda x: 1 if x else -1)
    df['url_length'] = df['url_length'].apply(lambda x: 1 if x >= 130 else (0 if x >= 80 else -1))
    df['domain_length'] = df['domain_length'].apply(lambda x: 1 if x <= 10 else (0 if x <= 18 else -1))
    df['tld_length'] = df['tld_length'].apply(lambda x: 1 if x <= 2 else -1)
    df['path_length'] = df['path_length'].apply(lambda x: 1 if x >= 100 else (0 if x >= 30 else -1))
    df['query_length'] = df['query_length'].apply(lambda x: 1 if x >= 80 else (0 if x >= 20 else -1))
    df['subdomain_count'] = df['subdomain_count'].apply(lambda x: 1 if x <= 1 else (0 if x == 2 else -1))
    df['char_ratio'] = df['char_ratio'].apply(lambda x: 1 if x < 0.1 or x >= 0.3 else (-1 if 0.15 <= x <= 0.25 else 0))
    df['digit_ratio'] = df['digit_ratio'].apply(lambda x: 1 if x >= 0.1 else (0 if 0.09 <= x < 0.1 else -1))
    df['dot_count'] = df['dot_count'].apply(lambda x: 1 if x <= 2 else (-1 if x >= 5 else 0))
    df['hyphen_count'] = df['hyphen_count'].apply(lambda x: 1 if 2 <= x <= 3 else (0 if x < 1 else -1))
    df['slash_count'] = df['slash_count'].apply(lambda x: 1 if x >= 3 else -1)
    df['question_count'] = df['question_count'].apply(lambda x: 0 if x == 1 else -1)
    df['has_hash'] = df['has_hash'].apply(lambda x: 1 if x else -1)
    df['has_at_symbol'] = df['has_at_symbol'].apply(lambda x: 1 if x else -1)
    # df['is_https'] = df['is_https'].apply(lambda x: -1 if x == 1 else 1)

    binary_features = [
        'encoding', 'contains_port', 'file_extension', 'contains_ip',
        'phishing_keywords', 'free_domain', 'shortened_url', 'typosquatting'
    ]
    for col in binary_features:
        df[col] = df[col].apply(lambda x: 1 if x else -1)
    return df

