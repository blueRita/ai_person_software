# =========================================================================
# 灵山胜境AI导游系统（无缝丝滑版：本地VITS + 多视频图层预载 + 前端音频防抖驱动）
# =========================================================================

from http import client
from flask import Flask, request, jsonify, send_from_directory, render_template_string, redirect, url_for
from werkzeug.utils import secure_filename
import time
import os
import re
import requests
import subprocess
import sys
import json
import html
import zipfile
import xml.etree.ElementTree as ET
import soundfile as sf

try:
    import sherpa_onnx
except ImportError:
    sherpa_onnx = None

# 引入智能多轮 Session 与核心组件
from llm import SYSTEM_PROMPT, RAGChatSession
from knowledge import KnowledgeBase
from emotion import analyze
from route import get_route
from database import init_db, save_chat
from report import dashboard_data

app = Flask(__name__)

# 初始化核心组件
print("正在初始化系统组件...")
kb = KnowledgeBase()
init_db()
chat_session = RAGChatSession(knowledge_base=kb)

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
ASSETS_DIR = os.path.join(BASE_DIR, "assets")
os.makedirs(ASSETS_DIR, exist_ok=True)
LIPSYNC_DIR = os.path.join(BASE_DIR, "LipSync")
WAV2LIP_CHECKPOINT = os.path.join(LIPSYNC_DIR, "checkpoints", "wav2lip_gan.pth")
AVATAR_FACE_VIDEO = os.path.join(ASSETS_DIR, "avatar_idle.mp4")
CACHE_MANIFEST_PATH = os.path.join(BASE_DIR, "cache_manifest.json")
ADMIN_KNOWLEDGE_DIR = os.path.join(BASE_DIR, "admin_knowledge")
ADMIN_FAQ_PATH = os.path.join(BASE_DIR, "admin_faq.json")
ADMIN_AVATAR_CONFIG_PATH = os.path.join(BASE_DIR, "avatar_config.json")
ALLOWED_KNOWLEDGE_EXTENSIONS = {".txt", ".md", ".doc", ".docx", ".pdf", ".json", ".csv", ".xlsx"}
ALLOWED_AVATAR_EXTENSIONS = {".mp4", ".webm"}
os.makedirs(ADMIN_KNOWLEDGE_DIR, exist_ok=True)

DEFAULT_AVATAR_CONFIG = {
    "display_name": "灵山胜境AI数字人导游",
    "role_name": "灵山小导游",
    "appearance": "亲和、端庄、年轻化的数字导游形象",
    "costume": "禅意素雅服装，融合灵山佛教文化与江南色彩",
    "cultural_style": "温和、专业、富有灵山胜境文化气质",
    "theme_color": "#1a73e8",
    "voice_name": "清亮亲和导游音",
    "voice_sid": 46,
    "voice_speed": 1.05,
    "idle_video": "avatar_idle.mp4",
    "speaking_video": "avatar_speaking.mp4",
    "thinking_video": "avatar_thinking.mp4",
}


def load_avatar_config():
    config = dict(DEFAULT_AVATAR_CONFIG)
    if os.path.exists(ADMIN_AVATAR_CONFIG_PATH):
        try:
            with open(ADMIN_AVATAR_CONFIG_PATH, "r", encoding="utf-8-sig") as f:
                saved = json.load(f)
            if isinstance(saved, dict):
                config.update(saved)
        except Exception as e:
            print(f"[avatar] load config failed: {e}")
    return normalize_avatar_config(config)


def normalize_avatar_config(config):
    clean = dict(DEFAULT_AVATAR_CONFIG)
    clean.update(config or {})
    for key in ["display_name", "role_name", "appearance", "costume", "cultural_style", "theme_color", "voice_name"]:
        clean[key] = str(clean.get(key) or DEFAULT_AVATAR_CONFIG[key]).strip()
    for key in ["idle_video", "speaking_video", "thinking_video"]:
        filename = admin_safe_filename(str(clean.get(key) or DEFAULT_AVATAR_CONFIG[key]))
        if not os.path.exists(os.path.join(ASSETS_DIR, filename)):
            filename = DEFAULT_AVATAR_CONFIG[key]
        clean[key] = filename
    try:
        clean["voice_sid"] = max(0, int(clean.get("voice_sid", DEFAULT_AVATAR_CONFIG["voice_sid"])))
    except Exception:
        clean["voice_sid"] = DEFAULT_AVATAR_CONFIG["voice_sid"]
    try:
        speed = float(clean.get("voice_speed", DEFAULT_AVATAR_CONFIG["voice_speed"]))
        clean["voice_speed"] = min(1.6, max(0.6, speed))
    except Exception:
        clean["voice_speed"] = DEFAULT_AVATAR_CONFIG["voice_speed"]
    if not re.match(r"^#[0-9a-fA-F]{6}$", clean["theme_color"]):
        clean["theme_color"] = DEFAULT_AVATAR_CONFIG["theme_color"]
    return clean


def save_avatar_config(config):
    config = normalize_avatar_config(config)
    with open(ADMIN_AVATAR_CONFIG_PATH, "w", encoding="utf-8") as f:
        json.dump(config, f, ensure_ascii=False, indent=2)
    return config


def get_avatar_asset_path(kind):
    key = f"{kind}_video"
    filename = load_avatar_config().get(key, DEFAULT_AVATAR_CONFIG.get(key, "avatar_idle.mp4"))
    path = os.path.abspath(os.path.join(ASSETS_DIR, filename))
    if os.path.exists(path):
        return path
    return AVATAR_FACE_VIDEO


# =========================================================================
# 🧮 文本规范化工具：将阿拉伯数字智能转换为中文汉字
# =========================================================================
def int_to_zh(num_str):
    num = int(num_str)
    if len(num_str) == 4 and (num_str.startswith('1') or num_str.startswith('2')):
        zh_chars = ['零', '一', '二', '三', '四', '五', '六', '七', '八', '九']
        return "".join(zh_chars[int(d)] for d in num_str)

    digits = ['零', '一', '二', '三', '四', '五', '六', '七', '八', '九']
    units = ['', '十', '百', '千', '万', '十', '百', '千', '亿']
    if num == 0:
        return '零'

    res = ""
    str_n = str(num)
    length = len(str_n)
    if length > len(units):
        return "".join(digits[int(d)] for d in num_str)

    for i, d in enumerate(str_n):
        digit = int(d)
        if digit != 0:
            res += digits[digit] + units[length - 1 - i]
        else:
            if res and not res.endswith('零') and i != length - 1 and int(str_n[i + 1:]) != 0:
                res += '零'
    if res.startswith("一十") and length == 2:
        res = res[1:]
    return res


