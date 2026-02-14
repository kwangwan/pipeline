# Airflow & Redis 데이터 파이프라인

이 프로젝트는 Apache Airflow와 Redis를 사용하여 구축된 컨테이너화된 데이터 파이프라인 환경입니다.

## 아키텍처 (Architecture)

시스템은 다음과 같은 핵심 컴포넌트로 구성됩니다:
- **Airflow Webserver**: DAG 관리 및 모니터링용 UI.
- **Airflow Scheduler**: DAG 예약 및 태스크 트리거 담당.
- **Airflow Worker**: Celery를 통한 실제 태스크 실행.
- **Redis**: Celery 메시지 브로커 및 transient 데이터 저장소.
- **Postgres**: Airflow 메타데이터 및 수집된 뉴스 데이터 저장.

## 시작하기 (Getting Started)

### 사전 요구 사항
- Docker 및 Docker Compose가 설치되어 있어야 합니다.

### 설정 및 실행
1. 저장소를 클론합니다.
2. 환경 변수 파일 생성:
   ```bash
   echo "AIRFLOW_UID=$(id -u)" > .env
   ```
4. **환경 변수 구성**: `.env.example` 파일을 `.env`로 복사하거나 내용을 추가하여 설정을 구성합니다.
   - `OLLAMA_HOST`: Ollama 서버 주소 (기본값: `http://ollama:11434`)
   - `SUMMARIZATION_MODEL`: 사용할 LLM 모델 (기본값: `gemma3:4b`)
   - `SUMMARIZER_BATCH_SIZE`: 한 번에 요약할 기사 수 (기본값: `3`)
   - `CONTENT_COLLECTOR_BATCH_SIZE`: 한 번에 수집할 본문 수 (기본값: `100`)
   - `CONTENT_COLLECTOR_MAX_ACTIVE_RUNS`: 본문 수집기 동시 실행 수 (기본값: `2`)

5. 서비스 빌드 및 시작 (커스텀 Airflow 이미지 및 **Ollama** 포함):
   - `.env` 파일에 필요한 설정(모델명, 배치 크기 등)을 확인하거나 수정합니다.
   ```bash
   docker compose up -d --build
   ```
6. **Ollama 모델 다운로드 (필수)**:
   ```bash
   docker exec -it pipeline-ollama-1 ollama pull gemma3:4b
   ```
