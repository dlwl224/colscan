# ColScan - 데이터 플로우 다이어그램 (Data Flow Diagram)

## 시스템 데이터 흐름 개요

ColScan은 QR 코드 스캔을 통한 URL 보안 분석 및 AI 기반 챗봇 서비스를 제공하는 통합 보안 플랫폼입니다.

---

## 전체 데이터 플로우

```mermaid
flowchart TB
    subgraph Client["클라이언트 레이어"]
        Mobile["모바일 앱<br/>(React Native)"]
        QRScanner["QR 스캐너"]
        ChatUI["챗봇 UI"]
        HistoryUI["이력 조회 UI"]
    end

    subgraph FlaskServer["Flask 서버 (Backend)"]
        direction TB
        AppRouter["app.py<br/>Flask Router"]
        
        subgraph Routes["라우트 모듈"]
            ScanRoute["scan.py<br/>스캔 처리"]
            AnalyzeRoute["analyze.py<br/>URL 분석"]
            ChatbotRoute["chatbot.py<br/>챗봇 API"]
            HistoryRoute["history.py<br/>이력 관리"]
            AuthRoute["auth.py<br/>인증/세션"]
        end
        
        DBManager["db_manager.py<br/>DB 연결 관리"]
        SessionMgr["세션 관리<br/>(guest_id/user_id)"]
    end

    subgraph AIServices["AI 서비스 레이어"]
        direction TB
        
        subgraph URLBERTService["URL-BERT 분석"]
            URLBERTModel["URL-BERT Model<br/>(PyTorch)"]
            URLBERTTokenizer["URL Tokenizer"]
            ModelInference["model_loader.py<br/>추론 엔진"]
        end
        
        subgraph ChatbotService["Langchain 챗봇"]
            LangchainAgent["Langchain Agent<br/>(ReAct)"]
            LlamaLLM["Llama-3-Korean<br/>(GGUF)"]
            
            subgraph Tools["Agent Tools"]
                URLBERTTool["URLBERT Tool<br/>URL 위협 분석"]
                RAGTool["RAG Tool<br/>보안 문서 검색"]
                ChatTool["Chat Tool<br/>일반 대화"]
            end
        end
        
        subgraph RAGSystem["RAG (검색 증강 생성)"]
            FAISSIndex["FAISS Vector Index<br/>보안 문서 임베딩"]
            RAGDataset["rag_dataset.jsonl<br/>보안 지식 베이스"]
        end
        
        subgraph ExternalAPI["외부 API"]
            GeminiAPI["Google Gemini API<br/>(선택적 사용)"]
        end
    end

    subgraph Database["데이터베이스 레이어"]
        MySQL[(MySQL DB)]
        
        subgraph Tables["테이블 구조"]
            URLTable["url_scans<br/>- url<br/>- result<br/>- timestamp"]
            UserTable["users<br/>- user_id<br/>- guest_id<br/>- session_data"]
            HistoryTable["scan_history<br/>- user_id<br/>- url<br/>- analysis_result"]
            ChatTable["chat_logs<br/>- user_id<br/>- message<br/>- response"]
        end
    end

    %% 데이터 흐름: QR 스캔 → URL 분석
    Mobile -->|1. QR 코드 스캔| QRScanner
    QRScanner -->|2. URL 추출| ScanRoute
    ScanRoute -->|3. 분석 요청| AnalyzeRoute
    AnalyzeRoute -->|4. URL 데이터| URLBERTService
    URLBERTModel -->|5. 위협 분석 결과<br/>(안전/위험)| AnalyzeRoute
    AnalyzeRoute -->|6. 결과 저장| DBManager
    DBManager -->|7. DB 쓰기| URLTable
    AnalyzeRoute -->|8. 분석 결과 반환| Mobile
    Mobile -->|9. AR 경고 표시| QRScanner

    %% 데이터 흐름: 챗봇 대화
    ChatUI -->|10. 사용자 질문| ChatbotRoute
    ChatbotRoute -->|11. 질문 전달| LangchainAgent
    
    LangchainAgent -->|12a. URL 포함 시| URLBERTTool
    URLBERTTool -->|13a. URL 분석| URLBERTModel
    
    LangchainAgent -->|12b. 보안 질문 시| RAGTool
    RAGTool -->|13b. 문서 검색| FAISSIndex
    FAISSIndex -->|14b. 관련 문서 반환| RAGTool
    RAGTool -->|15b. 컨텍스트 제공| LlamaLLM
    
    LangchainAgent -->|12c. 일반 대화 시| ChatTool
    ChatTool -->|13c. 직접 응답| LlamaLLM
    
    LlamaLLM -->|16. 최종 응답 생성| LangchainAgent
    LangchainAgent -->|17. 응답 반환| ChatbotRoute
    ChatbotRoute -->|18. 대화 로그 저장| DBManager
    DBManager -->|19. DB 쓰기| ChatTable
    ChatbotRoute -->|20. 응답 전달| ChatUI

    %% 데이터 흐름: 이력 조회
    HistoryUI -->|21. 이력 요청| HistoryRoute
    HistoryRoute -->|22. 세션 검증| SessionMgr
    SessionMgr -->|23. user_id 확인| AuthRoute
    HistoryRoute -->|24. 이력 조회| DBManager
    DBManager -->|25. DB 읽기| HistoryTable
    HistoryTable -->|26. 이력 데이터| DBManager
    DBManager -->|27. 데이터 반환| HistoryRoute
    HistoryRoute -->|28. 이력 표시| HistoryUI

    %% 인증 및 세션
    Mobile -->|세션 쿠키| SessionMgr
    SessionMgr <-->|세션 데이터| UserTable

    %% RAG 데이터 빌드 (오프라인)
    RAGDataset -.->|인덱스 생성| FAISSIndex

    %% 외부 API 연동 (선택적)
    LangchainAgent -.->|확장 기능| GeminiAPI

    %% 스타일링
    classDef clientStyle fill:#e1f5ff,stroke:#01579b,stroke-width:2px
    classDef serverStyle fill:#fff3e0,stroke:#e65100,stroke-width:2px
    classDef aiStyle fill:#f3e5f5,stroke:#4a148c,stroke-width:2px
    classDef dbStyle fill:#e8f5e9,stroke:#1b5e20,stroke-width:2px
    classDef toolStyle fill:#fff9c4,stroke:#f57f17,stroke-width:1px

    class Mobile,QRScanner,ChatUI,HistoryUI clientStyle
    class FlaskServer,AppRouter,ScanRoute,AnalyzeRoute,ChatbotRoute,HistoryRoute,AuthRoute,DBManager,SessionMgr serverStyle
    class URLBERTService,ChatbotService,RAGSystem,LangchainAgent,LlamaLLM,URLBERTModel,FAISSIndex aiStyle
    class MySQL,URLTable,UserTable,HistoryTable,ChatTable dbStyle
    class URLBERTTool,RAGTool,ChatTool toolStyle
```

