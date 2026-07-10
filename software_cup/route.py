# =========================================
# 灵山胜境AI导游 - 语义路线推荐系统（升级版）
# =========================================

# =========================
# 1. 景点权重知识图谱
# =========================

SPOTS = {
    "灵山大佛": {
        "tags": ["佛教", "震撼", "登高", "徒步", "核心"],
    },
    "九龙灌浴": {
        "tags": ["表演", "亲子", "文化", "互动"],
    },
    "梵宫": {
        "tags": ["建筑", "文化", "艺术", "拍照"],
    },
    "五印坛城": {
        "tags": ["拍照", "文化", "静心"],
    },
    "祥符禅寺": {
        "tags": ["佛教", "静心", "文化"],
    },
    "灵山湖步道": {
        "tags": ["自然", "徒步", "休闲"],
    },
    "亲子互动区": {
        "tags": ["亲子", "互动", "儿童"],
    }
}


# =========================
# 2. 用户语义画像提取
# =========================

def extract_user_tags(text: str):

    text = text.lower()

    tags = []

    if any(k in text for k in ["亲子", "孩子", "家庭"]):
        tags.append("亲子")

    if any(k in text for k in ["老人", "长辈", "轻松"]):
        tags.append("休闲")

    if any(k in text for k in ["徒步", "爬山", "走路"]):
        tags.append("徒步")

    if any(k in text for k in ["拍照", "打卡"]):
        tags.append("拍照")

    if any(k in text for k in ["佛", "佛教", "大佛"]):
        tags.append("佛教")

    if any(k in text for k in ["文化", "历史"]):
        tags.append("文化")

    return tags if tags else ["通用"]


# =========================
# 3. 路线评分函数（核心）
# =========================

def score_spot(spot_tags, user_tags):

    score = 0

    for ut in user_tags:
        if ut in spot_tags:
            score += 3

    return score


# =========================
# 4. 路线生成
# =========================

def generate_route(user_text: str):

    user_tags = extract_user_tags(user_text)

    scored = []

    for spot, info in SPOTS.items():

        score = score_spot(info["tags"], user_tags)

        # ⭐基础权重（保证不会空）
        if score == 0:
            score = 1

        scored.append((score, spot))

    # 排序
    scored.sort(key=lambda x: x[0], reverse=True)

    # 取前4~6个
    route = [s for _, s in scored[:5]]

    return route


# =========================
# 5. 路线优化（去重+顺序保持）
# =========================

def optimize_route(route):
    seen = set()
    result = []

    for r in route:
        if r not in seen:
            result.append(r)
            seen.add(r)

    return result


# =========================
# 6. 对外接口
# =========================

def get_route(user_text: str):

    route = generate_route(user_text)
    route = optimize_route(route)

    return route


# =========================
# 7. 测试
# =========================

if __name__ == "__main__":

    tests = [
        "亲子游推荐路线",
        "老年人轻松游览",
        "喜欢徒步的路线",
        "拍照打卡推荐",
        "佛教文化路线"
    ]

    for t in tests:
        print("\n输入:", t)
        print("路线:", " -> ".join(get_route(t)))