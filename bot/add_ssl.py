import ssl
import socket
from datetime import datetime

# SSL 인증서 정보 추출 함수
# 단일 호스트명에 대해 인증서 유효기간(일)과 발급기관을 반환
# 임포트 시 바로 실행되지 않고, 필요한 곳에서만 호출됩니다.
def get_ssl_cert_info(hostname: str):
    try:
        ctx = ssl.create_default_context()
        with ctx.wrap_socket(socket.socket(), server_hostname=hostname) as s:
            s.settimeout(3)
            s.connect((hostname, 443))
            cert = s.getpeercert()

        not_before = datetime.strptime(cert['notBefore'], "%b %d %H:%M:%S %Y %Z")
        not_after  = datetime.strptime(cert['notAfter'],  "%b %d %H:%M:%S %Y %Z")
        period     = (not_after - not_before).days
        issuer     = " ".join([entry[0][1] for entry in cert.get('issuer', [])])
        return hostname, period, issuer
    except Exception:
        # 연결 실패나 포맷 오류 시 None으로 채웁니다
        return hostname, None, None

if __name__ == "__main__":
    import pandas as pd
    from concurrent.futures import ThreadPoolExecutor, as_completed
    from urllib.parse import urlparse
    from tqdm import tqdm

    # 파일 경로 설정
    INPUT_CSV  = 'final_feature.csv'
    OUTPUT_CSV = 'final_feature_2.csv'

    # 1) CSV 로드
    df = pd.read_csv(INPUT_CSV)
    # 'Domain' 컬럼을 호스트명으로 사용
    df['hostname'] = df['Domain'].apply(lambda u: urlparse(u).netloc.lstrip('www.'))

    # 2) 고유 호스트명 리스트
    hostnames = df['hostname'].dropna().unique().tolist()

    # 3) 병렬로 SSL 정보 수집
    results = {}
    with ThreadPoolExecutor(max_workers=30) as executor:
        future_map = {executor.submit(get_ssl_cert_info, h): h for h in hostnames}
        for fut in tqdm(as_completed(future_map), total=len(future_map), desc="Fetching SSL info"):
            hostname, days, issuer = fut.result()
            results[hostname] = (days, issuer)

    # 4) 결과 매핑
    df['cert_total_days'] = df['hostname'].map(lambda h: results.get(h, (None,None))[0])
    df['cert_issuer']     = df['hostname'].map(lambda h: results.get(h, (None,None))[1])

    # 5) 불필요 컬럼 제거 및 저장
    df.drop(columns=['hostname'], inplace=True)
    df.to_csv(OUTPUT_CSV, index=False)
    print(f"✅ SSL features saved to {OUTPUT_CSV}")