---

## 주요 데이터 흐름 설명

### 1️⃣ QR 코드 스캔 → URL 위협 분석 플로우
```
모바일 앱 → QR 스캔 → URL 추출 → Flask /scan 엔드포인트 
→ URL-BERT 모델 추론 → 위협 분석 (안전/위험) 
→ MySQL 저장 → 결과 반환 → AR 경고 표시
```

**핵심 데이터:**
- 입력: QR 코드 이미지 → URL 문자열
- 처리: URL-BERT 토큰화 → 임베딩 → 분류 (0: 안전, 1: 위험)
- 출력: `{result: "safe/dangerous", confidence: 0.95, timestamp: ...}`

---

### 2️⃣ AI 챗봇 대화 플로우
```
사용자 질문 → Flask /chatbot 엔드포인트 → Langchain Agent
→ 도구 선택 (URLBERTTool/RAGTool/ChatTool)
→ 응답 생성 (Llama-3-Korean) → MySQL 로그 저장 → 응답 반환
```

**핵심 데이터:**
- 입력: 사용자 자연어 질문 (예: "큐싱이 뭐야?", "https://example.com 안전해?")
- 처리: 
  - URL 포함 → URL-BERT 분석
  - 보안 개념 → FAISS 벡터 검색 → RAG 컨텍스트 제공
  - 일반 대화 → LLM 직접 응답
- 출력: 한국어 자연어 응답

---

### 3️⃣ RAG (검색 증강 생성) 데이터 플로우
```
사용자 질문 → 임베딩 벡터 생성 → FAISS 유사도 검색
→ 상위 K개 문서 추출 → LLM 컨텍스트 제공 → 답변 생성
```