7. Airflow 웹 UI 접속: [http://localhost:8080](http://localhost:8080)
   - **ID**: `airflow`
   - **PW**: `airflow`
8. 뉴스 데이터 대시보드 접속: [http://localhost:3000](http://localhost:3000)
   - 수집된 기사의 요약문과 통계를 확인할 수 있습니다.
   - **시계열 전환**: 데이터 수집 시간(`Created At`) 또는 기사 발행 시간(`Article Date`) 기준으로 차트를 전환하여 볼 수 있습니다.

---

## 네이버 뉴스 크롤러 (Naver News Crawler)

지정된 날짜와 섹션별로 네이버 뉴스의 기사를 수집하는 파이프라인입니다. 두 가지 모드로 운영됩니다.

1. **정기 수집 (Scheduled)**: 매시간 실행되어 **오늘**과 **어제**의 뉴스를 수집합니다.
2. **과거 데이터 수집 (Backfill)**: 사용자가 지정한 기간(Start Date ~ End Date)의 뉴스를 최신순으로 수집합니다.

### 주요 특징
- **효율적인 수집**: 네이버 내부 AJAX API를 사용하여 '더보기' 버튼을 누르지 않고도 전체 기사 목록을 빠르게 가져옵니다.
- **상세 데이터**: 네이버 뉴스 URL, 원본 기사 URL, 제목, 날짜, 언론사, 섹션 정보를 수집합니다.
- **차단 방지**: 맥북 크롬 User-Agent를 사용하며, 요청 사이에 랜덤 지연 시간을 두어 서버 부하를 최소화합니다.
- **중복 방지**: 네이버 URL의 SHA256 해시를 PK로 사용하여 중복 데이터를 저장하지 않습니다.

### 데이터 확인 (Data Verification)

수집된 데이터는 **Prisma Studio**를 통해 손쉽게 확인할 수 있습니다.

1. 웹 브라우저에서 [http://localhost:5555](http://localhost:5555) 접속
2. `naver_news_articles` 모델을 클릭하여 수집된 기사 목록 확인
3. 별도의 로그인 없이 바로 데이터를 조회, 필터링 및 수정 가능

### 사용 방법 (Usage)

#### 1. 정기 수집 (Scheduled)
- **DAG ID**: `naver_news_crawler_scheduled`
- **동작**: 매시간 자동으로 실행됩니다. 별도의 설정이 필요 없습니다.
- **수집 범위**: 실행 시점 기준 KST(한국 표준시) **오늘**과 **어제** 날짜의 기사.

#### 2. 과거 데이터 수집 (Backfill)
- **DAG ID**: `naver_news_crawler_backfill`
- **동작**: 수동으로 트리거하여 특정 기간의 데이터를 수집합니다.
- **실행 방법**:
    1. Airflow UI에서 `naver_news_crawler_backfill` DAG의 재생 버튼 -> **Trigger DAG w/ config** 클릭.
    2. JSON 설정 입력:
       ```json
       {
         "start_date": "20240201",
         "end_date": "20240210"
       }
       ```
    3. **Trigger** 버튼 클릭.
    - `end_date`부터 `start_date`까지 역순으로 날짜를 하루씩 감소시키며 수집합니다.

#### 3. 기사 본문 수집 (Content Collector)
- **DAG ID**: `naver_news_content_collector_dag`
- **동작**: 수집된 기사 목록 중 본문이 없는 기사를 찾아 내용을 수집합니다.
- **주요 특징**:
    - **연속 수집**: 한 번 실행되면 대기 중인(`PENDING`) 모든 기사를 처리할 때까지 멈추지 않고 동작합니다. 더 이상 처리할 기사가 없으면 종료됩니다.
    - **독립적 운영**: 본체 수집과 요약 작업을 분리하여 시스템 안정성을 높였습니다. 본문 수집이 완료되면 데이터베이스 상태에 따라 요약기가 독립적으로 작업을 이어받습니다.
    - **Trafilatura**: 고성능 본문 추출 라이브러리를 사용하여 정확한 내용을 수집합니다.
    - **동시성 제어**: `FOR UPDATE SKIP LOCKED`를 사용하여 중복 처리 없이 안전한 병렬 작업이 가능합니다.

#### 4. 기사 요약 (Article Summarizer)
- **DAG ID**: `naver_news_summarizer_dag`
- **동작**: 본문 수집이 완료된 기사를 대상으로 **Gemma 3** 모델을 사용하여 요약을 생성합니다.
- **주요 특징**:
    - **독립적 스케줄링**: 트리거 방식 대신 독립적인 스케줄에 따라 실행되어, 본문 수집량에 영향을 받지 않고 안정적으로 백로그를 처리합니다.
    - **최신순 우선순위**: 기사 발행일(`article_date`) 기준 최신 기사를 먼저 요약하여 대시보드에 최신 정보를 빠르게 반영합니다.
    - **대량 배치 처리**: 효율적인 처리를 위해 배치 크기를 지정하여 묶어서 처리합니다. (`.env`의 `SUMMARIZER_BATCH_SIZE` 설정 사용)
    - **연속 동작**: 처리해야 할 기사가 남아 있을 경우 루프를 돌며 즉시 요약을 이어나갑니다.
    - **Ollama**: 로컬 LLM 서버인 Ollama를 활용하여 외부 API 키 없이 요약을 수행합니다.
    - **언어 일치**: 원문이 한국어면 한국어 요약, 영어면 영어 요약을 생성합니다.
    - **글자 수 제약**: 최대 2000자 이내로 요약하며, 사용된 모델 정보를 함께 기록합니다.
113: 
114: #### 5. 검색 API 업로드 (Article Uploader)
115: - **DAG ID**: `naver_news_uploader_dag`
116: - **동작**: 요약이 완료된 기사를 외부 **Project RAG** 검색 API로 자동으로 업로드합니다.
117: - **주요 특징**:
118:     - **주기적 실행**: 5분마다 실행되어 요약은 완료되었으나 아직 업로드되지 않은 기사를 처리합니다.
119:     - **메타데이터 포함**: 기사 ID, 제목, 원본 URL, 언론사 정보를 문서 메타데이터로 함께 전송하여 검색 결과의 활용도를 높입니다.
120:     - **상태 동기화**: 업로드 성공 시 API로부터 반환받은 문서 ID(`doc_id`)를 데이터베이스에 기록하여 중복 업로드를 방지합니다.
121:     - **안전한 데이터 전송**: `FOR UPDATE SKIP LOCKED`를 통해 여러 워커가 동시에 작업해도 데이터 충돌 없이 안전하게 전송합니다.

---

## 디렉토리 구조 (Directory Structure)
- `dags/`: Airflow DAG 정의 파일
    - `naver_news_crawler_scheduled.py`: 정기 수집 DAG
    - `naver_news_crawler_backfill.py`: 과거 데이터 수집 DAG
    - `naver_news_content_collector_dag.py`: 본문 수집 DAG
    - `naver_news_summarizer_dag.py`: 기사 요약 DAG
    - `naver_news_uploader_dag.py`: 검색 API 업로드 DAG
- `dashboard-backend/`: 대시보드 백엔드 API (FastAPI)
- `dashboard-frontend/`: 대시보드 프론트엔드 (React + Vite)
- `prisma/`: Prisma ORM 설정 및 데이터베이스 스키마
- `plugins/`: 커스텀 파이썬 모듈 및 유틸리티 (`naver_news_crawler_utils.py`)
- `docker-compose.yaml`: 전체 서비스 인프라 정의 (Ollama 포함)
- `Dockerfile.airflow`: 커스텀 Airflow 이미지 빌드 정의
- `postgres_data/`: Postgres 데이터 영구 저장소
- `ollama_data/`: Ollama 모델 데이터 저장소
- `logs/`: Airflow 태스크 로그
