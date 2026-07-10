# pipeline.py (纯后台多模态逻辑，不包含任何 gr.Blocks)
import asyncio
import os
import time
import edge_tts

AVATAR_IDLE = "assets/avatar_idle.gif"
AVATAR_SPEAKING = "assets/avatar_speaking.gif"
os.makedirs("assets", exist_ok=True)


async def generate_tts_async(text, output_path):
    """异步调用 Edge-TTS 生成导游语音"""
    communicate = edge_tts.Communicate(text, "zh-CN-YunxiNeural")
    await communicate.save(output_path)


def digital_human_pipeline(user_query, kb_instance, real_llm_function):
    """
    多模态数字人核心状态机（生成器）
    :param user_query: 用户输入的文本
    :param kb_instance: 传递 main.py 里的知识库实例
    :param real_llm_function: 传递 main.py 里的真实大模型调用函数
    """
    if not user_query.strip():
        yield "您好像没有说话呢，请问有什么可以帮您？", None, AVATAR_IDLE
        return

    print(f"\n[后台收到提问] -> {user_query}")

    # 1. 检索本地知识库 (使用从 main 传过来的知识库)
    matched_chunks = kb_instance.search(user_query, top_k=3)

    # 2. 调用你在 main.py 里写的、你更喜欢的那个真实大模型回答逻辑
    llm_response = real_llm_function(user_query, matched_chunks)
    print(f"[后台生成文本] -> {llm_response}")

    # 3. 异步合成语音 (使用正斜杠防止转义报错)
    audio_filename = f"assets/reply_{int(time.time())}.mp3"
    asyncio.run(generate_tts_async(llm_response, audio_filename))

    # 4. 动态计算玩偶说话应当持续的时间
    estimated_duration = max(3.0, len(llm_response) * 0.25 + 1.0)

    # 🛑 第一次闪送：瞬间刷新网页，文字展示、语音播放、玩偶立刻切到 SPEAKING (张嘴)
    yield llm_response, audio_filename, AVATAR_SPEAKING

    # 让玩偶保持张嘴说话的状态
    time.sleep(estimated_duration)

    # 🛑 第二次闪送：说话时间结束，悄悄把左侧的玩偶切回 IDLE (待机)，文字和语音保留
    yield llm_response, audio_filename, AVATAR_IDLE