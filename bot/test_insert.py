# bot/test_insert.py
import os, sys
repo_root = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
if repo_root not in sys.path:
    sys.path.insert(0, repo_root)

from Server.DB_conn import get_connection

def test_insert():
    conn = get_connection()
    if conn is None:
        print("❌ 연결에 실패했습니다.")
        return

    sample_url = "https://example.com/insert_test"
    # 최소한 URL만 넣어서 쿼리 동작 여부 검증
    sql = "INSERT INTO UrlFeatureRaw (url) VALUES (%s);"

    try:
        with conn.cursor() as cur:
            cur.execute(sql, (sample_url,))
        print("✅ 더미 삽입 성공!")
    except Exception as e:
        print("❌ 삽입 에러:", e)

if __name__ == "__main__":
    test_insert()
