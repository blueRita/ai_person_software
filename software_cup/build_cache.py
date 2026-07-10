import argparse
import asyncio
import json
import os
import requests
import subprocess
import sys
import types


BASE_DIR = os.path.dirname(os.path.abspath(__file__))
ASSETS_DIR = os.path.join(BASE_DIR, "assets")
MANIFEST_PATH = os.path.join(BASE_DIR, "cache_manifest.json")
LIPSYNC_DIR = os.path.join(BASE_DIR, "LipSync")
WAV2LIP_CHECKPOINT = os.path.join(LIPSYNC_DIR, "checkpoints", "wav2lip_gan.pth")
AVATAR_FACE_VIDEO = os.path.join(ASSETS_DIR, "avatar_idle.mp4")
VITS_MODEL_DIR = os.path.abspath(os.path.join(BASE_DIR, "..", "vits-zh-hf-fanchen-C"))
_offline_vits_engine = None


def load_manifest():
    with open(MANIFEST_PATH, "r", encoding="utf-8") as f:
        return json.load(f)


def generate_vits_tts(text, output_file):
    global _offline_vits_engine
    try:
        import sherpa_onnx
        import soundfile as sf

        if _offline_vits_engine is None:
            tts_config = sherpa_onnx.OfflineTtsConfig(
                model=sherpa_onnx.OfflineTtsModelConfig(
                    vits=sherpa_onnx.OfflineTtsVitsModelConfig(
                        model=os.path.join(VITS_MODEL_DIR, "vits-zh-hf-fanchen-C.onnx"),
                        lexicon=os.path.join(VITS_MODEL_DIR, "lexicon.txt"),
                        tokens=os.path.join(VITS_MODEL_DIR, "tokens.txt"),
                        data_dir=os.path.join(VITS_MODEL_DIR, "espeak-ng-data")
                        if os.path.exists(os.path.join(VITS_MODEL_DIR, "espeak-ng-data"))
                        else "",
                    ),
                    num_threads=4,
                    debug=False,
                )
            )
            _offline_vits_engine = sherpa_onnx.OfflineTts(tts_config)

        output_path = os.path.join(ASSETS_DIR, output_file)
        audio = _offline_vits_engine.generate(text, sid=12, speed=1.05)
        sf.write(output_path, audio.samples, samplerate=audio.sample_rate)
        return output_file
    except Exception as e:
        print(f"[tts] local VITS failed: {e}")
        return None


def generate_cache_tts(text, cache_id):
    sovits_api_url = "http://127.0.0.1:9880"
    wav_file = f"cache_{cache_id}.wav"
    wav_path = os.path.join(ASSETS_DIR, wav_file)
    payload = {
        "text": text,
        "text_language": "zh",
        "ref_audio_path": "vocal_seed.wav",
        "prompt_text": "小和尚原话",
        "prompt_language": "zh",
    }
    try:
        response = requests.post(sovits_api_url, json=payload, timeout=1.0)
        if response.status_code == 200:
            with open(wav_path, "wb") as f:
                f.write(response.content)
            return wav_file
    except Exception:
        pass

    vits_file = generate_vits_tts(text, wav_file)
    if vits_file:
        return vits_file

    mp3_file = f"cache_{cache_id}.mp3"
    mp3_path = os.path.join(ASSETS_DIR, mp3_file)
    try:
        import edge_tts

        async def make_tts():
            communicate = edge_tts.Communicate(text, "zh-CN-YunxiNeural")
            await communicate.save(mp3_path)

        asyncio.run(make_tts())
        return mp3_file
    except Exception as e:
        print(f"[tts] edge_tts failed: {e}")

    try:
        import comtypes

        gen_dir = os.path.join(BASE_DIR, ".cache", "comtypes_gen")
        os.makedirs(gen_dir, exist_ok=True)
        gen_module = types.ModuleType("comtypes.gen")
        gen_module.__path__ = [gen_dir]
        sys.modules["comtypes.gen"] = gen_module
        comtypes.gen = gen_module

        import pyttsx3

        engine = pyttsx3.init()
        engine.setProperty("rate", 195)
        engine.save_to_file(text, wav_path)
        engine.runAndWait()
        return wav_file
    except Exception as e:
        print(f"[tts] pyttsx3 failed: {e}")
        return None


