# models/user_dao.py
import uuid
from Server.DB_conn import get_connection

class UserDAO:
    @staticmethod
    def find_by_email(email):
        conn = get_connection()
        try:
            with conn.cursor() as cursor:
                # ✅ 불필요한 조건 제거 (is_deleted 없음)
                sql = "SELECT * FROM User WHERE email = %s"
                cursor.execute(sql, (email,))
                return cursor.fetchone()
        finally:
            conn.close()

    @staticmethod
    def create_user(email, password, nickname, birth_date, gender, is_guest=False):  # ✅ 인자 추가
        user_id = str(uuid.uuid4())  # UUID로 id 생성
        conn = get_connection()
        try:
            with conn.cursor() as cursor:
                sql = """
                    INSERT INTO User (
                        id, email, password, nickname, birth_date, gender, created_at, role, status, is_guest
                    )
                    VALUES (%s, %s, %s, %s, %s, %s, NOW(), 'USER', 'ACTIVATE', %s)
                """
                cursor.execute(sql, (
                    user_id,
                    email,
                    password,
                    nickname,
                    birth_date,
                    gender,
                    1 if is_guest else 0  # ✅ True이면 1, 아니면 0
                ))
                conn.commit()
                return user_id
        finally:
            conn.close()