def normalize_text(text):
    if not text:
        return ""

    digit_zh = ['零', '一', '二', '三', '四', '五', '六', '七', '八', '九']

    def number_to_speech(num_text):
        num_text = str(num_text).strip()
        if "." in num_text:
            left, right = num_text.split(".", 1)
            right = right.rstrip("0") or "零"
            return int_to_zh(left) + "点" + "".join(digit_zh[int(ch)] for ch in right if ch.isdigit())
        return int_to_zh(num_text)

    def time_to_speech(match):
        hour = int(match.group(1))
        minute_text = match.group(2)
        second_text = match.group(3)
        result = f"{int_to_zh(str(hour))}点"
        if minute_text == "00":
            result += "整"
        else:
            minute = int(minute_text)
            if minute < 10:
                result += "零" + int_to_zh(str(minute)) + "分"
            else:
                result += int_to_zh(str(minute)) + "分"
        if second_text:
            second = int(second_text)
            if second > 0:
                result += int_to_zh(str(second)) + "秒"
        return result

    text = str(text)
    text = text.translate(str.maketrans("０１２３４５６７８９．：，％", "0123456789.:,%"))

    unit_replacements = [
        (r"km²|km2|平方千米|平方公里", "平方公里"),
        (r"m²|m2|㎡|平方米", "平方米"),
        (r"cm²|cm2|平方厘米", "平方厘米"),
        (r"mm²|mm2|平方毫米", "平方毫米"),
        (r"㎞", "公里"),
        (r"㎝", "厘米"),
        (r"㎜", "毫米"),
        (r"(?<=\d)\s*m\b", "米"),
        (r"(?<=\d)\s*km\b", "公里"),
        (r"(?<=\d)\s*cm\b", "厘米"),
        (r"(?<=\d)\s*mm\b", "毫米"),
    ]
    for pattern, replacement in unit_replacements:
        text = re.sub(pattern, replacement, text, flags=re.IGNORECASE)

    text = re.sub(r"(?<!\d)([01]?\d|2[0-3])[:：]([0-5]\d)(?:[:：]([0-5]\d))?", time_to_speech, text)
    text = re.sub(
        r"(\d+(?:\.\d+)?)\s*%",
        lambda m: "百分之" + number_to_speech(m.group(1)),
        text,
    )
    text = re.sub(
        r"(\d+(?:\.\d+)?)\s*[-~～—]\s*(\d+(?:\.\d+)?)",
        lambda m: number_to_speech(m.group(1)) + "到" + number_to_speech(m.group(2)),
        text,
    )
    text = re.sub(r"\d+\.\d+", lambda m: number_to_speech(m.group(0)), text)
    text = re.sub(r'\d+', lambda x: int_to_zh(x.group(0)), text)
    text = re.sub(r"(?<=[分整秒米元年月日])\s*[-~～—]\s*(?=[零一二三四五六七八九十])", "到", text)
    text = re.sub(r"[：:]", "，", text)
    return text


# =========================================================================
# 🪄 全局一次性初始化本地高清 VITS 离线引擎
# =========================================================================
VITS_MODEL_DIR = os.path.abspath(os.path.join(BASE_DIR, "..", "vits-zh-hf-fanchen-C"))

try:
    if sherpa_onnx is None:
        raise ImportError("sherpa_onnx is not installed")
    print("正在预加载本地VITS语音包...")
    tts_config = sherpa_onnx.OfflineTtsConfig(
        model=sherpa_onnx.OfflineTtsModelConfig(
            vits=sherpa_onnx.OfflineTtsVitsModelConfig(
                model=f"{VITS_MODEL_DIR}/vits-zh-hf-fanchen-C.onnx",
                lexicon=f"{VITS_MODEL_DIR}/lexicon.txt",
                tokens=f"{VITS_MODEL_DIR}/tokens.txt",
                data_dir=f"{VITS_MODEL_DIR}/espeak-ng-data" if os.path.exists(
                    f"{VITS_MODEL_DIR}/espeak-ng-data") else "",
            ),
            num_threads=4,
            debug=False,
        )
    )
    offline_vits_engine = sherpa_onnx.OfflineTts(tts_config)
    print("本地VITS引擎加载就绪")
except Exception as e:
    print(f"本地VITS语音包加载失败: {e}")
    offline_vits_engine = None


# =========================================================================
#  高可用语音合成逻辑 (.wav 格式输出)
# =========================================================================
def generate_cloned_tts(text, output_filename):
    output_path = os.path.join(ASSETS_DIR, output_filename)

#     # 【方案 1】：本地 GPT-SoVITS 动态克隆
#     sovits_api_url = "http://127.0.0.1:9880"
#     payload = {
#         "text": text, "text_language": "zh",
#         "ref_audio_path": "vocal_seed.wav",
#         "prompt_text": "小和尚原话", "prompt_language": "zh"
#     }
#     try:
#         response = requests.post(sovits_api_url, json=payload, timeout=1.0)
#         if response.status_code == 200:
#             with open(output_path, "wb") as f: f.write(response.content)
#             print("✅ [方案1] 成功调用本地专属音色克隆！")
#             return output_filename
#     except:
#         pass

#     # 【方案 2】：微软云端高品质正太音色
#     try:
#         import asyncio, edge_tts
#         VOICE = "zh-CN-YunxiNeural"

#         async def amake_tts():
#             communicate = edge_tts.Communicate(text, VOICE)
#             await communicate.save(output_path)

#         asyncio.run(amake_tts())
#         print("✅ [方案2] 成功调用微软云端阳光正太音！")
#         return output_filename
#     except:
#         pass

    # 【方案3】： 本地离线语音包
    if offline_vits_engine:
        try:
            print("[方案3] 正在使用本地预下载的高清语音模型进行无网推理...")
            processed_text = normalize_text(text)
            print(f"[数字规范化修正]原始文本 -> 语音文本: \"{processed_text}\"")

            avatar_config = load_avatar_config()
            selected_sid = avatar_config["voice_sid"]
            voice_speed = avatar_config["voice_speed"]
            audio = offline_vits_engine.generate(processed_text, sid=selected_sid, speed=voice_speed)
            sf.write(output_path, audio.samples, samplerate=audio.sample_rate)
            print(f"[方案3] 本地 VITS 音频生成成功: sid={selected_sid}, speed={voice_speed}")
            return output_filename
        except Exception as vits_err:
            print(f"方案3模型生成失败: {vits_err}")

    # 【方案 4】：系统底层原始音绝对兜底
    try:
        import pyttsx3
        engine = pyttsx3.init()
        engine.setProperty('rate', 195)
        engine.save_to_file(text, output_path)
        engine.runAndWait()
        print("[方案4] 系统基础离线引擎兜底完成。")
        return output_filename
    except:
        return None


