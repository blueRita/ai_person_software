import os
from PIL import Image, ImageDraw

# 确保 assets 目录存在
os.makedirs("assets", exist_ok=True)


def create_idle_gif():
    """生成一个模拟呼吸/眨眼的绿色待机Q版占位动图"""
    frames = []
    # 循环生成4帧，让正方形的大小和颜色有轻微变化（模拟呼吸）
    for i in range(4):
        img = Image.new("RGBA", (300, 300), "white")
        draw = ImageDraw.Draw(img)
        # 模拟玩偶身体
        size_offset = i * 4
        draw.rectangle([50 + size_offset, 80, 250 - size_offset, 280], fill=(100, 200, 100), outline="black", width=3)
        # 模拟眼睛（眨眼效果）
        eye_y = 150 if i != 2 else 153
        eye_h = 10 if i != 2 else 2
        draw.ellipse([90, eye_y, 110, eye_y + eye_h], fill="black")
        draw.ellipse([190, eye_y, 210, eye_y + eye_h], fill="black")
        # 闭着的嘴巴
        draw.line([140, 180, 160, 180], fill="black", width=4)
        frames.append(img)

    frames[0].save(
        r"assets\avatar_idle.gif",
        save_all=True,
        append_images=frames[1:],
        duration=300,
        loop=0
    )
    print("✅ 成功生成待机动图：assets\\avatar_idle.gif")


def create_speaking_gif():
    """生成一个嘴巴大张、颜色变红的说话状态动图"""
    frames = []
    for i in range(2):
        img = Image.new("RGBA", (300, 300), "white")
        draw = ImageDraw.Draw(img)
        # 说话时身体颜色变深，带有动态
        draw.rectangle([50, 80 - (i * 5), 250, 280], fill=(230, 100, 100), outline="black", width=3)
        # 睁大的眼睛
        draw.ellipse([90, 145, 110, 165], fill="black")
        draw.ellipse([190, 145, 210, 165], fill="black")
        # 嘴巴：第0帧小嘴，第1帧大嘴（张合效果）
        if i == 0:
            draw.ellipse([135, 175, 165, 190], fill=(150, 0, 0))
        else:
            draw.ellipse([130, 170, 170, 210], fill=(150, 0, 0))  # 大张的嘴

        frames.append(img)

    frames[0].save(
        r"assets\avatar_speaking.gif",
        save_all=True,
        append_images=frames[1:],
        duration=200,
        loop=0
    )
    print("✅ 成功生成说话动图：assets\\avatar_speaking.gif")


if __name__ == "__main__":
    create_idle_gif()
    create_speaking_gif()
    print("\n🎉 临时数字人素材准备完毕！现在可以去运行你的 Gradio 主程序了！")