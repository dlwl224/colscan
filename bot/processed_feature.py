import pandas as pd
import re
from urllib.parse import urlparse
import idna
from difflib import SequenceMatcher

def extract_url_features_minimal(url):
    parsed = urlparse(url)

    # Punycode 사용 여부
    try:
        punycode_used = url != idna.decode(url)
    except:
        punycode_used = False

    # 전체 URL 길이
    url_length = len(url)

    # 도메인, TLD, 경로(Path), 파라미터(Query)의 길이
    domain = parsed.netloc
    path = parsed.path
    query = parsed.query

    domain_length = len(domain)
    tld_length = len(domain.split('.')[-1]) if '.' in domain else 0
    path_length = len(path)
    query_length = len(query)

    # subdomain count
    subdomain_count = len(domain.split('.')) - 2 if len(domain.split('.')) > 2 else 0

    # 특수문자 및 숫자 포함 비율
    def ratio(text, pattern):
        matches = re.findall(pattern, text)
        return len(matches) / len(text) if text else 0

    special_char_ratio = ratio(url, r'[^a-zA-Z0-9]')
    digit_ratio = ratio(url, r'[0-9]')

    # "." 개수
    dot_count = url.count('.')

    # "-" 개수
    hyphen_count = url.count('-')

    # "/" 개수
    slash_count = url.count('/')

    # "?" 개수
    question_mark_count = url.count('?')

    # "#" 포함 여부
    has_hash = 1 if '#' in url else 0

    # "@" 포함 여부
    has_at_symbol = 1 if '@' in url else 0

    # HTTP vs HTTPS
    is_https = 1 if parsed.scheme == "https" else 0

    # 인코딩 사용 여부
    contains_encoding = 1 if re.search(r'%[0-9A-Fa-f]{2}|base64', url) else 0

    # 포트 번호 포함 여부
    contains_port = 1 if ':' in domain.split('.')[-1] else 0

    # 파일 확장자 포함 여부
    contains_file_extension = 1 if re.search(r'\.(php|html|htm|doc|docx|xls|xlsx|ppt|pptx|hwp|exe|apk|zip)', path) else 0

    # IP 포함 여부
    contains_ip = 1 if re.match(r'^(?:http[s]?://)?(?:[0-9]{1,3}\.){3}[0-9]{1,3}', url) else 0

    # 피싱 관련 단어 포함 여부
    phishing_keywords = ["secure", "security", "login", "verify", "account", "update", "bank", "paypal", "mail", "free", "email", "amazon", "app"]
    contains_phishing_words = 1 if any(re.search(rf'\b{re.escape(word)}\b', url.lower()) for word in phishing_keywords) else 0

    # 무료 도메인 사용 여부
    free_domains = [".tk", ".ml", ".cf", ".ga", ".gq"]
    is_free_domain = 1 if any(url.endswith(fd) for fd in free_domains) else 0

    # 단축 URL 여부
    shortening_services = [
        "bit.ly", "goo.gl", "tinyurl.com", "ow.ly", "t.co", "is.gd",
        "buff.ly", "adf.ly", "bit.do", "mcaf.ee", "shorturl.at"
    ]
    is_shortened = 1 if any(service in domain for service in shortening_services) else 0

    # 타이포스쿼팅 탐지 (도메인에 대한 유사도 측정)
    brand_list = [
        "naver", "kakao", "google", "youtube", "facebook", "instagram", "twitter", "wikipedia", "amazon",
        "apple", "microsoft", "whatsapp", "bing", "yahoo"
    ]
    domain_main = domain.split('.')[-2] if len(domain.split('.')) >= 2 else domain
    typosquatting_detected = 0
    for brand in brand_list:
        similarity = SequenceMatcher(None, domain_main.lower(), brand).ratio()
        if similarity > 0.8 and domain_main.lower() != brand:
            typosquatting_detected = 1
            break

    return pd.Series({
        "is_punycode": punycode_used,
        "url_length": url_length,
        "domain_length": domain_length,
        "tld_length": tld_length,
        "path_length": path_length,
        "query_length": query_length,
        "subdomain_count": subdomain_count,
        "char_ratio": special_char_ratio,
        "digit_ratio": digit_ratio,
        "dot_count": dot_count,
        'hyphen_count': hyphen_count,
        "slash_count": slash_count,
        "question_count": question_mark_count,
        "has_hash": has_hash,
        "has_at_symbol": has_at_symbol,
        "is_https": is_https,
        "encoding": contains_encoding,
        "contains_port": contains_port,
        "file_extension": contains_file_extension,
        "contains_ip": contains_ip,
        "phishing_keywords": contains_phishing_words,
        "free_domain": is_free_domain,
        "shortened_url": is_shortened,
        "typosquatting": typosquatting_detected
    })
# 예측 시에는 아래 코드가 실행되지 않도록 막아둠
if __name__ == "__main__":
    df = pd.read_csv("/home/injeolmi/myproject/sQanAR/whois_data/analyzed_url.csv")
    df_features = df["url"].apply(extract_url_features_minimal)
    df_processed = pd.concat([df, df_features], axis=1)
    df_processed.to_csv("/home/injeolmi/myproject/sQanAR/feature.csv", index=False)