def generate_lipsync_video(audio_filename):
    """Generate a speech video whose mouth frames are driven by the exact TTS audio."""
    if not audio_filename:
        return None
    face_video = get_avatar_asset_path("idle")
    if not (os.path.exists(WAV2LIP_CHECKPOINT) and os.path.exists(face_video)):
        return None

    stem = os.path.splitext(audio_filename)[0]
    output_filename = f"{stem}_lipsync.mp4"
    audio_path = os.path.abspath(os.path.join(ASSETS_DIR, audio_filename))
    output_path = os.path.abspath(os.path.join(ASSETS_DIR, output_filename))

    cmd = [
        sys.executable,
        "inference.py",
        "--checkpoint_path", os.path.abspath(WAV2LIP_CHECKPOINT),
        "--face", os.path.abspath(face_video),
        "--audio", audio_path,
        "--outfile", output_path,
        "--resize_factor", "2",
        "--static", "True",
        "--nosmooth",
    ]

    try:
        result = subprocess.run(
            cmd,
            cwd=LIPSYNC_DIR,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            timeout=900,
        )
        if result.returncode == 0 and os.path.exists(output_path):
            print(f"[Wav2Lip] generated {output_filename}")
            return output_filename
        print(f"[Wav2Lip] failed:\n{result.stdout[-2000:]}")
    except Exception as e:
        print(f"[Wav2Lip] skipped: {e}")
    return None


def get_cached_lipsync_video(item):
    lipsync_video = item.get("lipsync_video_file", "")
    if lipsync_video and os.path.exists(os.path.join(ASSETS_DIR, lipsync_video)):
        return lipsync_video

    audio_file = item.get("audio_file", "")
    if not audio_file:
        video_file = item.get("video_file", "")
        if video_file and os.path.exists(os.path.join(ASSETS_DIR, video_file)):
            return video_file
        return None

    expected_video = lipsync_video or f"{os.path.splitext(audio_file)[0]}_lipsync.mp4"
    expected_path = os.path.join(ASSETS_DIR, expected_video)
    if os.path.exists(expected_path):
        return expected_video

    print(f"[cache] missing lipsync video: {expected_path}")
    return None




def normalize_cache_key(text):
    text = (text or "").lower()
    return re.sub(r"[^\w\u4e00-\u9fff]+", "", text)


def load_cache_answer(item):
    video_file = item.get("video_file", "")
    answer_file = item.get("answer_file", "")
    if not answer_file and video_file:
        answer_file = os.path.splitext(video_file)[0] + ".txt"

    if answer_file:
        answer_path = os.path.join(ASSETS_DIR, answer_file)
        if os.path.exists(answer_path):
            try:
                with open(answer_path, "r", encoding="utf-8-sig") as f:
                    text = f.read().strip()
                if text:
                    return text
            except Exception as e:
                print(f"[cache] answer file load failed: {answer_path}, {e}")

    return item.get("answer", "")


def find_cached_reply(question):
    if not os.path.exists(CACHE_MANIFEST_PATH):
        print(f"[cache] manifest not found: {CACHE_MANIFEST_PATH}")
        return None
    try:
        with open(CACHE_MANIFEST_PATH, "r", encoding="utf-8-sig") as f:
            cache_items = json.load(f)
    except Exception as e:
        print(f"[cache] manifest load failed: {e}")
        return None

    normalized_question = normalize_cache_key(question)
    for item in cache_items:
        keywords = item.get("keywords", [])
        video_file = item.get("video_file", "")
        audio_file = item.get("audio_file", "")
        if not keywords or not (video_file or audio_file):
            continue

        normalized_keywords = [normalize_cache_key(keyword) for keyword in keywords]
        matched = any(
            keyword and (keyword in normalized_question or normalized_question in keyword)
            for keyword in normalized_keywords
        )
        if not matched:
            continue

        if audio_file:
            audio_path = os.path.join(ASSETS_DIR, audio_file)
            if not os.path.exists(audio_path):
                print(f"[cache] matched {item.get('id', audio_file)} but audio missing: {audio_path}")
                continue

        if video_file:
            video_path = os.path.join(ASSETS_DIR, video_file)
            if not os.path.exists(video_path):
                print(f"[cache] matched {item.get('id', video_file)} but video missing: {video_path}")
                continue

        if not (audio_file or video_file):
            continue

        cached_item = dict(item)
        cached_item["answer"] = load_cache_answer(item)
        return cached_item

    return None


@app.route('/assets/<path:filename>')
def serve_assets(filename):
    return send_from_directory(ASSETS_DIR, filename)


def safe(x):
    if isinstance(x, (set, tuple)): return list(x)
    if isinstance(x, dict): return {k: safe(v) for k, v in x.items()}
    if isinstance(x, list): return [safe(i) for i in x]
    return x


def admin_safe_filename(filename):
    name = os.path.basename((filename or "").replace("\\", "/"))
    name = re.sub(r"[^\w\u4e00-\u9fff.\-]+", "_", name).strip("._")
    return name or secure_filename(filename)


def admin_save_avatar_upload(field_name, current_filename):
    file = request.files.get(field_name)
    if not file or not file.filename:
        return current_filename
    filename = admin_safe_filename(file.filename)
    ext = os.path.splitext(filename)[1].lower()
    if ext not in ALLOWED_AVATAR_EXTENSIONS:
        return current_filename
    target_name = f"avatar_custom_{field_name}{ext}"
    file.save(os.path.join(ASSETS_DIR, target_name))
    return target_name


def admin_load_faqs():
    if not os.path.exists(ADMIN_FAQ_PATH):
        return []
    try:
        with open(ADMIN_FAQ_PATH, "r", encoding="utf-8-sig") as f:
            data = json.load(f)
        return data if isinstance(data, list) else []
    except Exception:
        return []


def admin_save_faqs(items):
    with open(ADMIN_FAQ_PATH, "w", encoding="utf-8") as f:
        json.dump(items, f, ensure_ascii=False, indent=2)


def admin_find_faq_reply(query):
    query_key = normalize_cache_key(query)
    if not query_key:
        return None
    fallback = None
    for item in admin_load_faqs():
        question = str(item.get("question", "")).strip()
        answer = str(item.get("answer", "")).strip()
        if not question or not answer:
            continue
        question_key = normalize_cache_key(question)
        if query_key == question_key:
            return {"question": question, "answer": answer}
        if question_key and (query_key in question_key or question_key in query_key):
            fallback = fallback or {"question": question, "answer": answer}
    return fallback


def admin_cell_to_text(value):
    if value is None:
        return ""
    try:
        if hasattr(value, "strftime"):
            return value.strftime("%Y-%m-%d %H:%M:%S").rstrip(" 00:00:00")
    except Exception:
        pass
    text = str(value).strip()
    if not text or text.lower() in {"nan", "none", "nat"}:
        return ""
    if re.fullmatch(r"-?\d+\.0", text):
        return text[:-2]
    return text


