import os
import sys
from fastapi import FastAPI, HTTPException, Request
from pydantic import BaseModel
from fastapi.responses import JSONResponse
from fastapi.middleware.cors import CORSMiddleware
import uvicorn

# 🔧 config.py를 인식시키기 위해 경로 추가
sys.path.append(os.path.join(os.path.dirname(__file__), '..', 'urlbert', 'urlbert2'))

from urlbert.urlbert2.core.model_loader import load_inference_model
from urlbert.urlbert2.core.urlbert_analyzer import classify_url_and_explain
from Server.db_manager import get_urlbert_info_from_db, save_urlbert_to_db

app = FastAPI(
  title="URL-BERT Security Chatbot API",
  description="URL-BERT 기반 위험도 분석 및 저장 API",
  version="1.0.0"
)

# CORS 허용 설정 (Unity, 웹 등 외부 클라이언트와 통신 시 필요)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # 배포 시 수정 권장
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# 모델 및 토크나이저 전역 로딩
model, tokenizer = load_inference_model()

# 요청 본문 스키마 정의
class URLRequest(BaseModel):
    url: str

@app.post("/analyze_url/")
async def analyze_url(request: URLRequest):
    url = request.url.strip()

    # 1. DB에서 URL 해시 기준 조회
    db_result = get_urlbert_info_from_db(url)

    # 2. regardless of DB 여부 → 항상 모델 분석 수행
    result = classify_url_and_explain(url, model, tokenizer)

    # 3. DB에 없다면 저장
    if db_result is None:
        save_urlbert_to_db(result)
        message = "분석을 수행했습니다."
    else:
        message = "이미 저장된 URL입니다. 분석은 수행되었습니다."

    # 4. 사용자에겐 항상 model 결과 제공 + 메시지 다르게
    response = {
        "message": message,
        "url": url,
        "label": result['is_malicious'],
        "confidence": result['confidence'],
        "summary": result['reason_summary'],
        "explanation": result['detailed_explanation']
    }

    return JSONResponse(content=response)

if __name__ == "__main__":
    uvicorn.run("bot.api_server:app", host="0.0.0.0", port=8000, reload=True)
