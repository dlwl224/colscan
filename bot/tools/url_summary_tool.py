from typing import Dict, Any
from langchain.agents import Tool

def summarize_url_analysis(analysis: Dict[str, Any]) -> str:
    """
    analysis['source'] 값에 따라 두 가지 요약 포맷을 지원합니다.
    - raw_db: type + 대표 피처만
    - analysis_db / realtime_analysis: 확률, 핵심 피처 3가지, 판단 근거
    """
    url          = analysis.get("url", "")
    source       = analysis.get("source", "")
    raw_feats    = analysis.get("raw_features", {})
    lines        = [f"🔗 URL: {url}"]

    if source == "raw_db":
        t = raw_feats.get("type", "알 수 없음")
        lines.append(f"• 타입: {t}")
        if raw_feats.get("url_length") is not None:
            lines.append(f"• URL 길이: {raw_feats['url_length']}자")
        if raw_feats.get("domain_age_days") is not None:
            lines.append(f"• 도메인 생성 후 경과: {raw_feats['domain_age_days']}일")
        return "\n".join(lines)

    is_mal = analysis.get("is_malicious", False)
    mal_p  = analysis.get("malicious_probability", 0.0)
    leg_p  = analysis.get("legitimate_probability", 0.0)
    lines.append(
        f"• 최종 판정: {'❌ 악성' if is_mal else '✅ 정상'}  "
        f"(악성 {mal_p*100:.2f}%, 정상 {leg_p*100:.2f}%)"
    )

    lines.append("\n[핵심 피처]")
    keys = ["domain_age_days", "url_length", "phishing_keywords"]
    for k in keys:
        v = raw_feats.get(k)
        if v is None: continue
        if isinstance(v, bool):
            v = "예" if v else "아니오"
        label = {
            "domain_age_days": "도메인 나이(일)",
            "url_length":       "URL 길이(자)",
            "phishing_keywords":"피싱 키워드 포함"
        }[k]
        lines.append(f"• {label}: {v}")

    lines.append("\n[판단 근거]")
    reasons = analysis.get("reasons", [])
    if reasons:
        for r in reasons:
            lines.append(f"• {r}")
    else:
        lines.append("• 특별한 근거가 없습니다.")

    return "\n".join(lines)

url_summary_tool = Tool(
    name="URLSummary",
    func=summarize_url_analysis,
    description="DB 또는 실시간 분석 결과를 받아 한국어 요약문을 반환합니다."
)
