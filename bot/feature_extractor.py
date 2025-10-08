# bot/feature_extractor.py
# -*- coding: utf-8 -*-
from __future__ import annotations

import os, json, math, socket  # ← socket 추가
from typing import Dict, Any, List, Tuple, Optional
from datetime import datetime
from urllib.parse import urlparse

import numpy as np
import pandas as pd

# 네 기존 모듈
from bot.processed_feature import extract_url_features_minimal
from bot.test_whois import extract_whois_features
from bot.feature_crawler import extract_crawler_features
from bot.add_ssl import get_ssl_cert_info

# 한글 라벨
FEATURE_LABELS: Dict[str, str] = {
    "url": "URL", "domain": "도메인",
    "Domain": "도메인", "created_date": "도메인 생성일", "expiry_date": "도메인 만료일",
    "Registrar": "등록기관", "whois_available": "WHOIS 제공 여부",
    "domain_age_days": "도메인 나이(일)", "days_to_expiry": "도메인 만료까지 남은 일수",
    "is_punycode": "Punycode 사용", "url_length": "URL 길이",
    "domain_length": "도메인 길이", "tld_length": "TLD 길이",
    "path_length": "경로 길이", "query_length": "쿼리 길이",
    "subdomain_count": "서브도메인 개수", "char_ratio": "특수문자 비율",
    "digit_ratio": "숫자 비율", "dot_count": ". 개수",
    "hyphen_count": "- 개수", "slash_count": "/ 개수",
    "question_count": "? 개수", "has_hash": "# 포함",
    "has_at_symbol": "@ 포함", "is_https": "HTTPS 사용",
    "encoding": "인코딩 토큰 포함(%xx/base64)", "contains_port": "포트 번호 포함",
    "file_extension": "파일 확장자 경로 포함", "contains_ip": "IP 주소 포함",
    "phishing_keywords": "피싱 키워드 포함", "free_domain": "무료 도메인 TLD",
    "shortened_url": "단축 URL", "typosquatting": "타이포스쿼팅 의심",
    "extUrlRatio": "외부 리소스 비율", "externalAnchorRatio": "외부 앵커 비율",
    "invalidAnchorRatio": "잘못된 앵커 비율",
    "cert_total_days": "SSL 인증서 총 유효기간(일)", "cert_issuer": "SSL 인증서 발급기관",
}

# 대체 키 표준화
FEATURE_ALIASES: Dict[str, str] = {
    "Created Date": "created_date",
    "Expiry Date": "expiry_date",
    "WHOIS Available": "whois_available",
    "ip_in_domain": "contains_ip",
    "use_https": "is_https",
    "contains_at": "has_at_symbol",
    # 의미가 다르면 제거하세요
    "days_since_creation": "days_to_expiry",
}

def _canonicalize_keys(d: Dict[str, Any]) -> Dict[str, Any]:
    out = dict(d)
    for k, v in list(d.items()):
        if k in FEATURE_ALIASES:
            out[FEATURE_ALIASES[k]] = v
    return out

# family 분류
FAMILY_MAP = {
    "domain_age_days": "whois", "days_to_expiry": "whois",
    "whois_available": "whois", "Registrar": "whois",
    "contains_ip": "url", "has_at_symbol": "url", "subdomain_count": "url",
    "url_length": "url", "is_punycode": "url", "encoding": "url",
    "contains_port": "url", "file_extension": "url", "phishing_keywords": "url",
    "free_domain": "url", "shortened_url": "url", "char_ratio": "url",
    "digit_ratio": "url", "hyphen_count": "url", "slash_count": "url",
    "question_count": "url", "has_hash": "url", "tld_length": "url",
    "domain_length": "url", "path_length": "url", "query_length": "url",
    "extUrlRatio": "content", "externalAnchorRatio": "content",
    "invalidAnchorRatio": "content",
    "cert_total_days": "ssl", "cert_issuer": "ssl", "is_https": "ssl",
}

