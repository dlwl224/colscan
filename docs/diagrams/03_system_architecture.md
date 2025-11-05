# ColScan - 시스템 아키텍처 (System Architecture)

## 전체 시스템 구성도

---

## 🏗️ 고수준 아키텍처 다이어그램 (High-Level Architecture)

```mermaid
C4Context
    title ColScan 시스템 아키텍처 - Level 1 (컨텍스트 다이어그램)

    Person(user, "일반 사용자", "QR 코드를 스캔하고<br/>보안 정보를 확인하는 사용자")
    
    System(colscan, "ColScan<br/>보안 분석 플랫폼", "QR 코드 URL 위협 분석<br/>및 AI 챗봇 서비스")
    
    System_Ext(gemini, "Google Gemini API", "확장 AI 기능<br/>(선택적 사용)")
    
    SystemDb(mysql, "MySQL Database", "사용자 데이터, 스캔 이력,<br/>채팅 로그 저장")
    
    Rel(user, colscan, "스캔 요청,<br/>챗봇 대화", "HTTPS")
    Rel(colscan, mysql, "데이터 읽기/쓰기", "TCP/3306")
    Rel(colscan, gemini, "API 호출", "HTTPS")
    
    UpdateLayoutConfig($c4ShapeInRow="3", $c4BoundaryInRow="1")
```

---

## 🎯 컨테이너 다이어그램 (Container Diagram)

```mermaid
graph TB
    subgraph Client["클라이언트 레이어"]
        direction TB
        MobileApp["모바일 앱<br/>────────<br/>React Native<br/>- QR 스캔 UI<br/>- 챗봇 인터페이스<br/>- 이력 관리<br/>────────<br/>JavaScript"]
        
        QRScanner["QR 스캐너<br/>────────<br/>React Native Camera<br/>- 실시간 QR 감지<br/>- URL 추출<br/>────────<br/>Native Module"]
    end
    
    subgraph BackendLayer["백엔드 레이어"]
        direction TB
        
        FlaskAPI["Flask REST API<br/>────────<br/>- 라우팅 및 세션 관리<br/>- CORS 처리<br/>- 요청 검증<br/>────────<br/>Python 3.10+<br/>Flask 2.x"]
        
        subgraph Services["서비스 모듈"]
            direction LR
            ScanService["스캔 서비스<br/>────────<br/>scan.py<br/>analyze.py"]
            
            ChatService["챗봇 서비스<br/>────────<br/>chatbot.py<br/>bot_main.py"]
            
            AuthService["인증 서비스<br/>────────<br/>auth.py<br/>세션 관리"]
        end
    end
    
    subgraph AILayer["AI 레이어"]
        direction TB
        
        URLBERTEngine["URL-BERT 엔진<br/>────────<br/>- 파인튜닝 모델 로드<br/>- URL 토큰화<br/>- 위협 분류<br/>────────<br/>PyTorch<br/>Transformers"]
        
        LangchainAgent["Langchain Agent<br/>────────<br/>- ReAct 패턴<br/>- 도구 선택 및 실행<br/>- 메모리 관리<br/>────────<br/>Langchain"]
        
        LlamaLLM["Llama-3-Korean<br/>────────<br/>- GGUF 양자화 모델<br/>- 한국어 생성<br/>- GPU 가속<br/>────────<br/>LlamaCpp<br/>8B 파라미터"]
        
        RAGEngine["RAG 엔진<br/>────────<br/>- FAISS 벡터 검색<br/>- 임베딩 생성<br/>- 문서 검색<br/>────────<br/>FAISS<br/>Sentence-Transformers"]
    end
    
    subgraph DataLayer["데이터 레이어"]
        direction TB
        
        MySQL[("MySQL<br/>────────<br/>관계형 DB<br/>- users<br/>- scan_history<br/>- chat_logs<br/>────────<br/>MySQL 8.0")]
        
        FAISSIndex[("FAISS Index<br/>────────<br/>벡터 DB<br/>- security_faiss_index<br/>- 임베딩 벡터<br/>────────<br/>IndexFlatL2")]
        
        ModelStorage[("모델 스토리지<br/>────────<br/>파일 시스템<br/>- URL-BERT (.pth)<br/>- Llama-3 (.gguf)<br/>────────<br/>로컬 디스크")]
    end
    
    subgraph ExternalAPI["외부 서비스"]
        GeminiAPI["Google Gemini API<br/>────────<br/>- 확장 AI 기능<br/>- 멀티모달 처리<br/>────────<br/>REST API"]
    end
    
    %% 클라이언트 → 백엔드
    MobileApp -->|"HTTP/HTTPS<br/>JSON API"| FlaskAPI
    QRScanner -.->|"QR 데이터"| MobileApp
    
    %% 백엔드 → 서비스
    FlaskAPI --> ScanService
    FlaskAPI --> ChatService
    FlaskAPI --> AuthService
    
    %% 서비스 → AI
    ScanService -->|"URL 분석 요청"| URLBERTEngine
    ChatService -->|"질문 처리"| LangchainAgent
    
    %% AI 레이어 내부
    LangchainAgent --> LlamaLLM
    LangchainAgent --> URLBERTEngine
    LangchainAgent --> RAGEngine
    
    %% AI → 데이터
    URLBERTEngine -.->|"모델 로드"| ModelStorage
    LlamaLLM -.->|"모델 로드"| ModelStorage
    RAGEngine -->|"벡터 검색"| FAISSIndex
    
    %% 백엔드 → 데이터
    FlaskAPI -->|"CRUD 작업"| MySQL
    AuthService -->|"세션 저장"| MySQL
    
    %% 외부 API
    LangchainAgent -.->|"선택적 호출"| GeminiAPI
    
    %% 스타일링
    classDef client fill:#e1f5ff,stroke:#01579b,stroke-width:3px
    classDef backend fill:#fff3e0,stroke:#e65100,stroke-width:3px
    classDef ai fill:#f3e5f5,stroke:#4a148c,stroke-width:3px
    classDef data fill:#e8f5e9,stroke:#1b5e20,stroke-width:3px
    classDef external fill:#fce4ec,stroke:#880e4f,stroke-width:2px
    
    class MobileApp,QRScanner client
    class FlaskAPI,ScanService,ChatService,AuthService backend
    class URLBERTEngine,LangchainAgent,LlamaLLM,RAGEngine ai
    class MySQL,FAISSIndex,ModelStorage data
    class GeminiAPI external
```

