# bot/tools/urlbert_tool.py

from langchain.agents import Tool
from Server.db_manager import get_urlbert_info_from_db, save_urlbert_to_db
from urlbert.urlbert2.core.urlbert_analyzer import classify_url_and_explain

def load_urlbert_tool(model, tokenizer) -> Tool:
    """
    URL-BERT 분석 전용 LangChain Tool 반환
    :param model: 학습된 BERT 모델 객체
    :param tokenizer: BERT 토크나이저 객체
    """
    def _analyze(url: str) -> str:
        # 1) DB 조회 (실패해도 실시간 분석으로 fallback)
        try:
            db_res = get_urlbert_info_from_db(url)
        except Exception as e:
            print(f"⚠️ DB 조회 오류 ({e}), 실시간 분석으로 진행합니다.")
            db_res = None

        if db_res:
            malicious = "🔴 악성" if db_res["is_malicious"] else "🟢 정상"
            confidence = (
                f"{db_res['confidence']*100:.2f}%"
                if db_res.get("confidence") is not None
                else "N/A"
            )
            return (
                f"[analysis_db] 이미 저장된 URL입니다.\n"
                f"URL: {db_res['url']}\n"
                f"헤더: {db_res.get('header_info') or '없음'}\n"
                f"악성 여부: {malicious}\n"
                f"신뢰도: {confidence}\n"
                f"요약: {db_res.get('reason_summary') or 'N/A'}"
            )

        # 2) 신규 URL: URL-BERT로 분석
        result = classify_url_and_explain(url, model, tokenizer)
        is_mal = int(result["is_malicious"])
        conf  = float(result["confidence"])
        rec = {
            "url":                  url,
            "header_info":          result.get("header_info"),
            "is_malicious":         is_mal,
            "confidence":           conf,
            "true_label":           None,
            "reason_summary":       result.get("reason_summary"),
            "detailed_explanation": result.get("detailed_explanation")
        }

        # 3) DB 저장 (실패해도 무시)
        try:
            save_urlbert_to_db(rec)
        except Exception as e:
            print(f"⚠️ DB 저장 오류 ({e}), 계속 진행합니다.")

        malicious = "🔴 악성" if rec["is_malicious"] else "🟢 정상"
        confidence = f"{rec['confidence']*100:.2f}%"

        # 4) 최종 결과 문자열로 반환
        return (
            f"[realtime_analysis] 분석을 수행했습니다.\n"
            f"URL: {rec['url']}\n"
            f"헤더: {rec['header_info'] or '없음'}\n"
            f"악성 여부: {malicious}\n"
            f"신뢰도: {confidence}\n"
            f"요약: {rec['reason_summary']}"
        )

    return Tool(
        name="URLAnalyzer",
        func=_analyze,
        description="주어진 URL에 대해 URL-BERT 모델로 악성 여부를 분석하고 결과를 문자열로 반환합니다."
    )
