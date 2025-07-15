# bot/tools/urlbert_tool.py

from langchain.agents import Tool
from Server.db_manager import get_urlbert_info_from_db, save_urlbert_to_db
from urlbert.urlbert2.core.urlbert_analyzer import classify_url_and_explain

def load_urlbert_tool(model, tokenizer) -> Tool:
    """
    URL-BERT 분석 전용 LangChain Tool 반환
    """
    def _analyze(url: str):
        # 1) DB 조회
        db_res = get_urlbert_info_from_db(url)
        if db_res:
            return (
                f"[analysis_db] 이미 저장된 URL입니다.\n"
                f"URL: {db_res['url']}\n"
                f"헤더: {db_res.get('header_info')}\n"
                f"악성 여부: {'🔴 악성' if db_res['is_malicious'] else '🟢 정상'}\n"
                f"신뢰도: {db_res['confidence']*100:.2f}%\n"
                f"요약: {db_res.get('reason_summary')}"
            )

        # 2) 신규 URL: 분석
        result = classify_url_and_explain(url, model, tokenizer)

        # 3) DB 저장
        record = {
            "url":                  url,
            "header_info":          result["header_info"],
            "is_malicious":         result["is_malicious"],  # 0/1 그대로
            "confidence":           float(result["confidence"]),
            "true_label":           None,
            "reason_summary":       result["reason_summary"],
            "detailed_explanation": result["detailed_explanation"]
        }
        save_urlbert_to_db(record)

        # 4) 리턴 스트링 포맷
        return (
            f"[realtime_analysis] 분석을 수행했습니다.\n"
            f"URL: {url}\n"
            f"헤더: {record['header_info']}\n"
            f"악성 여부: {'🔴 악성' if record['is_malicious'] else '🟢 정상'}\n"
            f"신뢰도: {record['confidence']*100:.2f}%\n"
            f"요약: {record['reason_summary']}"
        )

    return Tool(
        name="URLAnalyzer",
        func=_analyze,
        description="주어진 URL에 대해 URL-BERT 모델로 악성 여부를 분석하고 결과를 리턴합니다."
    )
