
import os
import pickle
import numpy as np
import pandas as pd
import ssl, socket
from datetime import datetime
from urllib.parse import urlparse

from bot.processed_feature import extract_url_features_minimal
from bot.test_whois import extract_whois_features
from bot.feature_crawler import extract_crawler_features
from bot.add_ssl import get_ssl_cert_info
from bot.reprocess import convert_to_risk_levels
# ───────────────────────────────────────────────────────────────────────────────
# (0) 모델 및 피처 순서 로드
BASE_DIR  = os.path.dirname(__file__)
MODEL_DIR = os.path.join(BASE_DIR, "models")

with open(os.path.join(MODEL_DIR, "xgb_final_model.pkl"), "rb") as f:
    _model = pickle.load(f)
with open(os.path.join(MODEL_DIR, "feature_order_reduced.pkl"), "rb") as f:
    _feature_order = pickle.load(f)
# ───────────────────────────────────────────────────────────────────────────────

def build_raw_features(url: str) -> pd.DataFrame:
    """
    URL 하나를 받아 다양한 원시 피처를 추출하여 DataFrame으로 반환합니다.
    'url', 'domain', 'created_date', 'expiry_date' 등을 포함하며,
    주요 수치형 피처는 np.nan으로 설정합니다.
    """
    parsed = urlparse(url)
    # URL 기반 피처
    url_feats = extract_url_features_minimal(url).to_dict()
    # 기본 필드 추가
    url_feats['url']    = url
    url_feats['domain'] = parsed.netloc

    # WHOIS 정보
    whois = extract_whois_features(url)
    created_str = whois.get("Created Date", None)
    expiry_str  = whois.get("Expiry Date", None)
    # lowercase keys for DB
    url_feats['created_date'] = created_str
    url_feats['expiry_date']  = expiry_str
    # uppercase keys for mapping
    url_feats['Created Date'] = created_str
    url_feats['Expiry Date']  = expiry_str

    try:
        created = datetime.strptime(created_str, "%Y-%m-%d") if created_str else None
        expiry  = datetime.strptime(expiry_str, "%Y-%m-%d") if expiry_str else None
        today   = datetime.now()
        url_feats["domain_age_days"]      = (today - created).days if created else np.nan
        url_feats["days_since_creation"] = (expiry - today).days if expiry else np.nan
    except Exception:
        url_feats["domain_age_days"]      = np.nan
        url_feats["days_since_creation"] = np.nan

    # lowercase WHOIS fields for DB
    url_feats["registrar"]       = whois.get("Registrar", None)
    url_feats["whois_available"] = bool(whois.get("WHOIS Available", False))
    # uppercase WHOIS fields for mapping
    url_feats["Registrar"]       = url_feats["registrar"]
    url_feats["WHOIS Available"] = url_feats["whois_available"]

    # 크롤러 기반 피처
    crawler = extract_crawler_features(url)
    url_feats.update(crawler)

    # SSL 정보
    _, ssl_days, ssl_issuer = get_ssl_cert_info(parsed.netloc)
    url_feats["cert_total_days"] = ssl_days if ssl_days is not None else np.nan
    url_feats["cert_issuer"]     = ssl_issuer or ""

    return pd.DataFrame([url_feats])


def build_mapped_features(url: str) -> tuple[np.ndarray, dict]:
    """
    build_raw_features → NA/None 채움 → 리스크 레벨 변환 →
    모델 입력 배열(X) + raw_feats dict 반환
    """
    df_raw = build_raw_features(url)
    # 결측치 처리: 매핑 단계에서 오류 방지
    for col in ["domain_age_days", "days_since_creation", "cert_total_days"]:
        if col in df_raw:
            df_raw[col] = df_raw[col].fillna(0)

    # –1/0/1 리스크 매핑
    df_mapped = convert_to_risk_levels(df_raw)

    # raw_feats: DB 저장 시 사용하기 위한 dict (NaN→None)
    raw_feats = df_raw.iloc[0].apply(lambda x: None if pd.isna(x) else x).to_dict()

    # X: feature_order 순서대로
    X = df_mapped[_feature_order].values
    return X, raw_feats


def predict_url(url: str) -> tuple[int, float, float, dict]:
    """
    URL 분석을 수행하고, (label, mal_prob, leg_prob, raw_feats) 반환
    label: 0(정상) or 1(악성)
    mal_prob, leg_prob: 확률
    raw_feats: 원시 피처 dict
    """
    X, raw_feats = build_mapped_features(url)
    proba = _model.predict_proba(X)[0]
    label = int(np.argmax(proba))
    mal_prob, leg_prob = float(proba[1]), float(proba[0])
    raw_feats['type'] = 'MALICIOUS' if label == 1 else 'LEGITIMATE'
    return label, mal_prob, leg_prob, raw_feats


# Example usage
if __name__ == "__main__":
    url = input("분석할 URL 입력> ")
    label, mal, leg, feats = predict_url(url)
    print(f"분류: {'악성' if label else '정상'}")
    print(f"악성 확률: {mal*100:.2f}%")
    print(f"정상 확률: {leg*100:.2f}%")
    print("원시 피처:", feats)