def admin_extract_knowledge_text(path):
    ext = os.path.splitext(path)[1].lower()
    try:
        if ext in {".txt", ".md"}:
            with open(path, "r", encoding="utf-8-sig", errors="ignore") as f:
                return f.read()
        if ext == ".csv":
            import pandas as pd
            df = pd.read_csv(path).fillna("")
            lines = []
            for _, row in df.iterrows():
                cells = [f"{col}：{text}" for col, val in row.items() if (text := admin_cell_to_text(val))]
                if cells:
                    lines.append("，".join(cells))
            return "\n".join(lines)
        if ext == ".xlsx":
            import pandas as pd
            sheets = pd.read_excel(path, sheet_name=None).items()
            lines = []
            for sheet_name, df in sheets:
                df = df.fillna("")
                for _, row in df.iterrows():
                    cells = [f"{col}：{text}" for col, val in row.items() if (text := admin_cell_to_text(val))]
                    if cells:
                        lines.append(f"【{sheet_name}】" + "，".join(cells))
            return "\n".join(lines)
        if ext == ".json":
            with open(path, "r", encoding="utf-8-sig", errors="ignore") as f:
                return json.dumps(json.load(f), ensure_ascii=False)
        if ext == ".docx":
            with zipfile.ZipFile(path) as docx:
                xml = docx.read("word/document.xml").decode("utf-8", errors="ignore")
            root = ET.fromstring(xml)
            ns = {"w": "http://schemas.openxmlformats.org/wordprocessingml/2006/main"}
            lines = []
            for paragraph in root.findall(".//w:p", ns):
                parts = [node.text or "" for node in paragraph.findall(".//w:t", ns)]
                text = html.unescape("".join(parts)).strip()
                if text:
                    lines.append(text)
            return "\n".join(lines)
    except Exception as e:
        print(f"[admin] knowledge extract failed: {path}, {e}")
    return ""


def admin_split_knowledge_text(text, max_len=420):
    lines = [line.strip() for line in text.splitlines() if line.strip()]
    if len(lines) > 1:
        chunks = []
        current = ""
        for line in lines:
            if len(line) >= max_len:
                chunks.append(line[:max_len])
                continue
            if len(current) + len(line) <= max_len:
                current = f"{current}\n{line}".strip()
            else:
                if len(current) > 8:
                    chunks.append(current)
                current = line
        if len(current) > 8:
            chunks.append(current)
        return chunks

    sentences = [s.strip() for s in re.split(r"(?<=[。！？；\n])", text) if s.strip()]
    chunks = []
    current = ""
    for sentence in sentences:
        if len(current) + len(sentence) <= max_len:
            current += sentence
        else:
            if len(current) > 8:
                chunks.append(current)
            current = sentence
    if len(current) > 8:
        chunks.append(current)
    return chunks


def admin_refresh_knowledge_chunks():
    base_chunks = [c for c in getattr(kb, "chunks", []) if not c.startswith("【后台知识】")]
    admin_chunks = []
    for item in admin_list_knowledge_files():
        path = os.path.join(ADMIN_KNOWLEDGE_DIR, item["name"])
        text = admin_extract_knowledge_text(path)
        for chunk in admin_split_knowledge_text(text):
            admin_chunks.append(f"【后台知识】{chunk}")
    kb.chunks = admin_chunks + base_chunks
    print(f"[admin] loaded {len(admin_chunks)} admin knowledge chunks")


def admin_list_knowledge_files():
    rows = []
    for name in sorted(os.listdir(ADMIN_KNOWLEDGE_DIR)):
        path = os.path.join(ADMIN_KNOWLEDGE_DIR, name)
        if not os.path.isfile(path):
            continue
        stat = os.stat(path)
        rows.append({
            "name": name,
            "size_kb": round(stat.st_size / 1024, 1),
            "mtime": time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(stat.st_mtime)),
        })
    return rows


def admin_load_chat_logs(limit=200):
    import sqlite3

    db_path = os.path.abspath(os.path.join(BASE_DIR, "..", "tourist_data.db"))
    if not os.path.exists(db_path):
        db_path = os.path.abspath(os.path.join(BASE_DIR, "tourist_data.db"))
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    try:
        rows = conn.execute(
            "SELECT time, user_input, bot_response, emotion, interest FROM chat_logs ORDER BY id DESC LIMIT ?",
            (limit,)
        ).fetchall()
        return [dict(row) for row in rows]
    except Exception:
        return []
    finally:
        conn.close()


def admin_keyword_focus(logs):
    stop_words = {"什么", "怎么", "一下", "介绍", "请问", "可以", "有没有", "多少", "哪里", "哪个", "我们", "你们"}
    counts = {}
    for row in logs:
        text = row.get("user_input") or ""
        for word in re.findall(r"[\u4e00-\u9fff]{2,6}", text):
            if word in stop_words:
                continue
            counts[word] = counts.get(word, 0) + 1
    return sorted(counts.items(), key=lambda x: x[1], reverse=True)[:10]


def admin_report_data():
    logs = admin_load_chat_logs(500)
    today = time.strftime("%Y-%m-%d")
    now = time.time()
    week_cutoff = now - 7 * 24 * 3600
    today_logs = [r for r in logs if (r.get("time") or "").startswith(today)]
    week_logs = []
    for row in logs:
        try:
            ts = time.mktime(time.strptime(row.get("time", ""), "%Y-%m-%d %H:%M:%S"))
            if ts >= week_cutoff:
                week_logs.append(row)
        except Exception:
            pass

    emotion_counts = {}
    for row in logs:
        emotion = row.get("emotion") or "neutral"
        emotion_counts[emotion] = emotion_counts.get(emotion, 0) + 1

    positive = emotion_counts.get("positive", 0)
    neutral = emotion_counts.get("neutral", 0)
    negative = emotion_counts.get("negative", 0)
    total_emotion = positive + neutral + negative
    satisfaction = 0 if total_emotion == 0 else round((positive * 100 + neutral * 75 + negative * 45) / total_emotion, 1)

    hot_questions = {}
    for row in logs:
        q = row.get("user_input") or ""
        hot_questions[q] = hot_questions.get(q, 0) + 1

    suggestions = []
    focus = admin_keyword_focus(logs)
    if focus:
        suggestions.append(f"重点补充“{focus[0][0]}”相关讲解词和 FAQ。")
    if negative:
        suggestions.append("近期存在负向情绪记录，建议复盘相关问答并优化服务话术。")
    if not suggestions:
        suggestions.append("当前交互整体平稳，可继续扩充高频景点讲解内容。")

    return {
        "today_count": len(today_logs),
        "week_count": len(week_logs),
        "total_count": len(logs),
        "hot_questions": sorted(hot_questions.items(), key=lambda x: x[1], reverse=True)[:8],
        "emotion_counts": emotion_counts,
        "satisfaction": satisfaction,
        "focus": focus,
        "suggestions": suggestions,
        "recent_logs": logs[:20],
    }


