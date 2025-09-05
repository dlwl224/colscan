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
        
        # 1) DB 조회 (기존 정보 확인용)
        db_res = None
        try:
            db_res = get_urlbert_info_from_db(url)
        except Exception as e:
            print(f"⚠️ DB 조회 오류 ({e}), 계속 진행합니다.")

        # 2) 모델 분석 (DB 존재 여부와 상관없이 무조건 수행)
        result = classify_url_and_explain(url, model, tokenizer)
        rec = {
            "url":              url,
            "header_info":      result.get("header_info"),
            "is_malicious":     int(result["is_malicious"]),
            "confidence":       float(result["confidence"]),
            "true_label":       result.get("true_label", None)
        }

        # 3) DB 저장 (기존 정보 업데이트)
        try:
            save_urlbert_to_db(rec)
        except Exception as e:
            print(f"⚠️ DB 저장 오류 ({e}), 계속 진행합니다.")

        # 4) 결과 반환
        malicious = "🔴 악성" if rec["is_malicious"] else "🟢 정상"
        confidence = f"{rec['confidence']*100:.2f}%"
        header_str = f"헤더: {rec['header_info']}" if rec["header_info"] else ""
        
        # DB에 기존 정보가 있었는지 여부에 따라 메시지 변경
        if db_res:
            return (
                f"[재분석 완료] 이전에 저장된 URL({url})을 재분석했습니다.\n"
                f"{header_str}\n"
                f"악성 여부: {malicious}\n"
                f"신뢰도: {confidence}\n"
            )
        else:
            return (
                f"[신규 분석] 새로운 URL({url})을 분석하고 DB에 저장했습니다.\n"
                f"{header_str}\n"
                f"악성 여부: {malicious}\n"
                f"신뢰도: {confidence}\n"
            )
            
    return Tool(
        name="URLBERT_ThreatAnalyzer",
        func=_analyze,
        description="지정한 URL을 URL-BERT 모델로 분석하여 악성 여부를 판단하고, DB와 연동된 설명을 제공합니다. 이미 저장된 URL도 재분석하여 정보를 업데이트합니다."
    )