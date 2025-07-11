from transformers import AutoTokenizer, AutoModelForCausalLM
import torch

# 사용하려는 Llama 3 모델의 Hugging Face ID (기반 모델)
model_id = "meta-llama/Meta-Llama-3-8B" # Instruct 모델이 아닌 기반 모델

print(f"모델을 로드 중: {model_id}")

# 토크나이저 로드
tokenizer = AutoTokenizer.from_pretrained(model_id)
print("토크나이저 로드 완료.")

# 모델 로드 (GPU 사용 시 bfloat16 또는 float16 사용)
# Llama 3는 bfloat16을 권장합니다. GPU가 bfloat16을 지원하는지 확인하세요 (NVIDIA Ampere 아키텍처 이상, RTX 30 시리즈 이상).
# torch.cuda.get_device_properties(0).major >= 8 : bfloat16 지원 여부 확인
if torch.cuda.is_available():
    print("GPU 사용 가능. 모델을 GPU로 로드합니다.")
    # bfloat16 지원 여부에 따라 dtype 결정
    dtype = torch.bfloat16 if torch.cuda.get_device_properties(0).major >= 8 else torch.float16
    print(f"사용할 dtype: {dtype}")
    model = AutoModelForCausalLM.from_pretrained(
        model_id,
        torch_dtype=dtype,
        device_map="auto" # 사용 가능한 GPU에 모델 레이어를 자동으로 분배
    )
else:
    print("GPU를 찾을 수 없습니다. 모델을 CPU로 로드합니다. (매우 느릴 수 있습니다)")
    model = AutoModelForCausalLM.from_pretrained(
        model_id,
        torch_dtype=torch.float32, # CPU에서는 float32 사용
        device_map="cpu"
    )
print("모델 로드 완료.")

# --- 변경된 부분 시작 ---
# Llama 3 기반 모델은 채팅 템플릿에 익숙하지 않습니다.
# 단순 텍스트 프롬프트 사용
prompt = "What is the capital of France?" # 간단한 질문
print(f"프롬프트: {prompt}")

# 프롬프트를 토크나이징하고 모델 디바이스로 이동
input_ids = tokenizer(prompt, return_tensors="pt").input_ids.to(model.device)
# --- 변경된 부분 끝 ---

print("텍스트 생성 시작...")
# 텍스트 생성 파라미터 설정
outputs = model.generate(
    input_ids,
    max_new_tokens=256,   # 최대 생성할 새 토큰 수
    do_sample=True,       # 샘플링 방식 사용 (True 시 temperature, top_k, top_p 적용)
    temperature=0.7,      # 출력의 다양성 조절 (낮을수록 보수적)
    top_k=50,             # 상위 k개 토큰 중에서 샘플링
    top_p=0.95,           # 누적 확률 p 내에서 샘플링
    # 기반 모델은 특별한 EOS/PAD 토큰 설정 없이도 작동하는 경우가 많지만,
    # 필요시 tokenizer.eos_token_id를 사용하거나,
    # 특정 응답 길이에서 자르고 싶다면 max_new_tokens에 의존합니다.
    # pad_token_id=tokenizer.eos_token_id # 기반 모델에서는 생략하거나 None으로 설정 가능
)
print("텍스트 생성 완료.")

# 생성된 부분만 디코딩 (입력 부분 제외)
# Llama 3 기반 모델은 Instruct 모델처럼 깔끔한 응답 형식을 기대하기 어렵습니다.
# raw 출력 그대로를 디코딩하여 볼 수 있습니다.
response = tokenizer.decode(outputs[0], skip_special_tokens=True) # 전체 시퀀스 디코딩
# 또는 입력 프롬프트 부분을 제외하고 디코딩
# response = tokenizer.decode(outputs[0][input_ids.shape[-1]:], skip_special_tokens=True)
print("\n--- 생성된 응답 ---")
print(response)

# 가상 환경 비활성화 (스크립트 종료 후 수동으로)
# deactivate