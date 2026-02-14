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

지정된 날짜와 섹션별로 네이버 뉴스의 기사를 수집하는 파이프라인입니다.

### 주요 특징
- **효율적인 수집**: 네이버 내부 AJAX API를 사용하여 '더보기' 버튼을 누르지 않고도 전체 기사 목록을 빠르게 가져옵니다.
- **상세 데이터**: 네이버 뉴스 URL, 원본 기사 URL, 제목, 날짜, 언론사, 섹션 정보를 수집합니다.
- **차단 방지**: 맥북 크롬 User-Agent를 사용하며, 요청 사이에 랜덤 지연 시간을 두어 서버 부하를 최소화합니다.
- **중복 방지**: 네이버 URL의 SHA256 해시를 PK로 사용하여 중복 데이터를 저장하지 않습니다.

### 사용 방법 (Usage)

1. **DAG 활성화**: Airflow UI에서 `naver_news_crawler` DAG를 찾아 활성화(Unpause)합니다.
2. **트리거 (Trigger DAG w/ config)**: 우측 상단의 재생 버튼 옆 화살표를 눌러 'Trigger DAG w/ config'를 선택합니다.
3. **날짜 지정**: 수집하고 싶은 날짜를 JSON 형태로 입력합니다.
   ```json
   { "date": "20260214" }
   ```
   - 날짜 형식은 `YYYYMMDD`입니다.
   - 값을 입력하지 않으면 실행 시점의 당일 날짜로 자동 설정됩니다.
4. **결과 확인**: Postgres 데이터베이스의 `naver_news_articles` 테이블을 쿼리하여 결과를 확인합니다.

---

## 디렉토리 구조 (Directory Structure)
- `dags/`: Airflow DAG 정의 파일 (`naver_news_crawler.py` 등)
- `plugins/`: 커스텀 파이썬 모듈 및 유틸리티 (`naver_news_crawler_utils.py`)
- `logs/`: 태스크 실행 로그.
- `postgres_data/`: Postgres 데이터 영구 저장소 (Git 제외).
- `docker-compose.yaml`: 전체 인프라 정의.