---

## 🔧 컴포넌트 다이어그램 (Component Diagram)

```mermaid
graph TB
    subgraph FlaskApp["Flask Application (app.py)"]
        direction TB
        
        AppCore["Flask Core<br/>────────<br/>- 앱 초기화<br/>- 미들웨어 설정<br/>- CORS 구성"]
        
        SessionMgr["세션 관리자<br/>────────<br/>- guest_id 생성<br/>- 쿠키 관리<br/>- 세션 검증"]
        
        subgraph Blueprints["Blueprint 모듈"]
            direction LR
            HomeBP["home_bp<br/>홈 화면"]
            ScanBP["scan_bp<br/>스캔/분석"]
            ChatBP["chatbot_bp<br/>챗봇"]
            HistoryBP["history_bp<br/>이력"]
            AuthBP["auth_bp<br/>인증"]
            BoardBP["board_bp<br/>게시판"]
            SettingsBP["settings_bp<br/>설정"]
        end
        
        DBConn["DB 커넥터<br/>────────<br/>DB_conn.py<br/>db_manager.py"]
    end
    
    subgraph URLBERTModule["URL-BERT 모듈"]
        direction TB
        
        ModelLoader["모델 로더<br/>────────<br/>model_loader.py<br/>- 모델 초기화<br/>- 가중치 로드"]
        
        Tokenizer["URL 토크나이저<br/>────────<br/>tokenize.py<br/>- URL 파싱<br/>- vocab 매핑"]
        
        Inference["추론 엔진<br/>────────<br/>- 임베딩 생성<br/>- 분류 실행"]
        
        FinetuneModel["파인튜닝 모델<br/>────────<br/>modelx_URLBERT_80.pth<br/>- 피싱 탐지 특화"]
    end
    
    subgraph BotModule["챗봇 모듈"]
        direction TB
        
        AgentSetup["에이전트 설정<br/>────────<br/>agent_setup.py<br/>bot_main.py"]
        
        subgraph Tools["Langchain Tools"]
            URLTool["URLBERT Tool<br/>────────<br/>urlbert_tool.py"]
            RAGTool["RAG Tool<br/>────────<br/>rag_tools.py"]
            ChatTool["Chat Tool<br/>────────<br/>일반 대화"]
        end
        
        Memory["대화 메모리<br/>────────<br/>ConversationBufferMemory"]
        
        LLMInterface["LLM 인터페이스<br/>────────<br/>LlamaCpp 래퍼"]
    end
    
    subgraph RAGModule["RAG 모듈"]
        direction TB
        
        IndexBuilder["인덱스 빌더<br/>────────<br/>build_rag_index_from_jsonl<br/>- JSONL 파싱<br/>- 임베딩 생성"]
        
        VectorStore["벡터 스토어<br/>────────<br/>FAISS Index<br/>- 문서 저장<br/>- 유사도 검색"]
        
        EmbedModel["임베딩 모델<br/>────────<br/>Sentence-Transformers<br/>- 한국어 지원"]
        
        RAGData["지식 베이스<br/>────────<br/>rag_dataset.jsonl<br/>- 피싱<br/>- 큐싱<br/>- SSL 등"]
    end
    
    %% Flask 내부 연결
    AppCore --> SessionMgr
    AppCore --> Blueprints
    Blueprints --> DBConn
    
    %% Flask → URL-BERT
    ScanBP -->|"URL 분석 요청"| ModelLoader
    ModelLoader --> Tokenizer
    Tokenizer --> Inference
    Inference -.->|"모델 사용"| FinetuneModel
    
    %% Flask → 챗봇
    ChatBP -->|"질문 처리"| AgentSetup
    AgentSetup --> Tools
    AgentSetup --> Memory
    AgentSetup --> LLMInterface
    
    %% 챗봇 → URL-BERT
    URLTool -->|"URL 분석"| ModelLoader
    
    %% 챗봇 → RAG
    RAGTool --> VectorStore
    VectorStore -.->|"사용"| EmbedModel
    
    %% RAG 빌드
    RAGData -->|"빌드 시"| IndexBuilder
    IndexBuilder --> VectorStore
    
    %% 스타일링
    classDef flask fill:#fff3e0,stroke:#e65100,stroke-width:2px
    classDef urlbert fill:#e3f2fd,stroke:#0277bd,stroke-width:2px
    classDef bot fill:#f3e5f5,stroke:#6a1b9a,stroke-width:2px
    classDef rag fill:#e8f5e9,stroke:#2e7d32,stroke-width:2px
    
    class AppCore,SessionMgr,HomeBP,ScanBP,ChatBP,HistoryBP,AuthBP,BoardBP,SettingsBP,DBConn flask
    class ModelLoader,Tokenizer,Inference,FinetuneModel urlbert
    class AgentSetup,URLTool,RAGTool,ChatTool,Memory,LLMInterface bot
    class IndexBuilder,VectorStore,EmbedModel,RAGData rag
```

