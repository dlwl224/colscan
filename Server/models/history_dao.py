from Server.DB_conn import get_connection

class HistoryDAO:

    @staticmethod
    def save_history(user_id_or_guest_id, url, label):
        """
        분석 결과를 History 테이블에 저장
        :param user_id_or_guest_id: 로그인 유저 ID 또는 guest UUID
        :param url: 분석한 URL
        :param label: 결과 라벨 (LEGITIMATE, MALICIOUS, CAUTION)
        """
        connection = get_connection()
        try:
            with connection.cursor() as cursor:
                 # ✅ 1. 중복 URL 검사
                check_sql = "SELECT 1 FROM History WHERE user_id = %s AND url = %s"
                cursor.execute(check_sql, (user_id_or_guest_id, url))
                if cursor.fetchone():
                    return  # 이미 존재 → 저장 안 함

                # ✅ 2. 게스트일 경우 10개 초과 시 FIFO 삭제
                if HistoryDAO._is_guest(user_id_or_guest_id):
                    count_sql = "SELECT COUNT(*) FROM History WHERE user_id = %s"
                    cursor.execute(count_sql, (user_id_or_guest_id,))
                    count = cursor.fetchone()[0]

                    if count >= 10:
                        delete_sql = """
                            DELETE FROM History
                            WHERE user_id = %s
                            ORDER BY scanned_at ASC
                            LIMIT 1
                        """
                        cursor.execute(delete_sql, (user_id_or_guest_id,))

                # ✅ 3. 저장
                sql = """
                    INSERT INTO History (user_id, url, result_label, scanned_at)
                    VALUES (%s, %s, %s, NOW())
                """
                cursor.execute(sql, (user_id_or_guest_id, url, label))
                connection.commit()
        finally:
            connection.close()

    @staticmethod
    def _is_guest(user_id):
        """User 테이블에서 is_guest 여부 확인"""
        conn = get_connection()
        try:
            with conn.cursor() as cursor:
                cursor.execute("SELECT is_guest FROM User WHERE id = %s", (user_id,))
                row = cursor.fetchone()
                return row and row["is_guest"] == 1
        finally:
            conn.close()

    @staticmethod
    def get_user_history(user_id):
        """
        로그인 사용자의 전체 분석 이력 조회
        """
        connection = get_connection()
        try:
            with connection.cursor() as cursor:
                sql = """
                    SELECT url, result_label AS label, scanned_at AS analyzed_at
                    FROM History
                    WHERE user_id = %s
                    ORDER BY scanned_at DESC
                """
                cursor.execute(sql, (user_id,))
                return cursor.fetchall()
        finally:
            connection.close()

    @staticmethod
    def get_guest_history(guest_id, limit=10):
        """
        비로그인 사용자의 최근 분석 기록 조회 (게스트별)
        """
        connection = get_connection()
        try:
            with connection.cursor() as cursor:
                sql = """
                    SELECT url, result_label AS label, scanned_at AS analyzed_at
                    FROM History
                    WHERE user_id = %s
                    ORDER BY scanned_at DESC
                    LIMIT %s
                """
                cursor.execute(sql, (guest_id, limit))
                return cursor.fetchall()
        finally:
            connection.close()
    
    @staticmethod
    def count_by_user_id(user_id):
        """해당 사용자 히스토리 개수"""
        conn = get_connection()
        try:
            with conn.cursor() as cursor:
                cursor.execute("SELECT COUNT(*) FROM History WHERE user_id = %s", (user_id,))
                return cursor.fetchone()[0]
        finally:
            conn.close()

    @staticmethod
    def migrate_guest_to_user(guest_id, user_id):
        """
        guest_id로 저장된 기록을 로그인한 user_id로 이전
        """
        connection = get_connection()
        try:
            with connection.cursor() as cursor:
                sql = """
                    UPDATE History
                    SET user_id = %s
                    WHERE user_id = %s
                """
                cursor.execute(sql, (user_id, guest_id))
                connection.commit()
        finally:
            connection.close()