@app.route("/admin")
def admin_index():
    files = admin_list_knowledge_files()
    faqs = admin_load_faqs()
    report = admin_report_data()
    avatar_config = load_avatar_config()
    return render_template_string("""
<!doctype html>
<html>
<head>
<meta charset="utf-8">
<title>管理后台</title>
<style>
body{margin:0;background:#f5f7fb;font-family:Arial,"Microsoft YaHei",sans-serif;color:#1f2937}
.top{background:#172033;color:#fff;padding:18px 28px;font-size:22px;font-weight:700}
.wrap{padding:22px;display:grid;grid-template-columns:1.1fr 1fr;gap:18px}
.full{grid-column:1 / -1}
.panel{background:#fff;border:1px solid #e5e7eb;border-radius:8px;padding:18px}
h2{margin:0 0 14px;font-size:18px}
.cards{display:grid;grid-template-columns:repeat(4,1fr);gap:12px}
.card{background:#f8fafc;border:1px solid #e5e7eb;border-radius:8px;padding:14px}
.num{font-size:28px;font-weight:800;color:#1a73e8;margin-top:6px}
table{width:100%;border-collapse:collapse;font-size:14px}
th,td{border-bottom:1px solid #eee;padding:8px;text-align:left;vertical-align:top}
input,textarea{width:100%;box-sizing:border-box;padding:9px;border:1px solid #d1d5db;border-radius:6px}
textarea{height:76px}
button{background:#1a73e8;color:#fff;border:0;border-radius:6px;padding:9px 14px;cursor:pointer}
.muted{color:#6b7280;font-size:13px}
.chips span{display:inline-block;background:#eef2ff;color:#3730a3;padding:5px 8px;border-radius:99px;margin:4px}
.danger{background:#dc2626}
.form-grid{display:grid;grid-template-columns:1fr 1fr;gap:12px}
.form-grid label{font-size:13px;color:#374151;font-weight:700}
.form-grid input,.form-grid textarea{margin-top:6px}
.avatar-preview{display:grid;grid-template-columns:repeat(3,1fr);gap:10px;margin-top:10px}
.avatar-preview video{width:100%;height:150px;object-fit:cover;border-radius:8px;background:#111827}
</style>
</head>
<body>
<div class="top">景区数字人管理后台</div>
<div class="wrap">
  <section class="panel full">
    <h2>数据大屏概览</h2>
    <div class="cards">
      <div class="card">今日服务人次<div class="num">{{ report.today_count }}</div></div>
      <div class="card">本周服务人次<div class="num">{{ report.week_count }}</div></div>
      <div class="card">累计交互记录<div class="num">{{ report.total_count }}</div></div>
      <div class="card">游客满意度<div class="num">{{ report.satisfaction }}%</div></div>
    </div>
  </section>

  <section class="panel full">
    <h2>数字人形象配置</h2>
    <form action="/admin/avatar/config" method="post" enctype="multipart/form-data">
      <div class="form-grid">
        <label>数字人名称
          <input name="display_name" value="{{ avatar.display_name }}" required>
        </label>
        <label>角色定位
          <input name="role_name" value="{{ avatar.role_name }}" required>
        </label>
        <label>外观描述
          <textarea name="appearance">{{ avatar.appearance }}</textarea>
        </label>
        <label>服装设定
          <textarea name="costume">{{ avatar.costume }}</textarea>
        </label>
        <label>景区文化风格
          <textarea name="cultural_style">{{ avatar.cultural_style }}</textarea>
        </label>
        <label>主题色
          <input name="theme_color" value="{{ avatar.theme_color }}" placeholder="#1a73e8">
        </label>
        <label>声音名称
          <input name="voice_name" value="{{ avatar.voice_name }}">
        </label>
        <label>VITS 声线 SID
          <input name="voice_sid" type="number" min="0" max="999" value="{{ avatar.voice_sid }}">
        </label>
        <label>语速
          <input name="voice_speed" type="number" min="0.6" max="1.6" step="0.05" value="{{ avatar.voice_speed }}">
        </label>
        <label>待机视频 mp4/webm
          <input name="idle" type="file" accept=".mp4,.webm">
        </label>
        <label>说话视频 mp4/webm
          <input name="speaking" type="file" accept=".mp4,.webm">
        </label>
        <label>思考视频 mp4/webm
          <input name="thinking" type="file" accept=".mp4,.webm">
        </label>
      </div>
      <p class="muted">当前素材：待机 {{ avatar.idle_video }}；说话 {{ avatar.speaking_video }}；思考 {{ avatar.thinking_video }}。保存后游客端刷新即可生效。</p>
      <button type="submit">保存数字人配置</button>
    </form>
    <div class="avatar-preview">
      <video src="/assets/{{ avatar.idle_video }}" muted loop autoplay playsinline></video>
      <video src="/assets/{{ avatar.speaking_video }}" muted loop autoplay playsinline></video>
      <video src="/assets/{{ avatar.thinking_video }}" muted loop autoplay playsinline></video>
    </div>
  </section>

  <section class="panel">
    <h2>知识库管理</h2>
    <form action="/admin/knowledge/upload" method="post" enctype="multipart/form-data">
      <input type="file" name="file" required>
      <p class="muted">支持讲解词、文史资料、FAQ 文档：txt / md / docx / pdf / json / csv / xlsx</p>
      <button type="submit">上传知识文档</button>
    </form>
    <h3>已上传文档</h3>
    <form action="/admin/knowledge/rebuild" method="post" style="margin:8px 0 12px;">
      <button type="submit">重建知识索引</button>
      <span class="muted">上传数据集后如回答不准，可先重建索引。</span>
    </form>
    <table>
      <tr><th>文件</th><th>大小KB</th><th>更新时间</th><th>操作</th></tr>
      {% for f in files %}
      <tr>
        <td>{{ f.name }}</td><td>{{ f.size_kb }}</td><td>{{ f.mtime }}</td>
        <td><form action="/admin/knowledge/delete/{{ f.name }}" method="post"><button class="danger">删除</button></form></td>
      </tr>
      {% endfor %}
    </table>
  </section>

  <section class="panel">
    <h2>常见问题维护</h2>
    <form action="/admin/faq/add" method="post">
      <p><input name="question" placeholder="常见问题，例如：大佛多高？" required></p>
      <p><textarea name="answer" placeholder="标准回答" required></textarea></p>
      <button type="submit">新增 FAQ</button>
    </form>
    <table>
      <tr><th>问题</th><th>回答</th><th>操作</th></tr>
      {% for item in faqs %}
      <tr>
        <td>{{ item.question }}</td><td>{{ item.answer }}</td>
        <td><form action="/admin/faq/delete/{{ loop.index0 }}" method="post"><button class="danger">删除</button></form></td>
      </tr>
      {% endfor %}
    </table>
  </section>

  <section class="panel">
    <h2>游客感受度报告</h2>
    <h3>关注点分析</h3>
    <div class="chips">{% for k,v in report.focus %}<span>{{ k }} · {{ v }}</span>{% endfor %}</div>
    <h3>情感趋势</h3>
    <pre>{{ report.emotion_counts }}</pre>
    <h3>服务建议</h3>
    <ul>{% for s in report.suggestions %}<li>{{ s }}</li>{% endfor %}</ul>
  </section>

  <section class="panel">
    <h2>热门问答</h2>
    <table>
      <tr><th>问题</th><th>次数</th></tr>
      {% for q,c in report.hot_questions %}
      <tr><td>{{ q }}</td><td>{{ c }}</td></tr>
      {% endfor %}
    </table>
  </section>

  <section class="panel full">
    <h2>最近交互记录</h2>
    <table>
      <tr><th>时间</th><th>游客问题</th><th>数字人回答</th><th>情绪</th></tr>
      {% for r in report.recent_logs %}
      <tr><td>{{ r.time }}</td><td>{{ r.user_input }}</td><td>{{ r.bot_response }}</td><td>{{ r.emotion }}</td></tr>
      {% endfor %}
    </table>
  </section>
</div>
</body>
</html>
""", files=files, faqs=faqs, report=report, avatar=avatar_config)


