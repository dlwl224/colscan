import pymysql.cursors  # 🔑 꼭 필요
from DB_conn import get_connection_dict
from DB_conn import get_connection

class UrlAnalysisDAO:
    @staticmethod
    def find_by_url(url):
        connection = get_connection()
        try:
            with connection.cursor() as cursor:
                sql = """
                    SELECT 
                        label,
                        domain,
                        created_date,
                        expiry_date
                    FROM UrlAnalysis
                    WHERE url = %s
                """
                cursor.execute(sql, (url,)) 
                row = cursor.fetchone()
                print("🧪 가져온 row:", row)

                if row is not None:
                    return {
                        "label": row["label"],
                        "domain": row["domain"],
                        "created_date": row["created_date"],
                        "expiry_date": row["expiry_date"]
                    }
                else:
                    return None
        finally:
            connection.close()