# 임계값 JSON 로딩
THRESH_PATH = os.path.join(os.path.dirname(__file__), "feature_thresholds.json")
_THRESH: Optional[Dict[str, Any]] = None

def _load_thresholds() -> Dict[str, Any]:
    global _THRESH
    if _THRESH is not None:
        return _THRESH
    if os.path.exists(THRESH_PATH):
        with open(THRESH_PATH, "r", encoding="utf-8") as f:
            _THRESH = json.load(f)
    else:
        _THRESH = {}
    return _THRESH

def _is_num(x) -> bool:
    return isinstance(x, (int, float)) and not (isinstance(x, float) and math.isnan(x))

def _fmt_val(v):
    if isinstance(v, float):
        return f"{v:.2f}"
    return v

def _can_resolve(host: str) -> bool:
    try:
        socket.getaddrinfo(host, None)
        return True
    except Exception:
        return False

# 1) 모든 원시 특징 수집 (모델 불필요)
def build_raw_features(url: str) -> pd.DataFrame:
    parsed = urlparse(url)
    netloc = parsed.netloc.split(":")[0]
    feats: Dict[str, Any] = {"url": url, "domain": netloc}

    # URL 패턴/문자열
    try:
        s = extract_url_features_minimal(url)
        feats.update(s.to_dict())
    except Exception:
        keys = ["is_punycode","url_length","domain_length","tld_length","path_length","query_length",
                "subdomain_count","char_ratio","digit_ratio","dot_count","hyphen_count","slash_count",
                "question_count","has_hash","has_at_symbol","is_https","encoding","contains_port",
                "file_extension","contains_ip","phishing_keywords","free_domain","shortened_url","typosquatting"]
        for k in keys:
            feats.setdefault(k, np.nan if k not in ("has_hash","has_at_symbol","is_https") else 0)

    # WHOIS
    try:
        who = extract_whois_features(url) or {}
        feats["Domain"] = who.get("Domain", netloc)
        feats["created_date"] = who.get("Created Date")
        feats["expiry_date"]  = who.get("Expiry Date")
        feats["Registrar"]    = who.get("Registrar")
        feats["whois_available"] = who.get("WHOIS Available", False)
    except Exception:
        feats.setdefault("Domain", netloc)
        feats.setdefault("created_date", None)
        feats.setdefault("expiry_date", None)
        feats.setdefault("Registrar", None)
        feats.setdefault("whois_available", False)

    # 파생: 나이/만료D-일
    feats["domain_age_days"] = np.nan
    feats["days_to_expiry"]  = np.nan
    try:
        c = feats.get("created_date"); e = feats.get("expiry_date")
        created = datetime.strptime(c, "%Y-%m-%d") if c and c != "Unknown" else None
        expiry  = datetime.strptime(e, "%Y-%m-%d") if e and e != "Unknown" else None
        now = datetime.now()
        if created: feats["domain_age_days"] = (now - created).days
        if expiry:  feats["days_to_expiry"]  = (expiry - now).days
    except Exception:
        pass

    # ─────────────────────────────────────────────────────────────
    # 크롤링 지표 (환경변수 DISABLE_CRAWL 로 토글 + DNS 가드)
    # ─────────────────────────────────────────────────────────────
    if os.getenv("DISABLE_CRAWL", "0") == "1":
        # 크롤링 OFF: 기본값(0.0)으로 고정
        feats["extUrlRatio"]         = 0.0
        feats["externalAnchorRatio"] = 0.0
        feats["invalidAnchorRatio"]  = 0.0
    else:
        host = netloc
        if _can_resolve(host):
            try:
                cr = extract_crawler_features(url) or {}
                feats["extUrlRatio"]         = cr.get("extUrlRatio", 0.0)
                feats["externalAnchorRatio"] = cr.get("externalAnchorRatio", 0.0)
                feats["invalidAnchorRatio"]  = cr.get("invalidAnchorRatio", 0.0)
            except Exception:
                feats["extUrlRatio"]         = 0.0
                feats["externalAnchorRatio"] = 0.0
                feats["invalidAnchorRatio"]  = 0.0
        else:
            feats["extUrlRatio"]         = 0.0
            feats["externalAnchorRatio"] = 0.0
            feats["invalidAnchorRatio"]  = 0.0
    # ─────────────────────────────────────────────────────────────

    # SSL
    try:
        _, cert_days, issuer = get_ssl_cert_info(netloc)
        feats["cert_total_days"] = cert_days if cert_days is not None else np.nan
        feats["cert_issuer"]     = issuer or ""
    except Exception:
        feats["cert_total_days"] = np.nan
        feats["cert_issuer"]     = ""

    feats = _canonicalize_keys(feats)
    return pd.DataFrame([feats])