---

## 📦 배포 다이어그램 (Deployment Diagram)

```mermaid
graph TB
    subgraph UserDevice["사용자 디바이스"]
        direction TB
        MobileApp["React Native App<br/>────────<br/>iOS/Android<br/>포트: N/A"]
    end
    
    subgraph ServerInfra["서버 인프라"]
        direction TB
        
        subgraph WebServer["웹 서버 (단일 서버 구성)"]
            FlaskProc["Flask Application<br/>────────<br/>Python 3.10+<br/>포트: 5000<br/>────────<br/>프로세스:<br/>- app.py (메인)<br/>- threaded=True"]
            
            WSGIServer["WSGI Server<br/>────────<br/>Gunicorn (프로덕션)<br/>또는<br/>Flask Dev Server<br/>────────<br/>워커: 4개"]
        end
        
        subgraph AIRuntime["AI 런타임 환경"]
            direction LR
            
            PyTorch["PyTorch<br/>────────<br/>GPU: CUDA 11.8+<br/>CPU: Fallback<br/>────────<br/>메모리: 4GB+"]
            
            LlamaCpp["LlamaCpp<br/>────────<br/>GGUF 모델 로드<br/>n_gpu_layers=-1<br/>────────<br/>메모리: 8GB+"]
            
            FAISS["FAISS<br/>────────<br/>벡터 검색<br/>IndexFlatL2<br/>────────<br/>메모리: 1GB+"]
        end
        
        subgraph Storage["스토리지"]
            FileSystem["파일 시스템<br/>────────<br/>- 모델 파일<br/>- FAISS 인덱스<br/>- 로그<br/>────────<br/>SSD 권장"]
        end
    end
    
    subgraph DatabaseServer["데이터베이스 서버"]
        MySQLDB["MySQL 8.0<br/>────────<br/>포트: 3306<br/>────────<br/>스토리지:<br/>- InnoDB 엔진<br/>- UTF-8 인코딩"]
    end
    
    subgraph ExternalServices["외부 서비스"]
        Gemini["Google Gemini API<br/>────────<br/>HTTPS<br/>API Key 인증"]
    end
    
    subgraph NetworkLayer["네트워크 레이어"]
        LoadBalancer["로드 밸런서<br/>────────<br/>Nginx (선택)<br/>────────<br/>HTTPS 종단<br/>포트: 443"]
        
        Firewall["방화벽<br/>────────<br/>- 포트 5000 허용<br/>- 포트 3306 제한<br/>- HTTPS 강제"]
    end
    
    %% 연결
    MobileApp -->|"HTTPS<br/>REST API"| LoadBalancer
    LoadBalancer -->|"HTTP"| WSGIServer
    WSGIServer --> FlaskProc
    
    FlaskProc --> PyTorch
    FlaskProc --> LlamaCpp
    FlaskProc --> FAISS
    
    PyTorch -.->|"모델 파일 읽기"| FileSystem
    LlamaCpp -.->|"GGUF 파일 읽기"| FileSystem
    FAISS -.->|"인덱스 파일 읽기"| FileSystem
    
    FlaskProc -->|"TCP/3306<br/>MySQL 프로토콜"| MySQLDB
    
    FlaskProc -.->|"HTTPS<br/>API 호출"| Gemini
    
    Firewall -.->|"보안 정책"| LoadBalancer
    Firewall -.->|"내부 네트워크"| MySQLDB
    
    %% 스타일링
    classDef device fill:#e1f5ff,stroke:#01579b,stroke-width:2px
    classDef server fill:#fff3e0,stroke:#e65100,stroke-width:2px
    classDef ai fill:#f3e5f5,stroke:#6a1b9a,stroke-width:2px
    classDef db fill:#e8f5e9,stroke:#1b5e20,stroke-width:2px
    classDef external fill:#fce4ec,stroke:#880e4f,stroke-width:2px
    classDef network fill:#e0f7fa,stroke:#006064,stroke-width:2px
    
    class MobileApp device
    class FlaskProc,WSGIServer server
    class PyTorch,LlamaCpp,FAISS ai
    class MySQLDB,FileSystem db
    class Gemini external
    class LoadBalancer,Firewall network
```