@app.route("/avatar/config")
def avatar_config_api():
    return jsonify(load_avatar_config())


@app.route("/admin/avatar/config", methods=["POST"])
def admin_update_avatar_config():
    current = load_avatar_config()
    config = {
        "display_name": request.form.get("display_name", current["display_name"]),
        "role_name": request.form.get("role_name", current["role_name"]),
        "appearance": request.form.get("appearance", current["appearance"]),
        "costume": request.form.get("costume", current["costume"]),
        "cultural_style": request.form.get("cultural_style", current["cultural_style"]),
        "theme_color": request.form.get("theme_color", current["theme_color"]),
        "voice_name": request.form.get("voice_name", current["voice_name"]),
        "voice_sid": request.form.get("voice_sid", current["voice_sid"]),
        "voice_speed": request.form.get("voice_speed", current["voice_speed"]),
        "idle_video": admin_save_avatar_upload("idle", current["idle_video"]),
        "speaking_video": admin_save_avatar_upload("speaking", current["speaking_video"]),
        "thinking_video": admin_save_avatar_upload("thinking", current["thinking_video"]),
    }
    save_avatar_config(config)
    return redirect(url_for("admin_index"))


@app.route("/admin/knowledge/upload", methods=["POST"])
def admin_upload_knowledge():
    file = request.files.get("file")
    if not file or not file.filename:
        return redirect(url_for("admin_index"))
    filename = admin_safe_filename(file.filename)
    ext = os.path.splitext(filename)[1].lower()
    if ext not in ALLOWED_KNOWLEDGE_EXTENSIONS:
        return redirect(url_for("admin_index"))
    file.save(os.path.join(ADMIN_KNOWLEDGE_DIR, filename))
    admin_refresh_knowledge_chunks()
    return redirect(url_for("admin_index"))


@app.route("/admin/knowledge/delete/<path:filename>", methods=["POST"])
def admin_delete_knowledge(filename):
    filename = admin_safe_filename(filename)
    path = os.path.abspath(os.path.join(ADMIN_KNOWLEDGE_DIR, filename))
    if path.startswith(os.path.abspath(ADMIN_KNOWLEDGE_DIR)) and os.path.exists(path):
        os.remove(path)
        admin_refresh_knowledge_chunks()
    return redirect(url_for("admin_index"))


@app.route("/admin/knowledge/rebuild", methods=["POST"])
def admin_rebuild_knowledge():
    admin_refresh_knowledge_chunks()
    return redirect(url_for("admin_index"))


@app.route("/admin/knowledge/search")
def admin_search_knowledge():
    query = (request.args.get("q") or "").strip()
    top_k = request.args.get("top_k", "8")
    try:
        top_k = min(20, max(1, int(top_k)))
    except Exception:
        top_k = 8
    docs = kb.search(query, top_k=top_k) if query else []
    return jsonify({
        "query": query,
        "total_chunks": len(getattr(kb, "chunks", [])),
        "admin_chunks": sum(1 for c in getattr(kb, "chunks", []) if c.startswith("【后台知识】")),
        "hits": docs,
    })


@app.route("/admin/faq/add", methods=["POST"])
def admin_add_faq():
    question = (request.form.get("question") or "").strip()
    answer = (request.form.get("answer") or "").strip()
    if question and answer:
        faqs = admin_load_faqs()
        faqs.append({"question": question, "answer": answer, "time": time.strftime("%Y-%m-%d %H:%M:%S")})
        admin_save_faqs(faqs)
    return redirect(url_for("admin_index"))


@app.route("/admin/faq/delete/<int:index>", methods=["POST"])
def admin_delete_faq(index):
    faqs = admin_load_faqs()
    if 0 <= index < len(faqs):
        faqs.pop(index)
        admin_save_faqs(faqs)
    return redirect(url_for("admin_index"))