# 2) 튜닝 임계값을 이용한 숫자형 점수화
def _score_num_with_thresholds(key: str, val: float) -> Optional[Tuple[float, str, str]]:
    thr = _load_thresholds().get(key)
    if not thr or val is None or (isinstance(val, float) and math.isnan(val)):
        return None
    direction = thr.get("direction", "higher_is_risk")
    t_med, t_high = thr.get("t_med"), thr.get("t_high")
    label = FEATURE_LABELS.get(key, key); v = _fmt_val(val)

    if direction == "higher_is_risk":
        if t_high is not None and val >= t_high: return (+1.2, f"{label} **{v}** — 높음", key)
        if t_med  is not None and val >= t_med:  return (+0.7, f"{label} **{v}** — 다소 높음", key)
        q25 = (thr.get("q") or {}).get("p25")
        if q25 is not None and val <= q25:       return (-0.3, f"{label} **{v}** — 낮음(안정)", key)
    else:
        if t_high is not None and val <= t_high: return (+1.2, f"{label} **{v}** — 낮음(위험)", key)
        if t_med  is not None and val <= t_med:  return (+0.7, f"{label} **{v}** — 다소 낮음", key)
        q75 = (thr.get("q") or {}).get("p75")
        if q75 is not None and val >= q75:       return (-0.3, f"{label} **{v}** — 높음(안정)", key)
    return None

