# Server/models/board_dao.py
from typing import List, Dict, Any, Optional
from urllib.parse import urlparse
from Server.DB_conn import get_connection
import hashlib
from Server.models.urlbert_dao import UrlBertDAO # UrlBertDAO 임포트 (upsert_board 사용)

def _normalize_url(u: str) -> str:
    u = (u or "").strip()
    if not u:
        return u
    if not (u.startswith("http://") or u.startswith("https://")):
        u = "http://" + u
    return u

def _domain_of(u: str) -> str:
    try:
        return urlparse(_normalize_url(u)).hostname or "-"
    except Exception:
        return "-"

def _md5(s: str) -> str:
    return hashlib.md5(s.encode("utf-8")).hexdigest()

_ALLOWED_JUDG = {"LEGITIMATE", "MALICIOUS", "PENDING"} # 💡 [수정] 판단 시 사용할 영문 값은 그대로 유지

class BoardDAO:
    @staticmethod
    def list_reports(page: int, size: int, q: str, reporter_id: str, is_admin: bool) -> List[Dict[str, Any]]:
        # 6. 신고 내역은 본인만 확인 가능 (ADMIN 제외)
        offset = max(0, (page - 1) * size)
        q_like = f"%{q.strip()}%" if q else "%"

        # 💡 reporter_id를 header_info에 기록된 값으로 찾습니다.
        # [수정 확인] reporter_search_pattern이 제대로 생성되는지 확인합니다.
        # 💡 [수정] ADMIN 여부에 따라 필터링 조건을 동적으로 설정
        report_filter = "reporter_id = %s"
        filter_params = [reporter_id]
        
        if is_admin:
            # ADMIN일 경우 모든 신고 내역을 조회하도록 필터링 조건을 TRUE로 변경
            report_filter = "TRUE"
            filter_params = [] # reporter_id 필터링을 사용하지 않으므로 매개변수에서 제거

        conn = get_connection()
        try:
            with conn.cursor() as cur:
                sql = f"""
                SELECT id, url, domain, reason,
                       status,
                       judgment, confidence, created_at, updated_at
                FROM url_report
                WHERE {report_filter} /* 동적으로 결정된 필터링 조건 사용 */
                  AND (url LIKE %s OR domain LIKE %s OR reason LIKE %s)
                ORDER BY created_at DESC
                LIMIT %s OFFSET %s
                """
                
                # 최종 쿼리 매개변수 조합
                final_params = filter_params + [q_like, q_like, q_like, size, offset]

                # [DEBUG SQL] 로깅 유지
                print(f"[DEBUG SQL] list_reports reporter_id: {reporter_id}, is_admin: {is_admin}")
                print(f"[DEBUG SQL] list_reports query: {sql[:100]}...")
                
                cur.execute(sql, tuple(final_params))
                return cur.fetchall()
        except Exception as e:
            print(f"[ERROR IN DAO] list_reports failed: {type(e).__name__}: {e}")
            raise
        finally:
            conn.close()

    @staticmethod
    def find_report_by_id(report_id: int) -> Optional[Dict[str, Any]]:
        """ 특정 신고 ID로 신고 내역을 조회합니다. (관리자 심사, 악성 로그 기록 용도) """
        conn = get_connection()
        try:
            with conn.cursor() as cur:
                sql = """
                SELECT id, url, domain, reason, status, judgment, confidence, reporter_id, 
                 reporter_nick, created_at, updated_at AS status_updated_at 
                FROM url_report
                WHERE id = %s
                """
                cur.execute(sql, (report_id,))
                return cur.fetchone()
        finally:
            conn.close()

    @staticmethod
    def create_report(url: str, reason: Optional[str],
                      reporter_id: Optional[str], reporter_nick: Optional[str]) -> int:
        url_norm = _normalize_url(url)
        domain   = _domain_of(url_norm)
        reason_text = reason if reason else "URL 신고 (사유 없음)"
        # 💡 Status 500 오류 방지 위해 None 대신 문자열 'NONE'/'익명' 사용
        safe_reporter_id = reporter_id or 'NONE' 
        safe_reporter_nick = reporter_nick or '익명'
        
        # ✅ [수정] url_report 테이블에만 저장. urlbert_analysis에는 저장하지 않습니다.
        conn = get_connection()
        try:
            with conn.cursor() as cur:
                sql = """
                INSERT INTO url_report (
                    url, domain, reason, status, judgment, confidence, reporter_id, reporter_nick, created_at
                ) VALUES (
                    %s, %s, %s, '확인중', NULL, NULL, %s, %s, NOW()
                    /* ✅ [수정] 한글 '확인중' 사용, judgment와 confidence는 NULL로 삽입 */
                )
                """
                cur.execute(sql, (
                    url_norm, domain, reason_text, safe_reporter_id, safe_reporter_nick
                ))
                conn.commit()
                return cur.rowcount 
        finally:
            conn.close()

    @staticmethod
    def list_malicious(page: int, size: int, q: str) -> List[Dict[str, Any]]:
        offset = max(0, (page - 1) * size)
        q_like = f"%{q.strip()}%" if q else "%"
        conn = get_connection()
        try:
            with conn.cursor() as cur:
                sql = """
                SELECT
                  id,
                  url,
                  domain,
                  'REPORT' AS source,
                  CASE
                    WHEN confidence >= 0.85 THEN '높음'
                    WHEN confidence >= 0.60 THEN '보통'
                    ELSE '낮음'
                  END AS severity,
                  created_at AS detected_at
                FROM url_report
                WHERE judgment = 'MALICIOUS'
                  AND (url LIKE %s OR domain LIKE %s)
                ORDER BY created_at DESC
                LIMIT %s OFFSET %s
                """
                cur.execute(sql, (q_like, q_like, size, offset))
                return cur.fetchall()
        finally:
            conn.close()

    @staticmethod
    def update_judgment(report_id: int, judgment: Optional[str],
                        confidence: Optional[float], updater_id: Optional[str]) -> int:
        if judgment is not None:
            j = judgment.strip().upper()
            if j not in _ALLOWED_JUDG:
                raise ValueError("judgment must be LEGITIMATE, MALICIOUS, or PENDING")
        
        # 💡 [수정] DB에 저장할 한글 상태 값 (새로운 VARCHAR 스키마에 맞춤)
        status_kor = '정상' if judgment == 'LEGITIMATE' else '악성' if judgment == 'MALICIOUS' else '확인중'
        
        # 신고 정보 조회 (UrlBertDAO에 넘길 정보와 url_to_analyze를 가져오기 위함)
        report = BoardDAO.find_report_by_id(report_id)
        if not report:
             raise ValueError(f"Report ID {report_id} not found")
        
        url_to_analyze = report['url']
        
        conn = get_connection()
        try:
            with conn.cursor() as cur:
                # 1. url_report 테이블 상태 업데이트
                sql_report = """
                UPDATE url_report
                    SET judgment  = %s,
                        status    = %s,
                        confidence = %s,
                        updated_by = %s,
                        updated_at = CURRENT_TIMESTAMP
                    WHERE id = %s
                """
                cur.execute(sql_report, (judgment, status_kor, confidence, updater_id, report_id))
                
                # 2. ✅ [핵심 변경] 악성/정상 확정 시에만 UrlBertDAO.upsert_board 호출
                if judgment in ('MALICIOUS', 'LEGITIMATE'):
                    true_label = 1 if judgment == 'MALICIOUS' else 0
                    
                    # UrlBertDAO에 넘겨줄 header_info 재구성 (신고 시점 정보)
                    temp_header_info = (
                        f"REPORTER_ID:{report.get('reporter_id') or 'NONE'} | "
                        f"REPORTER_NICK:{report.get('reporter_nick') or '익명'} | "
                        f"REASON:{report.get('reason') or 'No reason provided'}"
                    )
                    
                    # 💡 새로 정의된 upsert_board 함수 호출 (UrlBertDAO에 있어야 함)
                    UrlBertDAO.upsert_board( 
                        url=url_to_analyze,
                        true_label=true_label,
                        confidence=confidence,
                        header_info=temp_header_info
                    )
                
                conn.commit()
                return cur.rowcount
        finally:
            conn.close()