# =========================================================================
# 前端 UI（多图层独立常驻预载 + 振幅平滑防抖内核）
# =========================================================================
@app.route("/")
def index():
    return render_template_string("""
<!DOCTYPE html>
<html>
<head>
<meta charset="utf-8">
<title>灵山胜境AI数字人导游</title>
<style>
body { margin:0; font-family:Arial; background:#f4f6f9; }
.container { display:flex; height:100vh; }
.left { width:25%; background:#1e1e2f; color:white; padding:20px; box-sizing: border-box; display: flex; flex-direction: column; }
.center { width:55%; padding:20px; display: flex; flex-direction: column; box-sizing: border-box; }
.right { width:20%; background:white; padding:14px; box-sizing: border-box; border-left: 1px solid #e0e0e0; overflow-y: auto; }

.chat-box { 
    flex: 1; 
    overflow-y:auto; 
    background:white; 
    padding:20px; 
    border: 1px solid #ddd; 
    border-radius: 8px; 
    margin-bottom: 15px; 
    font-size: 16px;
}

.msg-user { 
    text-align:right; 
    color:#1a73e8; 
    margin:16px 10px; 
    font-weight: bold; 
    line-height: 1.9;
    font-size: 16px;
}

.msg-bot { 
    text-align:left; 
    color:#2e7d32; 
    margin:16px 10px; 
    line-height: 1.9; 
    font-size: 16px;
}
.input-area { display: flex; gap: 10px; }
input { flex: 1; padding:12px; border: 1px solid #ccc; border-radius: 4px; font-size: 14px; }
button { padding:12px 24px; background: #1a73e8; color: white; border: none; border-radius: 4px; cursor: pointer; font-size: 14px; }
pre { background: #f8f9fa; padding: 10px; border-radius: 4px; font-family: Consolas, monospace; white-space: pre-wrap; }
.avatar-container { width: 100%; text-align: center; margin-top: 20px; position: relative; min-height: 380px; }
.avatar-video { width: 100%; max-height: 380px; object-fit: cover; border-radius: 12px; border: 3px solid #3f3f5f; background: #151522; position: absolute; top: 0; left: 0; }
.persona-card { background: rgba(255,255,255,0.08); border: 1px solid rgba(255,255,255,0.12); border-radius: 8px; padding: 10px; margin-top: 14px; color: #ddd; font-size: 13px; line-height: 1.7; }
.persona-card b { color: #fff; }
</style>
</head>

<body>
<div class="container">
<div class="left">
<h2 id="avatar-title">😉 AI数字人导游</h2>
<p>互动状态：<span style="color:#4caf50;">● 在线智能导览</span></p>
<p id="emotion">驱动状态：待机 (neutral)</p>
<hr style="border-color: #333;">
<div class="persona-card">
    <b id="avatar-role">灵山小导游</b>
    <div id="avatar-costume">服装：禅意素雅服装</div>
    <div id="avatar-style">风格：温和、专业、富有景区文化气质</div>
    <div id="avatar-voice">声音：清亮亲和导游音</div>
</div>

<div class="avatar-container">
    <video id="avatar-idle" class="avatar-video" autoplay loop muted playsinline style="display: block;">
        <source src="/assets/avatar_idle.mp4" type="video/mp4">
    </video>
    <video id="avatar-speaking" class="avatar-video" autoplay loop muted playsinline style="display: none;">
        <source src="/assets/avatar_speaking.mp4" type="video/mp4">
    </video>
    <video id="avatar-thinking" class="avatar-video" autoplay loop muted playsinline style="display: none;">
        <source src="/assets/avatar_thinking.mp4" type="video/mp4">
    </video>
    <video id="avatar-cache" class="avatar-video" playsinline style="display: none;"></video>

    <audio id="audio-player" style="display:none;"></audio>
</div>

<small style="color:#aaa; margin-top: auto; padding-top: 15px;">核心架构：多图层隐藏式预载。拒绝高频重载src，画面完美丝滑，配合语音消隐防抖。</small>
</div>

<div class="center">
<div class="chat-box" id="chat"></div>
<div class="input-area">
    <input id="text" placeholder="请输入您想了解的景点问题..." onkeydown="if(event.keyCode==13) send()">
    <button onclick="send()">发送问询</button>
</div>
</div>

<div class="right">
<h3>📍 智能推荐游览路线</h3><pre id="route">等待生成...</pre>
<h3>🫶 游客多模态情感分析</h3><pre id="emo">等待分析...</pre>
<h3>📚 知识库召回</h3><pre id="knowledge">等待检索...</pre>
<h3>⏱ 系统响应延迟 (SLO)</h3><pre id="time">0.00s</pre>
</div>
</div>

<script>
let audioCtx = null;
let analyser = null;
let source = null;
let animationId = null;
let silenceTimer = 0;    // 语音平滑消隐计时器，防止字间停顿导致口型剧烈闪烁
let audioQueue = [];
let isPlayingAudio = false;
let currentBotMsg = null;
let avatarConfig = {};

function setVideoSource(videoId, filename) {
    if (!filename) return;
    let video = document.getElementById(videoId);
    let sourceEl = video.querySelector("source");
    let src = "/assets/" + filename + "?t=" + new Date().getTime();
    if (sourceEl) {
        sourceEl.src = src;
        sourceEl.type = filename.endsWith(".webm") ? "video/webm" : "video/mp4";
    } else {
        video.src = src;
    }
    video.load();
    video.play().catch(e => console.log(e));
}

function applyAvatarConfig(config) {
    avatarConfig = config || {};
    document.getElementById("avatar-title").innerText = avatarConfig.display_name || "AI数字人导游";
    document.getElementById("avatar-role").innerText = avatarConfig.role_name || "灵山小导游";
    document.getElementById("avatar-costume").innerText = "服装：" + (avatarConfig.costume || "禅意素雅服装");
    document.getElementById("avatar-style").innerText = "风格：" + (avatarConfig.cultural_style || "温和、专业、富有景区文化气质");
    document.getElementById("avatar-voice").innerText = "声音：" + (avatarConfig.voice_name || "清亮亲和导游音");

    let theme = avatarConfig.theme_color || "#1a73e8";
    document.querySelectorAll("button").forEach(btn => btn.style.background = theme);
    document.querySelectorAll(".avatar-video").forEach(video => video.style.borderColor = theme);

    setVideoSource("avatar-idle", avatarConfig.idle_video);
    setVideoSource("avatar-speaking", avatarConfig.speaking_video);
    setVideoSource("avatar-thinking", avatarConfig.thinking_video);
}

function loadAvatarConfig() {
    fetch("/avatar/config")
    .then(r => r.json())
    .then(applyAvatarConfig)
    .catch(e => console.log(e));
}

function initAudioAnalyser() {
    if (!audioCtx) {
        audioCtx = new (window.AudioContext || window.webkitAudioContext)();
        analyser = audioCtx.createAnalyser();
        analyser.fftSize = 256;
        let audioEl = document.getElementById("audio-player");
        source = audioCtx.createMediaElementSource(audioEl);
        source.connect(analyser);
        analyser.connect(audioCtx.destination);
    }
}

// 📲 无缝状态机：通过操作隐藏/显示，彻底消灭重载卡顿
function switchAvatarLayer(activeState) {
    let idleV = document.getElementById("avatar-idle");
    let speakV = document.getElementById("avatar-speaking");
    let thinkV = document.getElementById("avatar-thinking");
    let cacheV = document.getElementById("avatar-cache");

    idleV.style.display = activeState === "idle" ? "block" : "none";
    speakV.style.display = activeState === "speaking" ? "block" : "none";
    thinkV.style.display = activeState === "thinking" ? "block" : "none";
    cacheV.style.display = activeState === "cache" ? "block" : "none";

    if (activeState !== "cache") { cacheV.pause(); }
}

function monitorAmplitude() {
    let audioPlayer = document.getElementById("audio-player");
    let bufferLength = analyser.frequencyBinCount;
    let dataArray = new Uint8Array(bufferLength);

    function check() {
        if (audioPlayer.paused || audioPlayer.ended) {
            cancelAnimationFrame(animationId);
            return;
        }
        analyser.getByteFrequencyData(dataArray);
        let sum = 0;
        for (let i = 0; i < bufferLength; i++) { sum += dataArray[i]; }
        let average = sum / bufferLength;

        if (average > 12) { 
            // 只要有声音，立刻归零计时器并保持张嘴
            silenceTimer = 0;
            switchAvatarLayer("speaking");
        } else {
            silenceTimer++;
            // 只有当持续静音超过 18 帧(约 350ms)时，才判定为一句话讲完了，切换回闭嘴待机
            if (silenceTimer > 18) {
                switchAvatarLayer("idle");
            }
        }
        animationId = requestAnimationFrame(check);
    }
    check();
}
                                  
function send(){
    let inputEl = document.getElementById("text");
    let text = inputEl.value.trim();
    if(!text) return;

    if(window.AudioContext || window.webkitAudioContext) { initAudioAnalyser(); if(audioCtx) audioCtx.resume(); }

    document.getElementById("chat").innerHTML += "<div class='msg-user'>你：" + text + "</div>";
    inputEl.value = "";
    let chatBox = document.getElementById("chat");
    chatBox.scrollTop = chatBox.scrollHeight;

    let audioPlayer = document.getElementById("audio-player");
    let cacheVideo = document.getElementById("avatar-cache");

    cancelAnimationFrame(animationId);
    // 瞬间无感知切到思考状态
    switchAvatarLayer("thinking");
    document.getElementById("emotion").innerText = "驱动状态: 思考中 (thinking...)";

    fetch("/chat",{
        method:"POST",
        headers:{"Content-Type":"application/json"},
        body:JSON.stringify({text:text})
    })
    .then(r=>r.json())
    .then(d=>{
        document.getElementById("chat").innerHTML += "<div class='msg-bot'>Guide: " + d.answer + "</div>";
        chatBox.scrollTop = chatBox.scrollHeight;

        document.getElementById("route").innerText = JSON.stringify(d.route, null, 2);
        document.getElementById("emo").innerText = JSON.stringify(d.emotion, null, 2);
        document.getElementById("knowledge").innerText = JSON.stringify(d.knowledge_source || {}, null, 2);
        document.getElementById("time").innerText = d.cost_time + "s";

        cacheVideo.onended = null;
        audioPlayer.onended = null;

        if (d.mode === "cache") {
            // 模式 A：黄金高频展示题 -> 唤醒常驻的完美 Wav2Lip 对齐独立图层
            document.getElementById("emotion").innerText = "驱动状态: 高清精细嘴型播报 (cache)";
            switchAvatarLayer("cache");
            cacheVideo.src = "/assets/" + d.video_file + "?t=" + new Date().getTime();
            cacheVideo.loop = false;
            cacheVideo.muted = false;
            cacheVideo.load();
            cacheVideo.play().catch(e => console.log(e));

            cacheVideo.onended = function() {
                switchAvatarLayer("idle");
                document.getElementById("emotion").innerText = "驱动状态: 待机 (neutral)";
            };
        } else {
            // 模式 B：随机应变题 -> 采用 VITS 音频 + 前端高速振幅无感图层咬合机制
            document.getElementById("emotion").innerText = "驱动状态: 极速振幅联动播报 (vits)";
            audioPlayer.src = "/assets/" + d.audio_file + "?t=" + new Date().getTime();
            audioPlayer.load();

            audioPlayer.oncanplaythrough = function() {
                let speakingVideo = document.getElementById("avatar-speaking");
                speakingVideo.currentTime = 0;
                speakingVideo.play().catch(e => console.log(e));
                audioPlayer.play().catch(e => console.log(e));
                silenceTimer = 0;
                monitorAmplitude();
            };

            audioPlayer.onended = function() {
                cancelAnimationFrame(animationId);
                switchAvatarLayer("idle");
                document.getElementById("emotion").innerText = "驱动状态: 待机 (neutral)";
            };
        }
    })
    .catch(err => {
        switchAvatarLayer("idle");
    });
}

loadAvatarConfig();
</script>
</body>
</html>
""")


