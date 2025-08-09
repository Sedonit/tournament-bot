# database.py
import psycopg2
import os
from psycopg2.extras import RealDictCursor

# Получаем URL базы данных из переменных окружения
DATABASE_URL = os.environ.get('DATABASE_URL')

# === ВАЖНО: ЭТА ФУНКЦИЯ ДОЛЖНА БЫТЬ ПЕРВОЙ ===
def get_db_connection():
    """Создание подключения к базе данных"""
    return psycopg2.connect(DATABASE_URL, cursor_factory=RealDictCursor)

# === Теперь можно использовать get_db_connection ===

def init_db():
    """Инициализация базы данных - создание таблиц"""
    conn = get_db_connection()
    cur = conn.cursor()
    
    # Создание таблицы для анкет
    cur.execute("""
        CREATE TABLE IF NOT EXISTS applications (
            id SERIAL PRIMARY KEY,
            nickname VARCHAR(100) NOT NULL,
            rank VARCHAR(100) NOT NULL,
            name VARCHAR(100),
            contact VARCHAR(200) NOT NULL,
            team VARCHAR(100),
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)
    
    conn.commit()
    cur.close()
    conn.close()

def save_application(nickname, rank, name, contact, team):
    """Сохранение анкеты в базу данных"""
    conn = get_db_connection()
    cur = conn.cursor()
    
    cur.execute("""
        INSERT INTO applications (nickname, rank, name, contact, team)
        VALUES (%s, %s, %s, %s, %s)
        RETURNING id
    """, (nickname, rank, name, contact, team))
    
    app_id = cur.fetchone()['id']
    conn.commit()
    cur.close()
    conn.close()
    return app_id

def get_stats():
    """Получение статистики"""
    conn = get_db_connection()
    cur = conn.cursor()
    
    # Общее количество анкет
    cur.execute("SELECT COUNT(*) as count FROM applications")
    total = cur.fetchone()['count']
    
    # Количество анкет по командам
    cur.execute("""
        SELECT team, COUNT(*) as count 
        FROM applications 
        WHERE team != 'Нет' AND team IS NOT NULL
        GROUP BY team
        ORDER BY count DESC
    """)
    teams = cur.fetchall()
    
    cur.close()
    conn.close()
    return total, teams

def get_all_applications():
    """Получение всех анкет"""
    conn = get_db_connection()
    cur = conn.cursor()
    
    cur.execute("""
        SELECT id, nickname, rank, name, contact, team, created_at
        FROM applications
        ORDER BY created_at DESC
    """)
    applications = cur.fetchall()
    
    cur.close()
    conn.close()
    return applications

def reset_applications():
    """Очистка всех анкет"""
    conn = get_db_connection()
    cur = conn.cursor()
    
    cur.execute("DELETE FROM applications")
    deleted_count = cur.rowcount
    
    conn.commit()
    cur.close()
    conn.close()
    return deleted_count

def delete_application_by_id(app_id):
    """Удаление анкеты по ID"""
    conn = get_db_connection()
    cur = conn.cursor()
    cur.execute("DELETE FROM applications WHERE id = %s", (app_id,))
    deleted = cur.rowcount
    conn.commit()
    cur.close()
    conn.close()
    return deleted
