import json
from pydantic import BaseModel
from langchain_core.tools import Tool

from url_repository import UrlRepository
from feature_extraction import predict_url

# ───────────────────────────────────────────────────────────────────────────────
# 입력 스키마 정의
class URLInput(BaseModel):
    url: str

# ───────────────────────────────────────────────────────────────────────────────
# 1) 캐시 조회 도구

def run_lookup_db_url_tool(query: dict) -> str:
    """
    주어진 URL에 대해 DB 캐시된 분석 결과를 조회합니다.
    입력: {"url": "https://..."}
    반환: JSON 문자열 (캐시된 분석 결과) 또는 메시지 JSON
    """
    repo = UrlRepository()
    try:
        rec = repo.lookup(query.url)
    except Exception as e:
        return json.dumps({"error": str(e)}, ensure_ascii=False)

    if rec:
        return json.dumps(rec, ensure_ascii=False, indent=2)
    return json.dumps({"message": "캐시된 분석 결과가 없습니다."}, ensure_ascii=False, indent=2)

lookup_db_url_tool = Tool(
    name="lookup_db_url",
    func=run_lookup_db_url_tool,
    description="DB에서 주어진 URL의 캐시된 분석 결과를 JSON 형식으로 반환합니다.",
    args_schema=URLInput
)

# ───────────────────────────────────────────────────────────────────────────────
# 2) 신규 분석 도구

def run_analyze_url_tool(query: dict) -> str:
    """
    URL에 대한 캐시를 먼저 조회하고, 없으면 모델 예측 후 DB에 저장하고 결과 반환합니다.
    입력: {"url": "https://..."}
    반환: JSON 문자열 (분석 결과 및 원시 피처 포함)
    """
    repo = UrlRepository()
    url = query.url

    # 1) 캐시 있으면 바로 반환
    try:
        rec = repo.lookup(url)
    except Exception as e:
        return json.dumps({"error": str(e)}, ensure_ascii=False)

    if rec:
        return json.dumps(rec, ensure_ascii=False, indent=2)

    # 2) 모델 예측
    label, mal_prob, leg_prob, raw_feats = predict_url(url)
    label_str = "MALICIOUS" if label == 1 else "LEGITIMATE"

    # 3) DB 저장
    repo.save_analysis(
        url=url,
        raw=raw_feats,
        label=label_str,
        proba_safe=leg_prob,
        proba_warn=0.0,
        proba_mal=mal_prob
    )

    # 4) 결과 포맷
    result = {"url": url, "label": label_str,
              "malicious_prob": mal_prob, "legitimate_prob": leg_prob}
    result.update(raw_feats)

    return json.dumps(result, ensure_ascii=False, indent=2)

analyze_url_tool = Tool(
    name="analyze_url",
    func=run_analyze_url_tool,
    description="새로운 URL을 분석하고, 결과를 DB에 저장한 후 JSON 형식으로 반환합니다.",
    args_schema=URLInput
)