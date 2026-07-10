# database.py
# =========================================
# 灵山胜境AI导游 - 游客行为数据库模块（SQLite）
# =========================================

import sqlite3
import os
import datetime
import pandas as pd

# =========================
# 1. 数据库路径
# =========================

DB_PATH = "tourist_data.db"


# =========================
# 2. 初始化数据库
# =========================

def init_db():
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()

    cursor.execute("""
    CREATE TABLE IF NOT EXISTS chat_logs (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        time TEXT,
        user_input TEXT,
        bot_response TEXT,
        emotion TEXT,
        interest TEXT
    )
    """)

    cursor.execute("""
    CREATE TABLE IF NOT EXISTS daily_stats (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        date TEXT,
        user_count INTEGER,
        question_count INTEGER,
        avg_length REAL
    )
    """)

    conn.commit()
    conn.close()


# =========================
# 3. 记录游客对话
# =========================

def save_chat(user_input: str, bot_response: str, emotion: str = "neutral", interest: str = ""):
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()

    cursor.execute("""
    INSERT INTO chat_logs (time, user_input, bot_response, emotion, interest)
    VALUES (?, ?, ?, ?, ?)
    """, (
        datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        user_input,
        bot_response,
        emotion,
        interest
    ))

    conn.commit()
    conn.close()


# =========================
# 4. 获取当天统计
# =========================

def get_today_stats():
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()

    today = datetime.datetime.now().strftime("%Y-%m-%d")

    cursor.execute("""
    SELECT * FROM chat_logs WHERE time LIKE ?
    """, (today + "%",))

    rows = cursor.fetchall()
    conn.close()

    return rows


# =========================
# 5. 生成统计数据（用于大屏）
# =========================

def generate_daily_report():
    conn = sqlite3.connect(DB_PATH)

    df = pd.read_sql_query("SELECT * FROM chat_logs", conn)

    conn.close()

    if df.empty:
        return {
            "user_count": 0,
            "question_count": 0,
            "avg_length": 0
        }

    today = datetime.datetime.now().strftime("%Y-%m-%d")

    today_df = df[df["time"].str.contains(today)]

    user_count = len(today_df)
    question_count = len(df)

    avg_length = df["user_input"].apply(len).mean()

    return {
        "user_count": int(user_count),
        "question_count": int(question_count),
        "avg_length": float(avg_length)
    }


# =========================
# 6. 热门问题统计
# =========================

def get_hot_questions(top_k=5):
    conn = sqlite3.connect(DB_PATH)

    df = pd.read_sql_query("SELECT user_input FROM chat_logs", conn)

    conn.close()

    if df.empty:
        return []

    counts = df["user_input"].value_counts().head(top_k)

    return list(zip(counts.index, counts.values))


# =========================
# 7. 情绪统计
# =========================

def emotion_statistics():
    conn = sqlite3.connect(DB_PATH)

    df = pd.read_sql_query("SELECT emotion FROM chat_logs", conn)

    conn.close()

    if df.empty:
        return {}

    return df["emotion"].value_counts().to_dict()


# =========================
# 8. 游客兴趣分析
# =========================

def interest_statistics():
    conn = sqlite3.connect(DB_PATH)

    df = pd.read_sql_query("SELECT interest FROM chat_logs", conn)

    conn.close()

    if df.empty:
        return {}

    return df["interest"].value_counts().to_dict()


# =========================
# 9. 初始化测试
# =========================

if __name__ == "__main__":
    init_db()

    print("数据库初始化完成")

    save_chat("灵山大佛在哪里？", "灵山大佛位于无锡灵山胜境核心区域", "positive", "佛教文化")

    print("今日统计：", get_today_stats())

    print("热门问题：", get_hot_questions())

    print("情绪分布：", emotion_statistics())

    print("兴趣分布：", interest_statistics())