# 시스템 아키텍처 (System Architecture)

이 문서는 Airflow 및 Redis 기반 데이터 파이프라인의 고수준 아키텍처를 설명합니다.

## 개요 (Overview)

이 시스템은 컨테이너화된 환경에서 Apache Airflow를 사용하여 데이터 수집 및 처리 워크플로우를 관리합니다. 최근에 고도화된 **네이버 뉴스 크롤러**는 이 인프라를 활용하여 대규모 뉴스 데이터를 수집하고 PostgreSQL에 저장합니다. 크롤러는 **정기 수집(Scheduled)**과 **과거 데이터 수집(Backfill)** 두 가지 모드로 운영됩니다.

```mermaid
graph TD
    User([사용자]) --> Webserver[Airflow Webserver]
    Webserver --> DB[(Postgres 메타데이터 DB)]
    Scheduler[Airflow Scheduler] --> DB
    Scheduler --> RedisBroker{Redis 메시지 브로커}
    RedisBroker --> Worker[Airflow Worker]
    Worker --> RedisStore[(Redis 데이터 저장소)]
    Worker --> NewsDB[(Postgres 기사 저장소)]
    Worker --> NaverNews[네이버 뉴스 API/웹]
    Worker --> Ollama[Local Ollama (Host)]
    Worker --> SearchAPI[Project RAG Search API]
    
    DashboardFE[Dashboard Frontend] --> DashboardBE[Dashboard Backend]
    DashboardBE --> NewsDB
```

## 주요 구성 요소 (Components)

### 1. 워크플로우 관리 (Apache Airflow)
- **Webserver**: DAG 모니터링 및 관리를 위한 GUI를 제공합니다.
- **Scheduler**: DAG를 모니터링하고 실행 조건이 충족된 태스크를 트리거합니다.
- **Worker**: 태스크를 실제로 실행합니다. **CeleryExecutor**를 사용하여 워커를 수평적으로 확장할 수 있습니다. 
    - **커스텀 이미지**: 효율적인 본문 추출을 위해 `trafilatura` 및 관련 시스템 라이브러리(`libxml2`, `libxslt`, `zlib`)가 포함된 커스텀 `Dockerfile.airflow`를 사용합니다. 태스크 실행 시 별도의 패키지 설치 없이 즉시 동작합니다.
- **DAGs**:
    - `naver_news_crawler_scheduled`: 매시간 실행되어 오늘/어제 뉴스를 수집합니다.
    - `naver_news_crawler_backfill`: 사용자가 요청한 기간의 뉴스를 역순으로 수집합니다.
    - `naver_news_content_collector_dag`: 본문이 없는 기사의 내용을 채우는 수집기입니다. (`.env`의 `CONTENT_COLLECTOR_BATCH_SIZE` 및 `MAX_ACTIVE_RUNS` 설정 사용)
    - `naver_news_summarizer_dag`: 본문 수집이 완료된 기사를 **Ollama(Gemma 3)**를 통해 요약합니다. (독립적 스케줄, 대량 배치, 최신순 처리 지원)
    - `naver_news_uploader_dag`: 요약된 기사를 외부 검색 API로 업로드하고 수신된 `doc_id`를 기록합니다. (5분 주기 실행)
- **Plugins**: `naver_news_crawler_utils.py`에 공통 크롤링 로직이 캡슐화되어 있어 유지보수성을 높였습니다.
- **Prisma Studio**: Docker 컨테이너로 실행되는 모던한 데이터베이스 GUI입니다. 별도의 인증 없이 로컬 환경에서 수집된 뉴스 데이터를 직관적으로 탐색하고 관리할 수 있습니다. (Port 5555)

### 2. 메시징 및 transient 저장소 (Redis)
- **Broker**: Celery의 메시지 브로커로 고용되어 스케줄러가 보낸 태스크를 워커로 전달합니다.
- **Data Store**: 일시적인 데이터 캐싱이나 파이프라인 단계 간 데이터 전달에 사용됩니다.

### 3. 메타데이터 및 서비스 데이터베이스 (Postgres)
- Airflow의 실행 상태(DAG, Run, Task 등)를 저장합니다.
- **네이버 뉴스 크롤러 데이터**: 수집된 기사 URL, 제목, 언론사 등의 정보가 동일한 Postgres 인스턴스의 `naver_news_articles` 테이블에 저장되어 영구적으로 보존됩니다.
- **영속성**: 로컬 디렉토리 `./postgres_data`와 연결(Bind Mount)되어 컨테이너가 삭제되어도 데이터가 유지됩니다.

### 4. 로컬 LLM 서버 (Ollama)
- **Ollama**: 호스트 머신의 로컬 Ollama 서버를 사용하여 기사 요약을 수행합니다. Docker 컨테이너의 리소스 제약을 피하기 위해 호스트의 자원(GPU/CPU)을 직접 활용합니다. `gemma3:4b` 모델을 사용합니다.

### 5. 데이터 시각화 (Dashboard)
- **Dashboard Backend**: FastAPI 기반의 REST API 서버입니다. Postgres에서 뉴스 수집 통계를 조회하고, **실패한 수집 건(상태가 FAILED이거나 실패 사유가 존재하는 건)을 초기화(Reset to PENDING & Clear fail_reason)**하는 기능을 제공합니다. (Port 8000)
- **Dashboard Frontend**: React + Vite 기반의 웹 애플리케이션입니다. Chart.js를 사용하여 수집 트렌드, 언론사별/섹션별 통계를 시각화하며, **브라우저 시간대 자동 동기화**, **로컬 날짜 기준 필터링**, **섹션 ID-이름 매핑**, **최근 30일 기본 필터링**, **처리 단계별 프로그레스 바**, **시계열 기준(수집일 vs 발행일) 전환** 기능과 실패한 기사를 일괄 재시도할 수 있는 리셋 버튼을 제공합니다. (Port 3000)

