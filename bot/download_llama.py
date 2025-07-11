from transformers import AutoModelForCausalLM, AutoTokenizer

model_id = "MLP-KTLim/llama-3-Korean-Bllossom-8B"

# 모델과 토크나이저 다운로드
tokenizer = AutoTokenizer.from_pretrained(model_id)
model = AutoModelForCausalLM.from_pretrained(model_id)

# 로컬 디렉토리에 저장 (옵션)
model.save_pretrained("./llama_kor_model")
tokenizer.save_pretrained("./llama_kor_model")

print("✅ 모델 다운로드 및 저장 완료")
