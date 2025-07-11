# test_db.py

import os, sys
# 현재 파일(__file__) 기준으로 상위 폴더(sQanAR) 경로를 잡아서
# sys.path에 넣어줍니다.
repo_root = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
if repo_root not in sys.path:
    sys.path.insert(0, repo_root)

from Server.DB_conn import get_connection

def test_select():
    conn = get_connection()
    if conn is None:
        print("❌ 연결에 실패했습니다.")
        return
    
    with conn.cursor() as cur:
        cur.execute("SELECT COUNT(*) AS cnt FROM UrlFeatureRaw;")
        result = cur.fetchone()
        print("UrlFeatureRaw 레코드 수:", result['cnt'])

if __name__ == "__main__":
    test_select()
