import os
import sys
import torch
import torch.nn.functional as F
import requests
import random
import numpy as np
import re
from urllib.parse import urlparse # URL 파싱을 위해 추가

from pytorch_pretrained_bert import BertTokenizer

project_root = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
if project_root not in sys.path:
    sys.path.insert(0, project_root)


from config import (
    PAD_SIZE, DEVICE, CLASS_LABELS, IMPORTANT_HEADERS,
    REQUEST_TIMEOUT_SECONDS
)

# 현재 파일의 디렉토리 (core)
current_dir = os.path.dirname(os.path.abspath(__file__))
# 프로젝트 루트 디렉토리 (urlbert2)
project_root = os.path.abspath(os.path.join(current_dir, '..'))

# 프로젝트 루트 디렉토리를 Python 검색 경로에 추가
if project_root not in sys.path:
    sys.path.insert(0, project_root)

# --- HTTP 헤더 정보 추출 함수 ---
def get_header_info(url: str) -> str:
    user_agents = [
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/114 Safari/537.36",
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 Version/14.0.3 Safari/605.1.15",
        "Mozilla/5.0 (iPhone; CPU iPhone OS 14_6 like Mac OS X) AppleWebKit/605.1.15 Version/14.0 Mobile/15E148 Safari/604.1"
    ]
    headers = {
        "User-Agent": random.choice(user_agents),
        "Accept-Language": "en-US,en;q=0.9",
        "Referer": "https://www.google.com/"
    }

    try:
        response = requests.get(url, headers=headers, timeout=REQUEST_TIMEOUT_SECONDS, allow_redirects=True)
        resp_headers = response.headers
        
        important = {
            k: resp_headers.get(k, "") for k in IMPORTANT_HEADERS
        }
        header_str = ", ".join(f"{k}: {v}" for k, v in important.items() if v)
        return header_str if header_str else "NOHEADER"
    except requests.exceptions.RequestException:
        return "NOHEADER"
    except Exception:
        return "NOHEADER"

# --- 데이터 전처리 함수 ---
def preprocess_url_for_inference(url: str, header_info: str, tokenizer: BertTokenizer, pad_size: int = PAD_SIZE):
    text = f"{url} [SEP] {header_info}"
    tokenized_text = tokenizer.tokenize(text)
    
    tokens = ["[CLS]"] + tokenized_text + ["[SEP]"]
    ids = tokenizer.convert_tokens_to_ids(tokens)
    types = [0] * (len(ids))
    masks = [1] * len(ids)

    if len(ids) < pad_size:
        types = types + [1] * (pad_size - len(ids))
        masks = masks + [0] * (pad_size - len(ids))
        ids = ids + [0] * (pad_size - len(ids))
    else:
        types = types[:pad_size]
        masks = masks[:pad_size]
        ids = ids[:pad_size]

    assert len(ids) == len(masks) == len(types) == pad_size

    return (
        torch.tensor([ids], dtype=torch.long).to(DEVICE),
        torch.tensor([types], dtype=torch.long).to(DEVICE),
        torch.tensor([masks], dtype=torch.long).to(DEVICE)
    )


# --- 1. 모델 예측만 수행하는 함수 ---
def predict_url(url: str, model, tokenizer) -> dict:
    header_info = get_header_info(url)
    
    input_ids, input_types, input_masks = preprocess_url_for_inference(
        url, header_info, tokenizer, PAD_SIZE
    )

    with torch.no_grad():
        outputs = model([input_ids, input_types, input_masks])
        probabilities = F.softmax(outputs, dim=1)
        predicted_class_id = torch.argmax(probabilities, dim=1).item()

    predicted_label = CLASS_LABELS[predicted_class_id]
    confidence = probabilities[0][predicted_class_id].item() # 0~1 사이 값으로 반환
    
    return {
        "predicted_label": predicted_label,
        "confidence": confidence, # 0~1 사이 값으로 반환
        "predicted_class_id": predicted_class_id,
        "header_info": header_info # LIME 설명을 위해 헤더 정보도 함께 반환
    }
# --- 3. URL 분류 및 설명을 통합하는 함수 ---
def classify_url_and_explain(url: str, model, tokenizer) -> dict:
    # 1) URL 예측 수행
    pred_out = predict_url(url, model, tokenizer)

  


    # 3) DB 저장용 필드명에 맞춰서 dict 반환
    is_mal = 1 if pred_out["predicted_label"] == "malicious" else 0

    return {
        "url": url,
        "header_info": pred_out["header_info"],
        "is_malicious": is_mal,
        "confidence": pred_out["confidence"],    # float 타입
        "true_label": None                 
        
    }