## 데이터 흐름 (Data Flow)

1. **트리거**:
    - **Scheduled**: 스케줄러가 매시간 자동으로 트리거합니다.
    - **Backfill**: 사용자가 Airflow UI에서 JSON 설정(`start_date`, `end_date`)과 함께 수동으로 트리거합니다.
2. **뉴스 목록 수집**: 워커는 `plugins`의 공통 로직을 사용하여 네이버 뉴스의 AJAX API를 호출합니다. 지정된 날짜/섹션의 기사 목록을 가져옵니다.
    - 이때 차단 방지를 위해 맥북 크롬 헤더와 랜덤 지연 시간을 적용합니다.
3. **상세 정보 추출**: 목록의 각 기사 URL을 방문하여 원본 기사 링크, 발행 시간, 언론사 이름을 추출합니다.
4. **저장**: 중복 확인(SHA256 해시 PK) 후 Postgres DB에 기사 정보를 저장합니다.
5. **본문 수집 (비동기)**:
    - 별도의 `content_collector` DAG가 주기적으로 실행됩니다.
    - **Locking**: `FOR UPDATE SKIP LOCKED` 쿼리로 처리되지 않은 기사들을 안전하게 가져옵니다.
    - **Trafilatura**: 기사 URL에 접속하여 본문과 부가 정보를 추출합니다.
    - **Update**: 추출된 본문을 원본 레코드에 업데이트하고 상태를 `COMPLETED`로 변경합니다.
7. **기사 요약 (비동기 & 독립 운영)**:
    - **스케줄 기반 실행**: 트리거 대신 독립적인 스케줄에 따라 실행되어 안정적으로 백로그를 소화합니다.
    - **최신순 우선순위**: `ORDER BY article_date DESC`를 통해 가장 최근 기사부터 요약을 생성합니다.
    - **대량 배치**: 효율적인 처리를 위해 배치 크기를 지정하여 묶어서 작업을 수행합니다. (`.env`의 `SUMMARIZER_BATCH_SIZE` 설정 사용)
    - **연속 수행**: 처리 대기 중인 모든 기사를 마칠 때까지 루프를 돌며 즉시 요약을 이어나갑니다.
    - **Ollama API**: 워커는 호스트 머신의 Ollama 서버(`host.docker.internal`)에 본문을 전달하여 요약문을 생성합니다.
    - **저장**: 생성된 요약문과 모델 정보를 `summary`, `summary_model` 컬럼에 업데이트합니다.
8. **검색 API 업로드 (비동기)**:
    - `naver_news_uploader_dag`가 주기적으로 실행됩니다.
    - 요약이 존재하고 `doc_id`가 없는 레코드를 선별하여 외부 **Project RAG** API에 `POST /documents` 요청을 보냅니다.
    - 업로드 성공 시 반환된 `docId`를 데이터베이스의 `doc_id` 컬럼에 업데이트하여 처리를 완료합니다.
    - **시간대 보정**: 검색 API 전송 시 KST 기준의 `article_date`를 **UTC로 변환**하여 저장합니다. 이를 통해 글로벌 서비스 환경에서 정확한 시점을 보장합니다.
8. **데이터 시각화 및 모니터링**:
    - **실시간 진행률**: `collected`(수집 완료), `summarized`(요약 완료), `uploaded`(업로드 완료) 상태를 기반으로 전체 파이프라인의 진행 상황을 백엔드에서 계산하여 대시보드에 프로그레스 바로 표시합니다.
    - **지능형 시간대 처리**: 
        - 데이터베이스의 `created_at`(UTC)과 `article_date`(KST)를 브라우저에서 감지된 사용자의 로컬 시간대로 실시간 변환(`AT TIME ZONE`)하여 일관된 뷰를 제공합니다.
        - 시작일/종료일 필터링 또한 사용자의 로컬 날짜 경계를 준수하여 정확한 통계를 보장합니다.
    - **최근 30일 데이터**: 대시보드 진입 시 최근 30일간의 데이터를 기본으로 노출하여 효율적인 모니터링을 지원합니다.
    - **날짜 파싱 강화**: 다양한 한국어 날짜 형식을 지원하며, 파싱 실패 시 수집 대상 날짜(`target_date`)를 폴백으로 사용합니다.
    - **대시보드 안정성**: 백엔드 필터링과 프론트엔드 안전 장치를 통해 잘못된 날짜 데이터가 차트 시각화를 방해하지 않도록 보호합니다.
9. **상태 동기화**: 모든 태스크 실행 결과는 Postgres의 Airflow 메타데이터 영역에 기록됩니다.

## 환경 고려 사항 (Environmental Considerations)

### macOS & RAID 볼륨 주의사항
- **Stale File Handles**: macOS에서 RAID 볼륨을 사용할 때, 볼륨의 마운트 상태가 변하면 터미널이 `stat .: no such file or directory` 에러를 뱉으며 현재 디렉토리를 잃어버릴 수 있습니다. 이 경우 `cd` 명령어로 명시적으로 다시 진입하여 셸 세션을 갱신해야 합니다.

### 포트 할당 전략 (Port Allocation)
- **Ollama (Conflict Avoidance)**: 로컬 머신에 이미 Ollama가 설치되어 동작 중인 경우 기본 포트(`11434`)가 충돌합니다. 이 프로젝트의 Docker 환경은 이를 피하기 위해 호스트 포트를 **`11435`**로 우회하여 할당합니다.
    - 호스트 접근: `http://localhost:11435`
    - 컨테이너 내부 통신: `http://ollama:11434`