# =========================================================================
# chat核心接口（混合双通道调度机制）
# =========================================================================
@app.route("/chat", methods=["POST"])
def chat_api():
    try:
        data = request.json or {}
        q = (data.get("text") or "").strip()
        start = time.time()

         # 1. 先查缓存
        cached = find_cached_reply(q)

        if cached:
            lipsync_video = get_cached_lipsync_video(cached)
            if lipsync_video:
                try:
                    save_chat(q, cached["answer"], "neutral", "cache")
                except Exception as log_err:
                    print(f"[admin] save chat failed: {log_err}")
                return jsonify({
                    "mode": "cache",
                    "answer": cached["answer"],
                    "video_file": lipsync_video,
                    "route": ["cache"],
                    "emotion": {"state": "neutral", "source": "cache"},
                    "cost_time": round(time.time() - start, 2)
                })

            try:
                save_chat(q, cached["answer"], "neutral", "cache")
            except Exception as log_err:
                print(f"[admin] save chat failed: {log_err}")
            return jsonify({
                "mode": "vits",
                "answer": cached["answer"],
                "audio_file": cached.get("audio_file", ""),
                "route": ["cache"],
                "emotion": {"state": "neutral", "source": "cache"},
                "cost_time": round(time.time() - start, 2),
                "warning": "No lipsync video was found or generated for this cached audio."
            })



        if not q:
            return jsonify({"answer": "您好，有什么我可以帮您的吗？", "route": [], "mode": "vits"})

        faq_item = admin_find_faq_reply(q)
        knowledge_source = {"admin_hit": False, "hit_count": 0}
        if faq_item:
            route = ["后台FAQ"]
            emo = {"emotion": "neutral", "source": "admin_faq"}
            answer = faq_item["answer"]
            interest = "admin_faq"
            knowledge_source = {"admin_hit": True, "hit_count": 1, "source": "admin_faq"}
        else:
            # 1️⃣ RAG知识库检索与大模型推理
            try:
                r = get_route(q); route = r["route"] if isinstance(r, dict) else r
            except:
                route = ["灵山大佛", "九龙灌浴", "梵宫"]
            try:
                emo = analyze(q)
            except:
                emo = {"emotion": "neutral"}

            try:
                answer = chat_session.ask(q)
            except Exception as e:
                answer = "欢迎来到灵山胜境！请近距离感受大佛的庄严与震撼。祝您旅途愉快！"
            docs = getattr(chat_session, "last_docs", [])
            knowledge_source = {
                "admin_hit": any(d.startswith("【后台知识】") for d in docs),
                "hit_count": len(docs),
                "preview": docs[:2],
            }
            interest = ""


        # 3️⃣ 实时兜底通道：实时生成 VITS 音频，前端通过振幅驱动常驻图层无缝显隐
        print("[实时计算] 未匹配缓存。利用纯离线VITS + 前端平滑防抖图层跟随。")
        emotion_value = emo.get("emotion", "neutral") if isinstance(emo, dict) else str(emo)
        try:
            save_chat(q, answer, emotion_value, interest)
        except Exception as log_err:
            print(f"[admin] save chat failed: {log_err}")

        audio_filename = f"reply_{int(time.time())}.wav"
        generated_file = generate_cloned_tts(answer, audio_filename)
        lipsync_file = generate_lipsync_video(generated_file)

        if lipsync_file:
            return jsonify(safe({
                "answer": answer, "route": route, "emotion": emo,
                "video_file": lipsync_file,
                "mode": "cache",
                "knowledge_source": knowledge_source,
                "cost_time": round(time.time() - start, 2)
            }))

        return jsonify(safe({
            "answer": answer, "route": route, "emotion": emo,
            "audio_file": generated_file,
            "mode": "vits",
            "knowledge_source": knowledge_source,
            "cost_time": round(time.time() - start, 2)
        }))
    except Exception as e:
        return jsonify({"answer": "系统后台升级中...", "route": [], "audio_file": "", "mode": "vits", "cost_time": 0})

    
def chat_stream_sentence(query: str, context: str = ""):
    """LLM流式输出，并按句子切分，适合实时TTS"""
    formatted_context = context.strip() if context else "暂无直接匹配的景区基础资料。"
    user_content = f"【景区权威资料】\n{formatted_context}\n\n【游客当前提问】\n{query}"

    buffer = ""

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
                piece = chunk.choices[0].delta.content
                buffer += piece

                if any(p in buffer for p in ["。", "！", "？", "；"]):
                    sentence = buffer.strip()
                    buffer = ""
                    if sentence:
                        yield sentence

        if buffer.strip():
            yield buffer.strip()

    except Exception as e:
        print(f"LLM流式调用异常: {e}")
        yield "系统正在连接中，请稍候。"

    except Exception as e:
        return jsonify({"answer": "系统后台升级中...", "route": [], "audio_file": "", "mode": "vits", "cost_time": 0})

admin_refresh_knowledge_chunks()


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000, debug=True, use_reloader=False)