**핵심 데이터:**
- 지식 베이스: `rag_dataset.jsonl` (피싱, 큐싱, SSL 인증서 등 보안 개념)
- 인덱스: FAISS 벡터 인덱스 (semantic search)
- 출력: 검색된 문서 기반 정확한 답변

---

### 4️⃣ 세션 및 이력 관리 플로우
```
사용자 접속 → guest_id 생성 (UUID) → 세션 쿠키 저장
→ 로그인 시 user_id 매핑 → 스캔/채팅 이력 DB 저장
→ /history 요청 → user_id 기반 이력 조회 → 반환
```

**핵심 데이터:**
- 세션: Flask Session + 쿠키 (`guest_id` 또는 `user_id`)
- 이력 데이터: URL 스캔 결과, 챗봇 대화 로그, 타임스탬프

---

## 데이터 저장 구조

### MySQL 테이블 스키마 (추정)

#### `url_scans`
```sql
CREATE TABLE url_scans (
    id INT AUTO_INCREMENT PRIMARY KEY,
    user_id VARCHAR(255),
    url TEXT NOT NULL,
    analysis_result VARCHAR(50),  -- 'safe' or 'dangerous'
    confidence FLOAT,
    timestamp DATETIME DEFAULT CURRENT_TIMESTAMP
);
```

#### `chat_logs`
```sql
CREATE TABLE chat_logs (
    id INT AUTO_INCREMENT PRIMARY KEY,
    user_id VARCHAR(255),
    user_message TEXT,
    bot_response TEXT,
    timestamp DATETIME DEFAULT CURRENT_TIMESTAMP
);
```

#### `users`
```sql
CREATE TABLE users (
    id INT AUTO_INCREMENT PRIMARY KEY,
    user_id VARCHAR(255) UNIQUE,
    guest_id VARCHAR(255),
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP
);
```

---

## 데이터 흐름 특징

### ✅ 비동기 처리
- Flask는 동기 방식이지만 `threaded=True`로 멀티스레드 처리
- Langchain Agent는 도구 호출을 순차적으로 처리

### ✅ 세션 관리
- 쿠키 기반 세션 (`flask_auth_session`)
- 비로그인 사용자는 `guest_id`로 임시 식별
- 로그인 사용자는 `user_id`로 영구 추적

### ✅ 데이터 캐싱
- FAISS 인덱스는 메모리에 로드 (빠른 검색)
- URL-BERT 모델은 GPU/CPU 메모리에 상주

### ✅ 에러 처리
- Flask 라우트: `try-except`로 에러 응답 반환
- Langchain Agent: 도구 실행 실패 시 폴백 응답

---

## 외부 의존성

| 서비스 | 용도 | 데이터 흐름 |
|--------|------|------------|
| **MySQL** | 영구 저장소 | Flask ↔ MySQL (읽기/쓰기) |
| **FAISS** | 벡터 검색 | 임베딩 → FAISS 검색 → 문서 반환 |
| **Gemini API** | 확장 기능 (선택) | Langchain → Gemini API |
| **URL-BERT** | URL 위협 분석 | URL → URL-BERT → 분류 결과 |
| **Llama-3-Korean** | LLM 응답 생성 | 컨텍스트 → Llama → 자연어 응답 |

---

## 성능 고려사항

### 병목 구간
1. **URL-BERT 추론**: GPU 가속 필요 (CPU는 느림)
2. **Llama-3-Korean 생성**: 긴 응답 생성 시 지연 발생
3. **FAISS 검색**: 인덱스 크기에 비례하여 검색 시간 증가
4. **MySQL 쓰기**: 대량 로그 저장 시 I/O 병목

### 최적화 전략
- URL-BERT: 배치 추론 지원 (여러 URL 동시 처리)
- Langchain: 스트리밍 응답 지원 (부분 응답 전송)
- FAISS: 인덱스 샤딩 또는 양자화
- MySQL: 커넥션 풀링, 비동기 쓰기

---

## 보안 데이터 흐름

### 민감 데이터 처리
- **세션 ID**: 쿠키에 저장 (HttpOnly, Secure 플래그)
- **사용자 입력**: SQL Injection 방지 (파라미터화된 쿼리)
- **URL 데이터**: 원본 URL 저장 시 개인정보 포함 가능성 검토

### 데이터 암호화
- HTTPS 전송 (권장)
- DB 비밀번호는 환경 변수로 관리

---

**작성일**: 2025-10-27  
**버전**: 1.0  
**프로젝트**: ColScan - QR Code Security Analysis Platform
