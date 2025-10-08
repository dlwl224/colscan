# Server/models/history_dao.py
from typing import Tuple
from Server.DB_conn import get_connection

class HistoryDAO:

    GUEST_LIMIT = 5  # ✅ 비회원 최대 5개

    # ========= 오늘/어제 카운트 =========
    @staticmethod
    def get_today_yesterday_counts(user_id: str) -> Tuple[int, int]:
        """
        DB 서버 시간(현재 KST, time_zone=SYSTEM)을 기준으로 '오늘/어제' 집계.
        - 오늘: [CURDATE(), CURDATE()+1)
        - 어제: [CURDATE()-1, CURDATE())
        """
        sql = """
            SELECT
              SUM(scanned_at >= CURDATE() AND scanned_at < (CURDATE() + INTERVAL 1 DAY)) AS today_cnt,
              SUM(scanned_at >= (CURDATE() - INTERVAL 1 DAY) AND scanned_at < CURDATE()) AS yday_cnt
            FROM History
            WHERE user_id = %s
        """
        conn = get_connection()
        try:
            with conn.cursor() as c:
                c.execute(sql, (user_id,))
                row = c.fetchone()
                if not row:
                    return 0, 0
                # DictCursor 또는 tuple 모두 대응
                if isinstance(row, dict):
                    return int(row.get("today_cnt") or 0), int(row.get("yday_cnt") or 0)
                return int(row[0] or 0), int(row[1] or 0)
        finally:
            try: conn.close()
            except: pass

    @staticmethod
    def get_history_summary(user_id: str):
        """
        해당 사용자/게스트의 전체, 정상, 악성 히스토리 개수를 집계합니다.
        결과: {'total': int, 'legit': int, 'malicious': int}
        """
        sql = """
            SELECT
                COUNT(*) AS total,
                SUM(CASE WHEN result_label = 'LEGITIMATE' THEN 1 ELSE 0 END) AS legit,
                SUM(CASE WHEN result_label = 'MALICIOUS' THEN 1 ELSE 0 END) AS malicious
            FROM History
            WHERE user_id = %s
        """
        conn = get_connection()
        try:
            # DictCursor를 가정하고 row.items()를 사용합니다.
            with conn.cursor() as c: 
                c.execute(sql, (user_id,))
                row = c.fetchone()
                if not row:
                    return {'total': 0, 'legit': 0, 'malicious': 0}
                return {k: int(v or 0) for k, v in row.items()}
        finally:
            try: conn.close()
            except: pass
            
    @staticmethod
    def can_guest_save_more(guest_id: str) -> bool:
        """게스트가 더 저장 가능(5개 미만)인지"""
        conn = get_connection()
        try:
            with conn.cursor() as c:
                c.execute("SELECT COUNT(*) AS cnt FROM History WHERE user_id = %s", (guest_id,))
                row = c.fetchone() or {}
                return (row.get("cnt", 0) < HistoryDAO.GUEST_LIMIT)
        finally:
            conn.close()

    @staticmethod
    def save_history(user_id_or_guest_id, url, label):
        """
        분석 결과를 History 테이블에 저장
        * 게스트: 5개까지만 허용(넘으면 저장 안 함)
        * 중복 URL은 저장 안 함
        """
        connection = get_connection()
        try:
            with connection.cursor() as cursor:
                # 중복 URL 검사(해당 유저/게스트 기준)
                check_sql = "SELECT 1 FROM History WHERE user_id = %s AND url = %s"
                cursor.execute(check_sql, (user_id_or_guest_id, url))
                if cursor.fetchone():
                    return False  # 이미 존재

                # 게스트 제한
                if HistoryDAO._is_guest(user_id_or_guest_id):
                    # 5개 넘으면 저장 금지
                    if not HistoryDAO.can_guest_save_more(user_id_or_guest_id):
                        return False

                # 저장
                sql = """
                    INSERT INTO History (user_id, url, result_label, scanned_at)
                    VALUES (%s, %s, %s, NOW())
                """
                cursor.execute(sql, (user_id_or_guest_id, url, label))
                connection.commit()
                return True
        finally:
            connection.close()

    @staticmethod
    def _is_guest(user_id):
        """User 테이블에 없거나, is_guest=1이면 게스트로 간주."""
        conn = get_connection()
        try:
            with conn.cursor() as cursor:
                cursor.execute("SELECT is_guest FROM User WHERE id = %s", (user_id,))
                row = cursor.fetchone()
                if not row:
                    return True
                return row.get("is_guest", 0) == 1
        finally:
            conn.close()

    @staticmethod
    def get_user_history(user_id):
        """로그인 사용자의 전체 분석 이력(필요시 기존 함수 유지)"""
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
    def get_user_history_paginated(user_id: str, page: int = 1, per_page: int = 10, q: str | None = None):
        """
        회원 히스토리 페이지네이션 + URL 검색.
        반환: (rows, total_count)
        """
        offset = (max(page, 1) - 1) * per_page
        connection = get_connection()
        try:
            with connection.cursor() as c:
                # 총 개수
                if q:
                    count_sql = """
                        SELECT COUNT(*) AS cnt
                        FROM History
                        WHERE user_id = %s AND url LIKE %s
                    """
                    c.execute(count_sql, (user_id, f"%{q}%"))
                else:
                    count_sql = "SELECT COUNT(*) AS cnt FROM History WHERE user_id = %s"
                    c.execute(count_sql, (user_id,))
                total = (c.fetchone() or {}).get("cnt", 0)

                # 페이지 데이터
                if q:
                    list_sql = """
                        SELECT url, result_label AS label, scanned_at AS analyzed_at
                        FROM History
                        WHERE user_id = %s AND url LIKE %s
                        ORDER BY scanned_at DESC
                        LIMIT %s OFFSET %s
                    """
                    c.execute(list_sql, (user_id, f"%{q}%", per_page, offset))
                else:
                    list_sql = """
                        SELECT url, result_label AS label, scanned_at AS analyzed_at
                        FROM History
                        WHERE user_id = %s
                        ORDER BY scanned_at DESC
                        LIMIT %s OFFSET %s
                    """
                    c.execute(list_sql, (user_id, per_page, offset))

                rows = c.fetchall() or []
                return rows, total
        finally:
            connection.close()

    @staticmethod
    def get_guest_history(guest_id, limit=GUEST_LIMIT):
        """비로그인 사용자의 최근 분석 기록(최대 5개)"""
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
        """해당 사용자/게스트 히스토리 개수"""
        conn = get_connection()
        try:
            with conn.cursor() as cursor:
                cursor.execute("SELECT COUNT(*) AS cnt FROM History WHERE user_id = %s", (user_id,))
                row = cursor.fetchone()
                return (row or {}).get("cnt", 0)
        finally:
            conn.close()

    @staticmethod
    def migrate_guest_to_user(guest_id, user_id):
        """guest_id로 저장된 기록을 로그인한 user_id로 이전"""
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
