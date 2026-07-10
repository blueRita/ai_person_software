# =========================================
# 灵山胜境AI导游 - 情感 + 兴趣 + 意图增强版
# =========================================

import re

# =========================
# 1. 情绪词典（增强版）
# =========================

POSITIVE_WORDS = [
    "好", "不错", "很好", "漂亮", "震撼", "喜欢", "满意",
    "棒", "精彩", "厉害", "值得", "推荐", "开心", "舒适"
]

NEGATIVE_WORDS = [
    "差", "不好", "一般", "失望", "坑", "贵", "累",
    "无聊", "垃圾", "不行", "太差", "拥挤", "排队"
]

# =========================
# 2. 兴趣 + 意图分类（重点升级）
# =========================

INTENT_KEYWORDS = {
    "family": ["亲子", "小孩", "孩子", "家庭", "带娃"],
    "route": ["路线", "怎么走", "游览", "顺序", "安排"],
    "buddha": ["佛", "大佛", "寺", "菩萨", "禅", "灵山"],
    "culture": ["文化", "历史", "故事", "背景"],
    "photo": ["拍照", "打卡", "照片", "摄影"],
    "food": ["吃", "美食", "素斋", "餐厅"]
}

# =========================
# 3. 情绪分析（升级逻辑）
# =========================

def analyze_emotion(text: str):

    text = text.lower()

    pos = sum(1 for w in POSITIVE_WORDS if w in text)
    neg = sum(1 for w in NEGATIVE_WORDS if w in text)

    total = pos + neg

    if total == 0:
        emotion = "neutral"
        score = 0.0
    else:
        score = (pos - neg) / total

        if score > 0.2:
            emotion = "positive"
        elif score < -0.2:
            emotion = "negative"
        else:
            emotion = "neutral"

    return emotion, round(score, 3)


# =========================
# 4. 兴趣 + 意图识别（统一输出）
# =========================

def detect_intent_and_interest(text: str):

    text = text.lower()

    intent = "general"
    interest = "general"

    for label, kws in INTENT_KEYWORDS.items():
        for kw in kws:
            if kw in text:
                intent = label
                interest = label
                return intent, interest

    return intent, interest


# =========================
# 5. 综合分析接口（推荐用）
# =========================

def analyze(text: str):

    emotion, score = analyze_emotion(text)
    intent, interest = detect_intent_and_interest(text)

    return {
        "emotion": emotion,
        "score": score,
        "interest": interest,
        "intent": intent
    }


# =========================
# 6. 测试
# =========================

if __name__ == "__main__":

    tests = [
        "灵山大佛太震撼了，非常漂亮",
        "亲子游路线推荐一下",
        "这里有点无聊，人太多了",
        "我想拍照打卡"
    ]

    for t in tests:
        print("\n输入：", t)
        print(analyze(t))