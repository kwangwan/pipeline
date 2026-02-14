# Airflow & Redis Data Pipeline

This project sets up a containerized data pipeline environment using Apache Airflow and Redis.

## Architecture

The system consists of the following components:
- **Airflow Webserver**: The UI for monitoring and managing DAGs.
- **Airflow Scheduler**: Handles the scheduling and triggering of DAGs.
- **Airflow Worker**: Executes the tasks in the DAGs using Celery.
- **Redis**: Acts as the message broker for Celery and also as a data store for pipelines.
- **Postgres**: The metadata database for Airflow.

## Getting Started

### Prerequisites
- Docker and Docker Compose installed.

### Setup
1. Clone the repository (if not already done).
2. Create an environment file:
   ```bash
   echo "AIRFLOW_UID=$(id -u)" > .env
   ```
3. Initialize the services:
   ```bash
   docker-compose up -d
   ```
4. Access the Airflow Web UI at [http://localhost:8080](http://localhost:8080).
   - **Username**: `airflow`
   - **Password**: `airflow`

## Example Pipeline

The `redis_data_pipeline` DAG demonstrates how to:
1. Connect to Redis using `RedisHook`.
2. Push processed data to a Redis key.
3. Pull and verify data from Redis.

## Directory Structure
- `dags/`: Contains the Airflow DAG definitions.
- `logs/`: Airflow execution logs.
- `plugins/`: Custom Airflow plugins.
- `postgres_data/`: Persistent storage for the PostgreSQL database (excluded from Git).
- `docker-compose.yaml`: Infrastructure definition.
