import openai
import time
import re

# 初始化客户端（保持你的配置不变）
client = openai.OpenAI(
    api_key="d5424c87a42c4473912e14fa8857d63e.QeDCxtQrwBSGc6rM",
    base_url="https://open.bigmodel.cn/api/paas/v4"
)

# =========================================
# 1. SYSTEM PROMPT（奠定数字人导游的人设与底线）
# =========================================
SYSTEM_PROMPT = """你是一位富有亲和力、幽默且专业的“灵山胜境AI数字人导游”。

【核心业务行为规范】
1. 知识底线：你的所有回答必须严格基于用户提供的【景区权威资料】。
2. 聪明推理：如果资料中包含相关线索但不够完美（例如提及了某个景点，但没写具体的演出分钟数），请基于资料进行温和、合理解释或引导，不要生硬、机械地拒绝回答！
3. 礼貌谢绝：只有当资料完全不沾边（如问及其他城市、股市、科技、娱乐八卦等）时，才礼貌地告知：“作为灵山胜境的AI导游，我暂时只能为您解答本景区的历史文化与游览服务哦。”
4. 篇幅控制：所有回答必须控制在 3~5 句话以内，用词要精炼、口语化，确保适合数字人的语音播报和口型同步。

【语言风格】
多使用“您”、“欢迎来到灵山胜境”、“祝您旅途愉快”等热情导游口吻。
"""


# =========================================
# 2. 安全过滤（轻量级，保护比赛演示安全）
# =========================================
def safety_check(answer: str) -> bool:
    if not answer:
        return False
    blacklist = ["股市", "全球政治", "世界大战", "股票", "金融预测", "反动", "暴恐"]
    return not any(b in answer for b in blacklist)


# =========================================
# 3. 场景一：单轮标准交互（常用于特定按纽触发或强单轮）
# =========================================
def chat_single_turn(query: str, context: str = ""):
    """标准单轮RAG调用接口"""
    # 优雅防空处理，不给大模型制造逻辑悖论
    formatted_context = context.strip() if context else "【暂无直接匹配的景区基础资料，请根据常识礼貌引导游客，切勿捏造历史、数字事实】"

    user_content = f"【景区权威资料】\n{formatted_context}\n\n【游客当前提问】\n{query}"

    for _ in range(2):  # 失败重试
        try:
            response = client.chat.completions.create(
                model="glm-4.5",
                messages=[
                    {"role": "system", "content": SYSTEM_PROMPT},
                    {"role": "user", "content": user_content}
                ],
                temperature=0.3,  # 保持适度严谨与生动
                top_p=0.85,
                timeout=15
            )
            answer = response.choices[0].message.content.strip()

            if len(answer) < 4:
                answer = "很高兴为您服务，请问有什么我可以帮您的吗？"

            if not safety_check(answer):
                answer = "作为您的AI导游，我更擅长为您讲解灵山胜境的风光，其他话题我们先放一边吧。"

            return {"success": True, "answer": answer}

        except Exception as e:
            print(f"LLM单轮调用异常: {e}")
            time.sleep(0.5)

    return {"success": False, "answer": "哎呀，信号好像有点弱，请您稍后再试呢。"}


# =========================================
# 4. 场景二：多轮对话 Session 控场（重点修复！）
# =========================================
class RAGChatSession:
    """具备多轮上下文感知 + 动态知识召回的智能Session"""

    def __init__(self, knowledge_base):
        self.kb = knowledge_base  # 必须把外部实例化的知识库传进来
        self.history = []  # 存放原始历史，格式为 [{"role": "user/assistant", "content": "..."}]
        self.last_docs = []

    def ask(self, user_input: str) -> str:
        # 1. 进行Query改写或上下文融合（解决“哪里有休息区”隐含的上一轮“梵宫”语境）
        refined_query = user_input
        if len(self.history) >= 2:
            last_bot_output = self.history[-1]["content"]
            # 自动继承上一轮提及的核心景点
            for landmark in ["梵宫", "大佛", "九龙灌浴", "五印坛城", "祥符禅寺"]:
                if landmark in last_bot_output and landmark not in user_input:
                    if any(w in user_input for w in ["哪里", "时间", "怎么走", "多高", "特色"]):
                        refined_query = f"在{landmark}，{user_input}"
                        break

        # 2. 实时用融合后的Query去知识库检索
        docs = self.kb.search(refined_query, top_k=6)
        self.last_docs = docs
        context = "\n---\n".join(docs) if docs else "暂无直接对应资料。"

        # 3. 动态构建本轮的 User Prompt（把检索出来的知识强行塞进当前轮次，不污染历史记录）
        current_user_content = (
            "【最新补充景区资料】\n"
            "请优先使用带有【后台知识】标记的管理员上传资料；如果资料中有明确数值、地点、时间或答案，必须据此回答。\n"
            "回答涉及高度、时间、价格、年份、距离、数量时，必须保留资料中的数字和单位，不要省略或改成模糊说法。\n"
            f"{context}\n\n【游客当前提问】\n{user_input}"
        )

        # 4. 组装给大模型的 messages 发射队列：SYSTEM + 历史截取 + 当前带知识的提问
        messages = [{"role": "system", "content": SYSTEM_PROMPT}]

        # 只取最近4轮的真实干净对话历史，防止上下文过长失去焦点
        messages.extend(self.history[-4:])

        # 把当前这一轮带有【最新知识】的提示词加到队尾
        messages.append({"role": "user", "content": current_user_content})

        try:
            response = client.chat.completions.create(
                model="glm-4.5",
                messages=messages,
                temperature=0.3,
                top_p=0.85,
                timeout=15
            )
            answer = response.choices[0].message.content.strip()

            # 安全与兜底保障
            if not safety_check(answer) or len(answer) < 4:
                answer = "关于这个问题，建议您可以关注一下景区的实时公告，或者询问身边的志愿者哦。"

            # 5. ⚠️ 注意：往真实历史里追加时，只追加干净的原始对话，千万不要把【景区资料】追加进去！
            self.history.append({"role": "user", "content": user_input})
            self.history.append({"role": "assistant", "content": answer})

            return answer

        except Exception as e:
            print(f"LLM多轮调用异常: {e}")
            return "不好意思，我开小差了，您可以再说一遍吗？"


# =========================================
# 5. 场景三：数字人流式输出（支持实时TTS口型驱动）
# =========================================
def chat_stream(query: str, context: str = ""):
    """专为数字人前端设计的流式响应（Stream）"""
    formatted_context = context.strip() if context else "暂无直接匹配的景区基础资料。"
    user_content = f"【景区权威资料】\n{formatted_context}\n\n【游客当前提问】\n{query}"

    try:
        response = client.chat.completions.create(
            model="glm-4.5",
            messages=[
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": user_content}
            ],
            temperature=0.25,
            stream=True
        )

        for chunk in response:
            if chunk.choices and chunk.choices[0].delta.content:
                yield chunk.choices[0].delta.content

    except Exception as e:
        print(f"LLM流式调用异常: {e}")
        yield "系统正在连接中，请稍候。"
