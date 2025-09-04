# models/urlbert_dao.py
from typing import Optional, Dict, Any
from urllib.parse import urlparse
from Server.DB_conn import get_connection

def _label_from_bits(is_malicious: int, confidence: Optional[float]) -> str:
    # 0=LEGITIMATE, 1=MALICIOUS
    return "MALICIOUS" if is_malicious == 1 else "LEGITIMATE"

class UrlBertDAO:
    @staticmethod
    def exists(url: str) -> bool:
        conn = get_connection()
        try:
            with conn.cursor() as cursor:
                cursor.execute("SELECT 1 FROM urlbert_analysis WHERE url_hash = MD5(%s) LIMIT 1", (url,))
                return cursor.fetchone() is not None
        finally:
            conn.close()

    @staticmethod
    def find_by_url(url: str) -> Optional[Dict[str, Any]]:
        """
        반환 형식(프론트 호환용):
        {
          "label": "LEGITIMATE|MALICIOUS",
          "domain": "example.com" 또는 "-",
          "is_malicious": 0/1,
          "confidence": float|None,
          "true_label": int|None,
          "header_info": str|None,
          "analysis_date": datetime,
          "url": str
        }
        """

        url = (url or "").strip()
        conn = get_connection()
        try:
            with conn.cursor() as cursor:
                sql = """
                SELECT url, header_info, is_malicious, confidence, true_label, analysis_date
                FROM urlbert_analysis
                WHERE url_hash = MD5(%s)
                """
                cursor.execute(sql, (url,))
                row = cursor.fetchone()
                if not row:
                    return None

                label = _label_from_bits(row["is_malicious"], row.get("confidence"))
                domain = urlparse(row["url"]).hostname or "-"
                return {
                    "label": label,
                    "domain": domain,
                    "is_malicious": row["is_malicious"],
                    "confidence": row.get("confidence"),
                    "true_label": row.get("true_label"),   # ✅ 포함
                    "header_info": row.get("header_info"),
                    "analysis_date": row.get("analysis_date"),
                    "url": row["url"],                    # ✅ 원본 url 포함(디버깅 편의)
                }
        finally:
            conn.close()

    @staticmethod
    def upsert_prediction(
        url: str,
        is_malicious: int,
        confidence: Optional[float] = None,
        header_info: Optional[str] = None,
        true_label: Optional[int] = None
    ) -> int:
        """
        기존 있으면 UPDATE, 없으면 INSERT. 반환: 영향 행 수(1)
        """
        url = (url or "").strip()
        conn = get_connection()
        try:
            with conn.cursor() as cursor:
                sql = """
                INSERT INTO urlbert_analysis (url, url_hash, header_info, is_malicious, confidence, true_label, analysis_date)
                VALUES (%s, MD5(%s), %s, %s, %s, %s, NOW())
                ON DUPLICATE KEY UPDATE
                  header_info = VALUES(header_info),
                  is_malicious = VALUES(is_malicious),
                  confidence = VALUES(confidence),
                  true_label = VALUES(true_label),
                  analysis_date = NOW()
                """
                cursor.execute(sql, (url, url, header_info, is_malicious, confidence, true_label))
                conn.commit()
                return cursor.rowcount
        finally:
            conn.close()