def generate_cache_lipsync(audio_file, output_file):
    if not os.path.exists(WAV2LIP_CHECKPOINT):
        print(f"[wav2lip] missing checkpoint: {WAV2LIP_CHECKPOINT}")
        return False
    if not os.path.exists(AVATAR_FACE_VIDEO):
        print(f"[wav2lip] missing avatar video: {AVATAR_FACE_VIDEO}")
        return False

    audio_path = os.path.abspath(os.path.join(ASSETS_DIR, audio_file))
    output_path = os.path.abspath(os.path.join(ASSETS_DIR, output_file))

    #####################################################################
    print("[wav2lip] AVATAR_FACE_VIDEO =", AVATAR_FACE_VIDEO)
    print("[wav2lip] face abs path =", os.path.abspath(AVATAR_FACE_VIDEO))
    print("[wav2lip] face exists =", os.path.exists(os.path.abspath(AVATAR_FACE_VIDEO)))
    ########################################################################

    cmd = [
        sys.executable,
        "inference.py",
        "--checkpoint_path",
        os.path.abspath(WAV2LIP_CHECKPOINT),
        "--face",
        os.path.abspath(AVATAR_FACE_VIDEO),
        "--audio",
        audio_path,
        "--outfile",
        output_path,
        # "--resize_factor",
        # "2",
        # "--static",
        # "True",
        # "--nosmooth",
        "--box",
        "198",
        "365",
        "220",
        "457",
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
    except subprocess.TimeoutExpired:
        print("[wav2lip] timed out")
        return False
    if result.returncode != 0:
        print(result.stdout[-4000:])
        return False
    return os.path.exists(output_path)


def build_item(item, force=False):

    cache_id = item["id"]
    answer = item["answer"]
    audio_file = item.get("audio_file", "")
    video_file = item.get("lipsync_video_file") or f"{os.path.splitext(audio_file or cache_id)[0]}_lipsync.mp4"
    video_path = os.path.join(ASSETS_DIR, video_file)

    if os.path.exists(video_path) and not force:
        print(f"[skip] {cache_id}: {video_file} already exists")
        return True

    if audio_file and os.path.exists(os.path.join(ASSETS_DIR, audio_file)):
        generated_audio = audio_file
        print(f"[tts] {cache_id}: using existing {audio_file}")
    else:
        print(f"[tts] {cache_id}: generating audio")
        generated_audio = generate_cache_tts(answer, cache_id)

    if not generated_audio:
        print(f"[fail] {cache_id}: TTS failed")
        return False

    print(f"[wav2lip] {cache_id}: generating lip-sync video")
    if not generate_cache_lipsync(generated_audio, video_file):
        print(f"[fail] {cache_id}: Wav2Lip failed")
        return False

    print(f"[ok] {cache_id}: {video_file}")
    return True


def main():
    parser = argparse.ArgumentParser(description="Build pre-rendered lip-sync cache videos.")
    parser.add_argument("--id", dest="only_id", help="Only build one cache item by id.")
    parser.add_argument("--force", action="store_true", help="Rebuild even if the output mp4 exists.")
    parser.add_argument("--list", action="store_true", help="List cache items and exit.")
    args = parser.parse_args()

    items = load_manifest()
    if args.list:
        for item in items:
            audio_file = item.get("audio_file", "")
            video_file = item.get("lipsync_video_file") or f"{os.path.splitext(audio_file or item['id'])[0]}_lipsync.mp4"
            status = "ready" if os.path.exists(os.path.join(ASSETS_DIR, video_file)) else "missing"
            print(f"{item['id']}: {video_file} ({status})")
        return

    selected = [item for item in items if not args.only_id or item["id"] == args.only_id]
    if not selected:
        print(f"No cache item matched id: {args.only_id}")
        sys.exit(1)

    failed = [item["id"] for item in selected if not build_item(item, force=args.force)]
    if failed:
        print("Failed items: " + ", ".join(failed))
        sys.exit(1)


if __name__ == "__main__":
    main()