# 3) 휴리스틱 점수화 + 문장 생성
def _score_and_explain(f: Dict[str, Any]) -> List[Tuple[float, str, str, str]]:
    C: List[Tuple[float, str, str, str]] = []

    def add_num(key: str, default_logic):
        v = f.get(key)
        if v is None or (isinstance(v, float) and math.isnan(v)): return
        tuned = _score_num_with_thresholds(key, v)
        fam = FAMILY_MAP.get(key, "other")
        if tuned is not None:
            s, t, _ = tuned; C.append((s, t, key, fam)); return
        out = default_logic(v)
        if out: C.append((out[0], out[1], key, fam))

    # WHOIS
    def _logic_domain_age_days(v):
        if v < 30:   return (+2.0, f"도메인 생성 {int(v)}일 — **매우 최근**")
        if v < 180:  return (+1.0, f"도메인 생성 {int(v)}일 — **최근 등록**")
        if v > 365:  return (-0.5, f"도메인 나이 {int(v)}일 — **1년 이상 유지**")
        return None
    add_num("domain_age_days", _logic_domain_age_days)

    def _logic_days_to_expiry(v):
        if v < 0:   return (+1.4, "도메인 **만료됨/지남** 가능성")
        if v < 30:  return (+0.8, f"만료까지 {int(v)}일 — **임박**")
        return None
    add_num("days_to_expiry", _logic_days_to_expiry)

    if f.get("whois_available") is False:
        C.append((+0.8, "WHOIS 정보 **부재/비공개**", "whois_available", "whois"))

    # URL (binary)
    if bool(f.get("contains_ip")):       C.append((+1.4, "URL에 **IP 주소** 포함", "contains_ip", "url"))
    if bool(f.get("has_at_symbol")):     C.append((+1.1, "URL에 **@ 기호** 포함", "has_at_symbol", "url"))
    if bool(f.get("shortened_url")):     C.append((+1.0, "단축 URL 사용 — **정보 감춤 가능성**", "shortened_url", "url"))
    if bool(f.get("is_punycode")):       C.append((+0.7, "Punycode — **유사 도메인 위장** 가능성", "is_punycode", "url"))
    if bool(f.get("encoding")):          C.append((+0.6, "인코딩 토큰(%xx/base64) — **가독성 저하**", "encoding", "url"))
    if bool(f.get("contains_port")):     C.append((+0.4, "비표준 **포트 번호** 포함", "contains_port", "url"))
    if bool(f.get("file_extension")):    C.append((+0.5, "경로에 **파일 확장자** 포함", "file_extension", "url"))
    if bool(f.get("phishing_keywords")): C.append((+1.2, "피싱 **키워드** 포함", "phishing_keywords", "url"))
    if bool(f.get("free_domain")):       C.append((+0.8, "무료 도메인 TLD 사용", "free_domain", "url"))
    if bool(f.get("has_hash")):          C.append((+0.2, "#(프래그먼트) 포함", "has_hash", "url"))

    # URL (numeric)
    def _logic_subdomain_count(v):
        if v >= 3: return (+1.0, f"서브도메인 **{int(v)}개** — 과다")
        return None
    add_num("subdomain_count", _logic_subdomain_count)

    def _logic_url_length(v):
        if v >= 120: return (+0.7, f"URL 길이 **{int(v)}자** — 비정상적으로 김")
        return None
    add_num("url_length", _logic_url_length)

    def _logic_char_ratio(v):
        if v >= 0.30: return (+0.6, f"특수문자 비율 **{v:.2f}** — 높음")
        elif 0.15 <= v <= 0.25: return (-0.2, f"특수문자 비율 **{v:.2f}** — 보통")
        return None
    add_num("char_ratio", _logic_char_ratio)

    def _logic_digit_ratio(v):
        if v >= 0.10: return (+0.5, f"숫자 비율 **{v:.2f}** — 다소 높음")
        return None
    add_num("digit_ratio", _logic_digit_ratio)

    def _logic_hyphen_count(v):
        if v >= 3: return (+0.4, f"-(하이픈) **{int(v)}개** — 과다")
        return None
    add_num("hyphen_count", _logic_hyphen_count)

    def _logic_slash_count(v):
        if v >= 5: return (+0.4, f"/(슬래시) **{int(v)}개** — 과다")
        return None
    add_num("slash_count", _logic_slash_count)

    def _logic_question_count(v):
        if v > 1: return (+0.3, f"?(쿼리) **{int(v)}개** — 과다")
        return None
    add_num("question_count", _logic_question_count)

    # 콘텐츠/크롤링
    def _logic_ext(v):
        if v >= 0.80: return (+1.1, f"외부 리소스 비율 **{v:.2f}** — 높음")
        if v >= 0.50: return (+0.6, f"외부 리소스 비율 **{v:.2f}** — 다소 높음")
        return None
    add_num("extUrlRatio", _logic_ext)

    def _logic_ea(v):
        if v >= 0.80: return (+1.1, f"외부 앵커 비율 **{v:.2f}** — 높음")
        if v >= 0.50: return (+0.6, f"외부 앵커 비율 **{v:.2f}** — 다소 높음")
        return None
    add_num("externalAnchorRatio", _logic_ea)

    def _logic_ia(v):
        if v >= 0.30: return (+1.1, f"잘못된 앵커 비율 **{v:.2f}** — 높음")
        if v >= 0.10: return (+0.6, f"잘못된 앵커 비율 **{v:.2f}** — 다소 높음")
        return None
    add_num("invalidAnchorRatio", _logic_ia)

    # SSL
    def _logic_cert_days(v):
        if v < 90:   return (+0.5, f"SSL 유효기간 **{int(v)}일** — 짧음")
        if v > 365:  return (-0.3, f"SSL 유효기간 **{int(v)}일** — 길음")
        return None
    add_num("cert_total_days", _logic_cert_days)

    https = f.get("is_https")
    if https == 1 or https is True:  C.append((-0.2, "HTTPS 사용 — 전송구간 **암호화**", "is_https", "ssl"))
    elif https == 0 or https is False: C.append((+1.0, "HTTPS **미사용**", "is_https", "ssl"))

    return C

