# bot/qr_analysis.py (이전 analysis_logic.py에서 이름 변경 및 로직 수정)

from urlbert.urlbert2.core.urlbert_analyzer import classify_url_and_explain
from Server.db_manager import get_urlbert_info_from_db, save_urlbert_to_db
from urlbert.urlbert2.core.model_loader import load_inference_model

# --- 모델 로딩 ---
urlbert_model, urlbert_tokenizer = load_inference_model()

def get_analysis_for_qr_scan(url: str) -> dict:
    """
    URL을 받아 DB에 이력이 있는지 먼저 확인하고, '항상' 모델 분석을 수행한 뒤,
    결과를 DB에 저장/업데이트하고, 출처('source')를 포함하여 반환합니다.
    """
    # 1. DB에 이력이 있는지 '먼저' 확인해서, 이 URL이 처음인지 아닌지만 기록합니다.
    is_existing_in_db = get_urlbert_info_from_db(url) is not None
    
    # 2. DB에 있든 없든 '항상' 모델로 최신 분석을 수행합니다.
    model_result = classify_url_and_explain(url, urlbert_model, urlbert_tokenizer)
    
    # 3. 분석 결과를 DB에 저장합니다 (없으면 INSERT, 있으면 UPDATE).
    save_urlbert_to_db(model_result)
    
    # 4. 프론트엔드에 전달할 결과와 함께 'source'를 결정하여 반환합니다.
    label = "MALICIOUS" if model_result.get("is_malicious") == 1 else "LEGITIMATE"
    
    return {
        "url": model_result.get("url"),
        "label": label,
        "confidence": model_result.get("confidence"),
        "source": "database" if is_existing_in_db else "new" # 출처 명시 (database / new)
    }