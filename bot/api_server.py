

from fastapi import FastAPI
from pydantic import BaseModel

# 1. 방금 만든 분석/챗봇 로직 함수들을 불러옵니다.
from bot.qr_analysis import get_analysis_for_qr_scan
from bot.bot_main2 import get_chatbot_response # (bot_main2.py는 아래에서 수정)

app = FastAPI(title="sQanAR 분석 및 챗봇 API")

# --- API가 받을 데이터 형식을 미리 정의 ---
class AnalyzeRequest(BaseModel):
    url: str

class ChatRequest(BaseModel):
    query: str

# --- API '창구' 2개 만들기 ---

# 기능 1: QR 스캔 및 URL 분석용 API
@app.post("/analyze")
def analyze_url_endpoint(req: AnalyzeRequest):
    """URL을 받아 간단한 분석 결과를 반환하는 API"""
    return get_analysis_for_qr_scan(req.url)

# 기능 2: 챗봇용 API
@app.post("/chat")
def chat_endpoint(req: ChatRequest):
    """사용자 질문을 받아 챗봇 답변을 반환하는 API"""
    return get_chatbot_response(req.query)

# --- 서버 실행 명령어 (친구에게 터미널에서 실행하라고 알려주세요) ---
# uvicorn api_server:app --host 0.0.0.0 --port 8000 --reload