# 4) 다양성 보장 Top-K
def _pick_diverse_topk(cands: List[Tuple[float, str, str, str]],
                       verdict: str, top_k: int=3, pos_min: float=0.5) -> List[str]:
    out: List[Tuple[float, str, str, str]] = []
    if verdict == "악성":
        pos = [x for x in cands if x[0] >= pos_min]; pos.sort(key=lambda x: -x[0])
        seen = set()
        for x in pos:
            fam = x[3]
            if fam in seen: continue
            out.append(x); seen.add(fam)
            if len(out) >= top_k: return [t for _, t, _, _ in out]
        for x in pos:
            if x in out: continue
            out.append(x)
            if len(out) >= top_k: return [t for _, t, _, _ in out]
        rest = sorted(cands, key=lambda x: -abs(x[0]))
        for x in rest:
            if x in out: continue
            out.append(x)
            if len(out) >= top_k: break
        return [t for _, t, _, _ in out[:top_k]]
    else:
        neg = [x for x in cands if x[0] < 0]; neg.sort(key=lambda x: x[0])  # 더 음수 우선
        seen = set()
        for x in neg:
            fam = x[3]
            if fam in seen: continue
            out.append(x); seen.add(fam)
            if len(out) >= 2: break
        pos = [x for x in cands if x[0] > 0]
        if pos:
            pos.sort(key=lambda x: -x[0]); out.append(pos[0])
        if len(out) < top_k:
            rest = sorted(cands, key=lambda x: (x[0] >= 0, -abs(x[0])))
            for x in rest:
                if x in out: continue
                out.append(x)
                if len(out) >= top_k: break
        return [t for _, t, _, _ in out[:top_k]]

# 5) 공개 API: WHY 설명 생성
def summarize_features_for_explanation(df_raw: pd.DataFrame, verdict: str, top_k: int=3) -> List[str]:
    if df_raw is None or df_raw.empty:
        return ["세부 특징을 추출하지 못했습니다."]
    f = _canonicalize_keys(df_raw.iloc[0].to_dict())
    for k, v in list(f.items()):
        if isinstance(v, float) and math.isnan(v):
            f[k] = None
    cands = _score_and_explain(f)
    if not cands:
        keys = ["domain_age_days", "days_to_expiry", "whois_available", "url_length", "subdomain_count", "extUrlRatio"]
        out = []
        for k in keys:
            if k in f and f[k] is not None:
                label = FEATURE_LABELS.get(k, k)
                out.append(f"{label}: {_fmt_val(f[k])}")
        return out[:max(1, top_k)]
    return _pick_diverse_topk(cands, verdict=verdict.strip(), top_k=top_k, pos_min=0.5)

# (옵션) 보기 좋은 dict
def to_labeled_dict(df_raw: pd.DataFrame) -> Dict[str, Any]:
    if df_raw is None or df_raw.empty:
        return {}
    d = df_raw.iloc[0].to_dict()
    out = {}
    for k, v in d.items():
        label = FEATURE_LABELS.get(k, FEATURE_LABELS.get(FEATURE_ALIASES.get(k, ""), k))
        out[label] = v
    return out
