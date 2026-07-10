# report.py
# =========================================
# 灵山胜境AI导游 - 数据统计与游客分析模块
# =========================================

import sqlite3
import pandas as pd
import datetime
import json
from collections import Counter

DB_PATH = "tourist_data.db"


# =========================
# 1. 读取全部数据
# =========================

def load_all_data():
    conn = sqlite3.connect(DB_PATH)
    df = pd.read_sql_query("SELECT * FROM chat_logs", conn)
    conn.close()
    return df


# =========================
# 2. 今日运营概览
# =========================

def daily_overview():
    df = load_all_data()

    if df.empty:
        return {
            "visitor_count": 0,
            "question_count": 0,
            "avg_length": 0
        }

    today = datetime.datetime.now().strftime("%Y-%m-%d")
    today_df = df[df["time"].str.contains(today)]

    return {
        "visitor_count": int(len(today_df)),
        "question_count": int(len(df)),
        "avg_length": float(df["user_input"].apply(len).mean())
    }


# =========================
# 3. 热门问题分析
# =========================

def hot_questions(top_k=5):
    df = load_all_data()

    if df.empty:
        return []

    counter = Counter(df["user_input"])
    return counter.most_common(top_k)


# =========================
# 4. 情绪趋势分析
# =========================

def emotion_trend():
    df = load_all_data()

    if df.empty:
        return {}

    if "emotion" not in df.columns:
        return {}

    return dict(Counter(df["emotion"]))


# =========================
# 5. 兴趣画像分析
# =========================

def interest_profile():
    df = load_all_data()

    if df.empty:
        return {}

    if "interest" not in df.columns:
        return {}

    return dict(Counter(df["interest"]))


# =========================
# 6. 数据大屏接口（核心）
# =========================

def dashboard_data():
    """
    给前端大屏用的统一接口
    """

    return {
        "overview": daily_overview(),
        "hot_questions": hot_questions(),
        "emotion": emotion_trend(),
        "interest": interest_profile()
    }


# =========================
# 7. 导出报告（JSON）
# =========================

def export_report(file_path="report.json"):
    data = dashboard_data()

    with open(file_path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=4)

    return file_path


# =========================
# 8. 测试代码
# =========================

if __name__ == "__main__":

    print("=== 数据大屏 ===")
    print(json.dumps(dashboard_data(), ensure_ascii=False, indent=2))

    path = export_report()
    print("\n报告已导出：", path)