---

## 🔐 보안 아키텍처

```mermaid
graph TB
    subgraph SecurityLayers["보안 계층"]
        direction TB
        
        subgraph AppSecurity["애플리케이션 보안"]
            CORS["CORS 정책<br/>────────<br/>- 허용 Origin 제한<br/>- Credentials 지원"]
            
            SessionSec["세션 보안<br/>────────<br/>- HttpOnly 쿠키<br/>- SameSite=Lax<br/>- 30일 만료"]
            
            InputValid["입력 검증<br/>────────<br/>- URL 형식 검증<br/>- SQL Injection 방지<br/>- XSS 방지"]
        end
        
        subgraph NetworkSec["네트워크 보안"]
            HTTPS["HTTPS/TLS<br/>────────<br/>- TLS 1.3<br/>- 인증서 갱신"]
            
            RateLimit["Rate Limiting<br/>────────<br/>- IP별 제한<br/>- API 엔드포인트별"]
        end
        
        subgraph DataSec["데이터 보안"]
            Encryption["저장 암호화<br/>────────<br/>- DB 암호화<br/>- 환경 변수 관리"]
            
            AccessControl["접근 제어<br/>────────<br/>- 세션 검증<br/>- 권한 확인"]
        end
        
        subgraph AISec["AI 모델 보안"]
            ModelIntegrity["모델 무결성<br/>────────<br/>- 체크섬 검증<br/>- 서명 확인"]
            
            PromptSafety["프롬프트 안전성<br/>────────<br/>- Injection 방지<br/>- 출력 필터링"]
        end
    end
    
    %% 연결
    HTTPS --> SessionSec
    SessionSec --> AccessControl
    InputValid --> AccessControl
    CORS --> RateLimit
    Encryption --> AccessControl
    ModelIntegrity --> PromptSafety
    
    %% 스타일링
    classDef security fill:#ffebee,stroke:#c62828,stroke-width:2px
    
    class CORS,SessionSec,InputValid,HTTPS,RateLimit,Encryption,AccessControl,ModelIntegrity,PromptSafety security
```

