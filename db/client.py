import os
import psycopg2
from dotenv import load_dotenv

load_dotenv()


def get_connection():
    return psycopg2.connect(
        host=os.getenv('DB_HOST', 'localhost'),
        port=os.getenv('DB_PORT', '5432'),
        dbname=os.getenv('DB_NAME', 'eventradar_dev'),
        user=os.getenv('DB_USER', 'eventradar'),
        password=os.getenv('DB_PASSWORD', 'eventradar_dev_pass'),
    )
