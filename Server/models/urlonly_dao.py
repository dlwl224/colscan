# models/urlonly_dao.py

from DB_conn import get_connection_dict

class UrlOnlyDAO:
    @staticmethod
    def exists(url):
        conn = get_connection_dict()
        try:
            with conn.cursor() as cursor:
                sql = "SELECT 1 FROM UrlOnly WHERE url = %s LIMIT 1"
                cursor.execute(sql, (url,))
                return cursor.fetchone() is not None
        finally:
            conn.close()
