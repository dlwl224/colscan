import datetime
from DB_conn import get_connection

class ScanDAO:
    @staticmethod
    def save_scan(qr_code, url):
        """QR 코드 데이터를 MySQL에 저장"""
        connection = get_connection()
        try:
            with connection.cursor() as cursor:
                sql = "INSERT INTO ScanLog (qr_code, url, scanned_at) VALUES (%s, %s, %s)"
                cursor.execute(sql, (qr_code, url, datetime.datetime.now()))
                connection.commit()
                return cursor.lastrowid
        finally:
            connection.close()

    @staticmethod
    def get_scan(scan_id):
        """ID로 QR 코드 데이터 조회"""
        connection = get_connection()
        try:
            with connection.cursor() as cursor:
                sql = "SELECT * FROM ScanLog WHERE scan_id = %s"
                cursor.execute(sql, (scan_id,))
                return cursor.fetchone()
        finally:
            connection.close()

    @staticmethod
    def get_all_scans():
        """모든 QR 코드 데이터 조회"""
        connection = get_connection()
        try:
            with connection.cursor(dictionary=True) as cursor:
                sql = "SELECT url, scanned_at FROM ScanLog ORDER BY scanned_at DESC"
                cursor.execute(sql)
                return cursor.fetchall()
        finally:
            connection.close()
