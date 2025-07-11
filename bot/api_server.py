# bot/api_server.py

import hashlib
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
from typing import Optional

# 실제 코드에서는 소문자 패키지명을 사용하거나 PYTHONPATH 설정을 확인하세요.
from Server.db_manager import get_urlbert_info_from_db, save_urlbert_to_db
from urlbert.urlbert2.core.urlbert_analyzer import classify_url_and_explain
from urlbert.urlbert2.core.model_loader import load_inference_model

app = FastAPI(
    title="URL-BERT Security Chatbot API",
    description="URL-BERT 기반 위험도 분석 및 저장 API",
    version="1.0.0"
)


class URLAnalysisRequest(BaseModel):
    url: str


class URLAnalysisResponse(BaseModel):
    message: str
    source: str
    url: str
    header_info: Optional[str]
    is_malicious: bool           # bool 로 변환
    confidence: Optional[str]    # 퍼센트 문자열
    true_label: Optional[bool]
    reason_summary: Optional[str]
    detailed_explanation: Optional[str]


# 애플리케이션 시작 시 모델·토크나이저를 한 번 로드
model, tokenizer = load_inference_model()


@app.post("/analyze_url/", response_model=URLAnalysisResponse)
async def analyze_url(request: URLAnalysisRequest):
    url = request.url

    # 1) 이미 DB에 저장된 URL인지 확인
    db_res = get_urlbert_info_from_db(url)
    if db_res:
        # DB에서 가져온 형태: is_malicious:int, confidence:float|None, true_label:int|None
        return {
            "message": "이미 저장된 URL입니다.",
            "source": "analysis_db",
            "url": db_res["url"],
            "header_info": db_res.get("header_info"),
            "is_malicious": bool(db_res["is_malicious"]),
            "confidence": (
                f"{db_res['confidence']*100:.2f}%"
                if db_res.get("confidence") is not None
                else None
            ),
            "true_label": (
                bool(db_res["true_label"])
                if db_res.get("true_label") is not None
                else None
            ),
            "reason_summary": db_res.get("reason_summary"),
            "detailed_explanation": db_res.get("detailed_explanation")
        }

    # 2) 신규 URL: 분석 수행
    try:
        result = classify_url_and_explain(url, model, tokenizer)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"분석 중 오류 발생: {e}")

    # 3) DB에 저장할 raw record 구성 (DB 스키마용)
    record = {
        "url":                  url,
        "header_info":          result.get("header_info"),
        "is_malicious":         1 if result["is_malicious"] else 0,
        "confidence":           result.get("confidence"),  # 이미 float 타입
        "true_label":           None,
        "reason_summary":       result.get("reason_summary"),
        "detailed_explanation": result.get("detailed_explanation")
    }
    save_urlbert_to_db(record)

    # 4) 응답용으로 포맷 변환
    return {
        "message": "분석을 수행했습니다.",
        "source": "realtime_analysis",
        "url": record["url"],
        "header_info": record["header_info"],
        "is_malicious": bool(record["is_malicious"]),
        "confidence": (
            f"{record['confidence']*100:.2f}%"
            if record["confidence"] is not None
            else None
        ),
        "true_label": None,
        "reason_summary": record["reason_summary"],
        "detailed_explanation": record["detailed_explanation"]
    }


if __name__ == "__main__":
    import uvicorn
    uvicorn.run("bot.api_server:app", host="0.0.0.0", port=8000, reload=True)