---

## 📊 기술 스택 상세

### 프론트엔드 (클라이언트)
| 기술 | 버전 | 역할 |
|------|------|------|
| **React Native** | 0.70+ | 크로스 플랫폼 모바일 앱 프레임워크 |
| **JavaScript** | ES2020+ | 프로그래밍 언어 |
| **React Native Camera** | - | QR 코드 스캔 및 카메라 제어 |
| **Axios** | 1.x | HTTP 클라이언트 |

---

### 백엔드 (서버)
| 기술 | 버전 | 역할 |
|------|------|------|
| **Flask** | 2.3+ | 웹 프레임워크 |
| **Python** | 3.10+ | 프로그래밍 언어 |
| **Flask-CORS** | 4.x | Cross-Origin 요청 처리 |
| **Gunicorn** | 20.x | WSGI 서버 (프로덕션) |
| **MySQL Connector** | 8.x | MySQL 클라이언트 |

---

### AI/ML 레이어
| 기술 | 버전 | 역할 |
|------|------|------|
| **PyTorch** | 2.0+ | 딥러닝 프레임워크 |
| **Transformers** | 4.30+ | URL-BERT 모델 인터페이스 |
| **Langchain** | 0.1+ | LLM 오케스트레이션 |
| **LlamaCpp** | - | GGUF 모델 추론 엔진 |
| **FAISS** | 1.7+ | 벡터 유사도 검색 |
| **Sentence-Transformers** | 2.2+ | 임베딩 생성 |

---

### 데이터베이스
| 기술 | 버전 | 역할 |
|------|------|------|
| **MySQL** | 8.0+ | 관계형 데이터베이스 |
| **InnoDB** | - | 스토리지 엔진 |

---

### 외부 API
| 서비스 | 용도 |
|--------|------|
| **Google Gemini API** | 확장 AI 기능 (선택적) |

---

## 🚀 성능 특성

### 시스템 요구사항

#### 서버 최소 사양
```yaml
CPU: 4 Core (8 Thread 권장)
RAM: 16GB (AI 모델 로드 시)
GPU: NVIDIA RTX 3060 이상 (선택, 추론 속도 5-10배 향상)
Storage: 50GB SSD
Network: 100Mbps
```

#### 모델 메모리 사용량
```yaml
URL-BERT (PyTorch):    ~500MB
Llama-3-Korean (GGUF): ~5GB (Q4 양자화)
FAISS Index:           ~200MB (10만 문서 기준)
Flask 프로세스:         ~200MB
총계:                  ~6GB
```

---

### 처리 성능 (단일 서버)

| 작업 | 평균 응답 시간 | 처리량 (TPS) |
|------|---------------|-------------|
| **URL 분석** | 1-2초 | 10-20 req/s |
| **챗봇 응답** | 3-8초 | 2-5 req/s |
| **이력 조회** | 0.1-0.5초 | 50-100 req/s |
| **RAG 검색** | 0.5-1초 | 20-30 req/s |

