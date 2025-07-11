import pandas as pd

# 1. 파일 경로 설정
input_path = "/home/injeolmi/myproject/sQanAR/Server/url_final.csv"
output_path = "/home/injeolmi/myproject/sQanAR/Server/url_final_enum.csv"

# 2. label 정규화 함수 정의
def normalize_label(label):
    mapping = {
        "0": "LEGITIMATE",
        "SAFE": "LEGITIMATE",
        "LEGITIMATE": "LEGITIMATE",
        "1": "CAUTION",
        "SUSPICIOUS": "CAUTION",
        "WARNING": "CAUTION",
        "CAUTION": "CAUTION",
        "2": "MALICIOUS",
        "DANGEROUS": "MALICIOUS",
        "MALICIOUS": "MALICIOUS"
    }
    return mapping.get(str(label).strip().upper(), None)

# 3. CSV 로드
df = pd.read_csv(input_path)
df.columns = df.columns.str.strip()  # 컬럼명 공백 제거

# 4. 라벨 변환
df["label"] = df["label"].apply(normalize_label)

# 5. 저장
df.to_csv(output_path, index=False)
print("✅ url_final_enum.csv 파일 생성 완료")




