from datetime import datetime, timedelta
from airflow import DAG
from airflow.operators.python import PythonOperator
from airflow.providers.redis.hooks.redis import RedisHook
import json

default_args = {
    'owner': 'airflow',
    'depends_on_past': False,
    'email_on_failure': False,
    'email_on_retry': False,
    'retries': 1,
    'retry_delay': timedelta(minutes=5),
}

def push_to_redis(**kwargs):
    hook = RedisHook(redis_conn_id='redis_default')
    client = hook.get_conn()
    
    data = {
        'timestamp': datetime.now().isoformat(),
        'message': 'Hello from Airflow!',
        'status': 'success'
    }
    
    client.set('airflow_test_key', json.dumps(data))
    print(f"Pushed data to Redis: {data}")

def pull_from_redis(**kwargs):
    hook = RedisHook(redis_conn_id='redis_default')
    client = hook.get_conn()
    
    val = client.get('airflow_test_key')
    if val:
        data = json.loads(val)
        print(f"Retrieved data from Redis: {data}")
    else:
        print("No data found in Redis for key 'airflow_test_key'")

with DAG(
    'redis_data_pipeline',
    default_args=default_args,
    description='A simple data pipeline using Redis',
    schedule_interval=timedelta(days=1),
    start_date=datetime(2023, 1, 1),
    catchup=False,
    tags=['example', 'redis'],
) as dag:

    push_task = PythonOperator(
        task_id='push_to_redis',
        python_callable=push_to_redis,
    )

    pull_task = PythonOperator(
        task_id='pull_from_redis',
        python_callable=pull_from_redis,
    )

    push_task >> pull_task