---

## 🔄 확장성 전략

### 수평 확장 (Horizontal Scaling)
```mermaid
graph LR
    LB["로드 밸런서<br/>Nginx"] --> Server1["Flask 서버 1"]
    LB --> Server2["Flask 서버 2"]
    LB --> Server3["Flask 서버 3"]
    
    Server1 --> SharedDB[("공유 MySQL")]
    Server2 --> SharedDB
    Server3 --> SharedDB
    
    Server1 -.->|"모델 복제"| LocalModel1["로컬 모델"]
    Server2 -.->|"모델 복제"| LocalModel2["로컬 모델"]
    Server3 -.->|"모델 복제"| LocalModel3["로컬 모델"]
    
    classDef lb fill:#fce4ec,stroke:#880e4f,stroke-width:2px
    classDef server fill:#fff3e0,stroke:#e65100,stroke-width:2px
    classDef db fill:#e8f5e9,stroke:#1b5e20,stroke-width:2px
    
    class LB lb
    class Server1,Server2,Server3 server
    class SharedDB db
```

**장점:**
- 트래픽 분산
- 고가용성 (HA)
- 무중단 배포

**과제:**
- 모델 파일 동기화 (각 서버 5GB+)
- 세션 공유 (Redis 사용 권장)

---

### 마이크로서비스 분리 (향후 개선)
```mermaid
graph TB
    Gateway["API Gateway"] --> ScanService["URL 분석 서비스"]
    Gateway --> ChatService["챗봇 서비스"]
    Gateway --> AuthService["인증 서비스"]
    
    ScanService --> URLBERTModel["URL-BERT 전용 서버"]
    ChatService --> LlamaModel["Llama 전용 서버"]
    ChatService --> RAGService["RAG 검색 서비스"]
    
    classDef gateway fill:#fce4ec,stroke:#880e4f,stroke-width:2px
    classDef service fill:#fff3e0,stroke:#e65100,stroke-width:2px
    classDef model fill:#f3e5f5,stroke:#6a1b9a,stroke-width:2px
    
    class Gateway gateway
    class ScanService,ChatService,AuthService,RAGService service
    class URLBERTModel,LlamaModel model
```

---

## 📈 모니터링 및 로깅

### 로깅 아키텍처
```mermaid
graph LR
    FlaskApp["Flask 앱"] -->|"로그 출력"| FileLog["파일 로그<br/>app.log"]
    FlaskApp -->|"에러"| ErrorLog["에러 로그<br/>error.log"]
    FlaskApp -->|"SQL"| QueryLog["쿼리 로그<br/>query.log"]
    
    FileLog --> LogAggregator["로그 수집기<br/>(Fluentd)"]
    ErrorLog --> LogAggregator
    QueryLog --> LogAggregator
    
    LogAggregator --> LogStorage["로그 저장소<br/>(Elasticsearch)"]
    
    LogStorage --> Kibana["시각화<br/>(Kibana)"]
    
    classDef app fill:#fff3e0,stroke:#e65100,stroke-width:2px
    classDef log fill:#e8f5e9,stroke:#1b5e20,stroke-width:2px
    classDef tool fill:#e1f5ff,stroke:#01579b,stroke-width:2px
    
    class FlaskApp app
    class FileLog,ErrorLog,QueryLog,LogStorage log
    class LogAggregator,Kibana tool
```

---

## 🛡️ 재해 복구 (Disaster Recovery)

### 백업 전략
```yaml
데이터베이스:
  - 일일 전체 백업 (3:00 AM)
  - 시간별 증분 백업
  - 보관 기간: 30일

모델 파일:
  - 버전 관리 (Git LFS)
  - S3/클라우드 스토리지 백업

FAISS 인덱스:
  - 주간 백업
  - 재생성 가능 (JSONL 기반)
```

---

**작성일**: 2025-10-27  
**버전**: 1.0  
**프로젝트**: ColScan - QR Code Security Analysis Platform
