# 필요한 라이브러리 및 모듈 임포트
import pymysql  # MySQL 데이터베이스와의 연결을 위한 라이브러리
from dotenv import load_dotenv  # .env 파일에서 환경 변수를 로드하는 라이브러리
import os  # 운영 체제(OS)와 상호작용하기 위한 라이브러리

# .env 파일을 로드하여 환경 변수에 접근할 수 있도록 합니다.
# dotenv_path를 사용하여 현재 파일(__file__)의 디렉토리에 있는 'db.env' 파일을 로드
load_dotenv(dotenv_path=os.path.join(os.path.dirname(__file__), "db.env"))


def get_connection():
    """
    데이터베이스 연결을 생성하는 함수
    1. 환경 변수에서 DB 접속 정보를 가져와 MySQL 서버에 연결을 시도
    2. 연결 성공 시 데이터베이스 연결 객체를 반환
    3. 연결 실패 시 오류 메시지를 출력하고 None을 반환
    """
    
    
    
    try:
        # pymysql.connect()를 사용하여 데이터베이스 연결을 시도
        conn = pymysql.connect(
            host=os.getenv('DB_HOST'),  # 데이터베이스 호스트 주소 (예: 'localhost')
            user=os.getenv('DB_USER'),  # 데이터베이스 사용자 이름
            password=os.getenv('DB_PASSWORD'),  # 데이터베이스 비밀번호
            db=os.getenv('DB_NAME'),  # 접속할 데이터베이스 이름
            port=int(os.getenv('DB_PORT')),  # 데이터베이스 포트 번호 (정수로 변환 필요)
            connect_timeout=5,
            autocommit=True,        # ✅ 자동 커밋 켜기
            cursorclass=pymysql.cursors.DictCursor
        )
        

        # 연결 성공 메시지 출력
        print("✅ MySQL 연결 성공!")
        return conn  # 데이터베이스 연결 객체 반환
    
    except pymysql.MySQLError as e:
        # 데이터베이스 연결 실패 시 오류 메시지 출력
        print(f"❌ MySQL 연결 오류: {e}")
        return None  # 연결 실패 시 None 반환


def get_connection_dict():
    import pymysql.cursors
    try:
        conn = pymysql.connect(
            host=os.getenv('DB_HOST'),
            user=os.getenv('DB_USER'),
            password=os.getenv('DB_PASSWORD'),
            db=os.getenv('DB_NAME'),
            port=int(os.getenv('DB_PORT')),
            connect_timeout=5,
            cursorclass=pymysql.cursors.DictCursor  # ✅ 딕셔너리 형태로 받을 수 있게
        )
        print("✅ [DictCursor] MySQL 연결 성공!")
        return conn
    except pymysql.MySQLError as e:
        print(f"❌ MySQL 연결 오류: {e}")
        return None
    
if __name__ == "__main__":
    # 스크립트를 직접 실행할 경우, 데이터베이스 연결 테스트 실행
    get_connection()
