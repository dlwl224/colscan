
import torch
from transformers import AutoTokenizer, AutoModelForCausalLM, BitsAndBytesConfig

def main():
    # 1) 로컬 모델 경로 및 디바이스 설정
    model_path = "./llama_kor_model"
    device = torch.device("cuda" if torch.cuda.is_available() else "cpu")

    # 2) 토크나이저 로드
    tokenizer = AutoTokenizer.from_pretrained(model_path, use_fast=True)

    # 3) 양자화 설정: 8-bit + 부족한 모듈은 CPU 오프로딩
    bnb_config = BitsAndBytesConfig(
        load_in_8bit=True,
        llm_int8_enable_fp32_cpu_offload=True,
    )

    # 4) 모델 로드: quantization_config에 전달, device_map 자동 분산
    model = AutoModelForCausalLM.from_pretrained(
        model_path,
        quantization_config=bnb_config,
        device_map="auto",
    )
    model.eval()

    # 5) 시스템 메시지와 사용자 인스트럭션 설정
    PROMPT = (
        "You are a helpful AI assistant. Please answer the user's questions kindly.\n"
        "당신은 유능한 AI 어시스턴트 입니다. 사용자의 질문에 대해 친절하게 답변해주세요."
    )
    instruction = "서울과학기술대학교의 인공지능응용학과에 대해 소개해줘"

    messages = [
        {"role": "system", "content": PROMPT},
        {"role": "user",   "content": instruction}
    ]

    # 6) 입력 준비: apply_chat_template이 tensor를 반환한다고 가정
    input_ids = tokenizer.apply_chat_template(
        messages,
        add_generation_prompt=True,
        return_tensors="pt"
    )
    input_ids = input_ids.to(device)

    # 7) 추론 실행: mapping error 방지 위해 명시적 키워드 인자 사용
    outputs = model.generate(
        input_ids=input_ids,
        max_new_tokens=256,
        eos_token_id=[
            tokenizer.eos_token_id,
            tokenizer.convert_tokens_to_ids("<|eot_id|>")
        ],
        do_sample=True,
        temperature=0.6,
        top_p=0.9,
        repetition_penalty=1.1
    )

    # 8) 생성된 토큰 디코딩 및 출력
    gen = outputs[0][input_ids.shape[-1]:]
    print(tokenizer.decode(gen, skip_special_tokens=True))

if __name__ == "__main__":
    main()

