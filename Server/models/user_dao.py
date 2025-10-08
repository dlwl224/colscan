# models/user_dao.py
import uuid
from Server.DB_conn import get_connection
from typing import Optional

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

    @staticmethod
    def find_by_email_and_nickname(email, nickname):
        """
        이메일과 닉네임이 모두 일치하는 사용자를 조회합니다.
        비밀번호 재설정 전 사용자 본인 확인 용도입니다.
        """
        conn = get_connection()
        try:
            with conn.cursor() as cursor:
                # id와 password만 가져와서 사용자 인증 및 업데이트에 사용합니다.
                sql = "SELECT id, password FROM User WHERE email = %s AND nickname = %s"
                cursor.execute(sql, (email, nickname))
                return cursor.fetchone()
        finally:
            conn.close()

    @staticmethod
    def update_password(user_id, hashed_password):
        """
        주어진 사용자 ID의 비밀번호를 새로 해시된 비밀번호로 업데이트합니다.
        """
        conn = get_connection()
        try:
            with conn.cursor() as cursor:
                # id를 기준으로 비밀번호 필드를 업데이트합니다.
                sql = "UPDATE User SET password = %s WHERE id = %s"
                cursor.execute(sql, (hashed_password, user_id))
                conn.commit()
                # 성공적으로 업데이트된 경우 True 반환 (또는 영향을 받은 행 수 확인)
                return cursor.rowcount > 0
        except Exception as e:
            # 실제 운영 환경에서는 로그를 남기는 것이 좋습니다.
            print(f"[DB ERROR] Failed to update password for user {user_id}: {e}")
            return False
        finally:
            conn.close()        

    @staticmethod
    def find_user_role(user_id: str) -> Optional[str]:
        """
        주어진 사용자 ID의 role을 조회합니다. (관리자 권한 확인 용도)
        """
        conn = get_connection()
        try:
            with conn.cursor() as cursor:
                sql = "SELECT role FROM User WHERE id = %s"
                cursor.execute(sql, (user_id,))
                result = cursor.fetchone()
                # 'role'은 enum('USER','ADMIN')으로 가정
                return result["role"] if result and "role" in result else None
        finally:
            conn.close()

    @staticmethod
    def find_user_profile_data(user_id: str) -> Optional[dict]:
        """
        주어진 ID의 프로필 수정에 필요한 핵심 정보(비밀번호 제외)를 조회합니다.
        필드: id, email, nickname, birth_date, gender, role
        """
        conn = get_connection()
        try:
            with conn.cursor() as cursor:
                # 💡 비밀번호(password)를 제외하고 필요한 모든 필드를 조회합니다.
                sql = """
                    SELECT id, email, nickname, birth_date, gender, role
                    FROM User
                    WHERE id = %s
                """
                cursor.execute(sql, (user_id,))
                return cursor.fetchone()
        finally:
            conn.close()

    @staticmethod
    def update_nickname(user_id: str, new_nickname: str) -> bool:
        """
        주어진 사용자 ID의 닉네임을 업데이트합니다.
        """
        conn = get_connection()
        try:
            with conn.cursor() as cursor:
                # 닉네임을 기준으로 닉네임 필드를 업데이트합니다.
                sql = "UPDATE User SET nickname = %s WHERE id = %s"
                cursor.execute(sql, (new_nickname, user_id))
                conn.commit()
                return cursor.rowcount > 0
        except Exception as e:
            print(f"[DB ERROR] Failed to update nickname for user {user_id}: {e}")
            return False
        finally:
            conn.close()

    @staticmethod
    def find_hashed_password_by_id(user_id: str) -> Optional[dict]:
        """
        주어진 사용자 ID의 해시된 비밀번호를 조회합니다.
        비밀번호가 기존과 동일한지 확인하는 용도입니다.
        """
        conn = get_connection()
        try:
            with conn.cursor() as cursor:
                # 💡 'password' 필드만 조회
                sql = "SELECT password FROM User WHERE id = %s"
                cursor.execute(sql, (user_id,))
                return cursor.fetchone() # 예: {'password': 'hashed_value'}
        finally:
            conn.close()