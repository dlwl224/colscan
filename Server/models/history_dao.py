# from DB_conn import get_connection

# class HistoryDAO:

#     @staticmethod
#     def save_history(user_id, url, label):
#         """
#         분석 결과를 History 테이블에 저장
#         :param user_id: 사용자 ID (익명 포함)
#         :param url: 분석한 URL
#         :param label: 결과 라벨 (예: LEGITIMATE, MALICIOUS, CAUTION)
#         """
#         connection = get_connection()
#         try:
#             with connection.cursor() as cursor:
#                 sql = """
#                     INSERT INTO History (user_id, url, result_label, scanned_at)
#                     VALUES (%s, %s, %s, NOW())
#                 """
#                 cursor.execute(sql, (user_id, url, label))
#                 connection.commit()
#         finally:
#             connection.close()

#     @staticmethod
#     def get_user_history(user_id):
#         """
#         특정 사용자의 분석 이력 조회
#         """
#         connection = get_connection()
#         try:
#             with connection.cursor() as cursor:
#                 sql = """
#                     SELECT url, result_label AS label, scanned_at AS analyzed_at
#                     FROM History
#                     WHERE user_id = %s
#                     ORDER BY scanned_at DESC
#                 """
#                 cursor.execute(sql, (user_id,))
#                 rows = cursor.fetchall()
#                 return rows
#         finally:
#             connection.close()

#     @staticmethod
#     def get_recent_history(limit=10):
#         """
#         로그인하지 않은 사용자를 위한 최근 분석 기록 조회
#         """
#         connection = get_connection()
#         try:
#             with connection.cursor() as cursor:
#                 sql = """
#                     SELECT url, result_label AS label, scanned_at AS analyzed_at
#                     FROM History
#                     ORDER BY scanned_at DESC
#                     LIMIT %s
#                 """
#                 cursor.execute(sql, (limit,))
#                 rows = cursor.fetchall()
#                 return rows
#         finally:
#             connection.close()

from DB_conn import get_connection

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
                sql = """
                    INSERT INTO History (user_id, url, result_label, scanned_at)
                    VALUES (%s, %s, %s, NOW())
                """
                cursor.execute(sql, (user_id_or_guest_id, url, label))
                connection.commit()
        finally:
            connection.close()

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

