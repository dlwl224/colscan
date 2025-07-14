# bot/tools/urlbert_tool.py

import hashlib
from langchain.agents import Tool
from Server.db_manager import get_urlbert_info_from_db, save_urlbert_to_db
from urlbert.urlbert2.core.urlbert_analyzer import classify_url_and_explain

def load_urlbert_tool(model_tokenizer_tuple) -> Tool:
    """
    URL-BERT 분석 전용 LangChain Tool 반환
    """
    model, tokenizer = model_tokenizer_tuple

    def _analyze(url: str):
        # 1) DB 조회
        db_res = get_urlbert_info_from_db(url)
        if db_res:
            return {
                "message": "이미 저장된 URL입니다.",
                "source":  "analysis_db",
                "url":     db_res["url"],
                "header_info": db_res.get("header_info"),
                "is_malicious": bool(db_res["is_malicious"]),
                "confidence": (
                    f"{db_res['confidence']*100:.2f}%"
                    if db_res.get("confidence") is not None else None
                ),
                "true_label": (
                    bool(db_res["true_label"])
                    if db_res.get("true_label") is not None else None
                ),
                "reason_summary":        db_res.get("reason_summary"),
                "detailed_explanation":  db_res.get("detailed_explanation")
            }

        # 2) 신규 URL: 분석
        result = classify_url_and_explain(url, model, tokenizer)

        # 3) DB 저장
        record = {
            "url":                  url,
            "header_info":          result["header_info"],
            "is_malicious":         1 if result["predicted_label"]=="malicious" else 0,
            "confidence":           float(result["confidence"]),
            "true_label":           None,
            "reason_summary":       result["reason_summary"],
            "detailed_explanation": result["detailed_explanation"]
        }
        save_urlbert_to_db(record)

        # 4) 응답
        return {
            "message": "분석을 수행했습니다.",
            "source":  "realtime_analysis",
            "url":     url,
            "header_info": record["header_info"],
            "is_malicious": bool(record["is_malicious"]),
            "confidence": (
                f"{record['confidence']*100:.2f}%"
                if record["confidence"] is not None else None
            ),
            "true_label": None,
            "reason_summary":       record["reason_summary"],
            "detailed_explanation": record["detailed_explanation"]
        }

    return Tool(
        name="SecurityURLAnalyzer",
        func=_analyze,
        description="주어진 URL에 대해 URL-BERT 모델로 악성 여부를 분석하고, 결과를 JSON 형태로 반환합니다."
    )
