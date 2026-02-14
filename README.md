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
3. 서비스 시작:
   ```bash
   docker-compose up -d
   ```
4. Airflow 웹 UI 접속: [http://localhost:8080](http://localhost:8080)
   - **ID**: `airflow`
   - **PW**: `airflow`

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
    - **Trafilatura**: 효율적인 본문 및 메타데이터(기자명 등) 추출 라이브러리를 사용합니다.
    - **동시성 제어**: `FOR UPDATE SKIP LOCKED`를 사용하여 여러 Worker가 동시에 실행되어도 중복 처리 없이 안전하게 병렬 처리가 가능합니다.
    - **자동 재시도**: 일시적인 오류는 재시도하며, 영구적인 오류는 실패 사유를 기록하고 건너뜁니다.

---

## 디렉토리 구조 (Directory Structure)
- `dags/`: Airflow DAG 정의 파일
    - `naver_news_crawler_scheduled.py`: 정기 수집 DAG
    - `naver_news_crawler_backfill.py`: 과거 데이터 수집 DAG
    - `naver_news_content_collector_dag.py`: 본문 수집 DAG
- `plugins/`: 커스텀 파이썬 모듈 및 유틸리티 (`naver_news_crawler_utils.py` - 공통 크롤링 로직)
- `logs/`: 태스크 실행 로그.
- `postgres_data/`: Postgres 데이터 영구 저장소 (Git 제외).
- `docker-compose.yaml`: 전체 인프라 정의.
