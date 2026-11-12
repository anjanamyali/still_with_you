import base64
import hashlib
import json
import os
import shutil
from datetime import datetime, timezone
from pathlib import Path

import requests
from configs import GEMINI_API_KEY, GEMINI_MODEL, INWORLDTTS_API_KEY
from google import genai

client = genai.Client(api_key=GEMINI_API_KEY)

DATA_DIR = Path(__file__).parent.parent / "data"
DATA_DIR.mkdir(exist_ok=True)


def get_user_dir(username: str):

    user_dir = DATA_DIR / "history" / username
    audio_dir = user_dir / "audio"
    vocies_dir = user_dir / "voices"

    user_dir.mkdir(exist_ok=True)
    audio_dir.mkdir(exist_ok=True)
    vocies_dir.mkdir(exist_ok=True)

    return user_dir, audio_dir, vocies_dir


def history_file(username: str):
    user_dir, audio_dir, vocies_dir = get_user_dir(username)
    return user_dir / "history.json"


def voices_file(username: str, display_name: str):
    user_dir, audio_dir, vocies_dir = get_user_dir(username)
    return vocies_dir / (display_name + ".wav"), vocies_dir / (display_name + ".json")


def list_saved_voices(username: str):
    user_dir, audio_dir, vocies_dir = get_user_dir(username)
    voices = []
    for json_file in sorted(vocies_dir.glob("*.json")):
        try:
            voice_info = json.loads(json_file.read_text())
            audio_file = json_file.with_suffix(".wav")
            voices.append(
                {
                    "display_name": voice_info.get("display_name", json_file.stem),
                    "audio_path": str(audio_file) if audio_file.exists() else None,
                    "transcript": voice_info.get("transcript", ""),
                    "voice_id": voice_info.get("voice_id"),
                }
            )
        except Exception:
            continue
    return voices


def load_history(username: str):

    file_path = history_file(username)

    if not file_path.exists():
        return []

    try:
        with open(file_path, "r", encoding="utf-8") as f:
            return json.load(f)

    except Exception:
        return []


def save_history(username: str, history):

    file_path = history_file(username)

    with open(file_path, "w", encoding="utf-8") as f:
        json.dump(history, f, indent=4, ensure_ascii=False)


def next_message_id(history):

    if not history:
        return 1

    return max(item["id"] for item in history) + 1


def generate_llm_response(history):

    contents = []
    system_instruction = """
You are a supportive, empathetic, and thoughtful therapist-like conversational assistant.

Guidelines:
- Respond in a warm, calm, and non-judgmental manner.
- Keep responses short and concise (1–4 sentences unless more detail is requested).
- Focus on understanding the user's feelings, thoughts, and experiences.
- Ask at most one gentle follow-up question when it helps the conversation.
- Avoid giving long lectures, excessive advice, or multiple suggestions at once.
- Encourage reflection rather than telling the user what to do.
- Validate emotions without making assumptions.
- Maintain a conversational, human-like tone.
- Do not diagnose mental health conditions or claim to be a licensed therapist.
- If the user expresses risk of self-harm, suicide, or harm to others, encourage them to seek immediate professional or emergency support.
- Keep every response under 50 words unless the user explicitly asks for more detail.

Style examples:
User: "I've been feeling overwhelmed lately."
Assistant: "That sounds exhausting. What's been weighing on you the most?"

User: "I think I failed."
Assistant: "It sounds like you're being hard on yourself. What happened?"

User: "I'm anxious about tomorrow."
Assistant: "Anticipation can feel really heavy. What's the part you're most worried about?"
"""

    for msg in history:

        role = "model" if msg["role"] == "assistant" else "user"

        contents.append({"role": role, "parts": [{"text": msg["content"]}]})

    config = {"system_instruction": system_instruction} if system_instruction else None

    response = client.models.generate_content(
        model=GEMINI_MODEL, contents=contents, config=config
    )

    return response.text


def clone_voice(
    audio_file: Path,
    username: str,
    display_name: str,
    transcription: str,
    lang_code: str = "EN_US",
    api_key: str = INWORLDTTS_API_KEY,
) -> str:
    """
    Clone a voice and return voice_id.
    """

    audio_save_path, json_save_path = voices_file(username, display_name)
    metadata_save_path = json_save_path

    if metadata_save_path.exists():
        voice_info = json.loads(metadata_save_path.read_text())
        voice_id = voice_info.get("voice_id")

        if voice_id:
            return voice_id

    shutil.copy2(src=audio_file, dst=audio_save_path)

    headers = {
        "Authorization": f"Basic {api_key}",
        "Content-Type": "application/json",
    }

    with open(audio_file, "rb") as f:
        audio_b64 = base64.b64encode(f.read()).decode("utf-8")

    payload = {
        "displayName": display_name,
        "langCode": lang_code,
        "voiceSamples": [
            {
                "audioData": audio_b64,
                # API currently expects transcription
                "transcription": transcription,
            }
        ],
        "description": "",
        "tags": [],
        "audioProcessingConfig": {"removeBackgroundNoise": True},
    }

    r = requests.post(
        "https://api.inworld.ai/voices/v1/voices:clone",
        headers=headers,
        json=payload,
        timeout=300,
    )

    r.raise_for_status()

    data = r.json()
    voice_id = data["voice"]["voiceId"]

    if metadata_save_path.exists():
        voice_info = json.loads(metadata_save_path.read_text())
    else:
        voice_info = {
            "display_name": display_name,
            "audio_file": audio_file,
            "transcript": transcription,
        }

    voice_info["voice_id"] = voice_id
    metadata_save_path.write_text(json.dumps(voice_info, indent=2))

    return voice_id


def conversations_dir(username: str) -> Path:
    user_dir, _, _ = get_user_dir(username)
    conv_dir = user_dir / "conversations"
    conv_dir.mkdir(exist_ok=True)
    return conv_dir


def new_conversation_id() -> str:
    return datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S_%f")


def list_conversations(username: str) -> list:
    conv_dir = conversations_dir(username)
    convs = []
    for f in sorted(conv_dir.glob("*.json"), reverse=True):
        try:
            data = json.loads(f.read_text(encoding="utf-8"))
            messages = data.get("messages", [])
            if not messages:
                continue
            convs.append(
                {
                    "id": data["id"],
                    "title": data.get("title", "Untitled"),
                    "created_at": data.get("created_at", ""),
                    "message_count": len(messages),
                }
            )
        except Exception:
            continue
    return convs


def load_conversation_messages(username: str, conversation_id: str) -> list:
    conv_dir = conversations_dir(username)
    f = conv_dir / f"{conversation_id}.json"
    if not f.exists():
        return []
    try:
        data = json.loads(f.read_text(encoding="utf-8"))
        return data.get("messages", [])
    except Exception:
        return []


def save_conversation_messages(username: str, conversation_id: str, messages: list):
    conv_dir = conversations_dir(username)
    f = conv_dir / f"{conversation_id}.json"

    if f.exists():
        data = json.loads(f.read_text(encoding="utf-8"))
    else:
        data = {
            "id": conversation_id,
            "created_at": datetime.now(timezone.utc).isoformat(),
            "title": "New Conversation",
        }

    if data.get("title") in ("New Conversation", None, ""):
        for msg in messages:
            if msg["role"] == "user":
                data["title"] = msg["content"][:60]
                break

    data["messages"] = messages
    data["updated_at"] = datetime.now(timezone.utc).isoformat()
    f.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")


def delete_conversation(username: str, conversation_id: str):
    conv_dir = conversations_dir(username)
    f = conv_dir / f"{conversation_id}.json"
    if f.exists():
        f.unlink()


def text_hash(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def synthesize(
    username: str,
    display_name: str,
    text: str,
    api_key: str = INWORLDTTS_API_KEY,
    model_id: str = "inworld-tts-1.5-mini",
    sample_rate: int = 22050,
) -> str:
    """
    Generate speech for the given text using the cloned voice.
    Cached by voice_id + text hash. Returns path to WAV file.
    """

    user_dir, audio_dir, vocies_dir = get_user_dir(username)
    audio_save_path, json_save_path = voices_file(username, display_name)
    voice_id = json.loads(json_save_path.read_text())["voice_id"]

    tts_save_path = audio_dir / display_name / (text_hash(text) + ".wav")
    tts_json_save_path = audio_dir / display_name / (text_hash(text) + ".json")

    tts_save_path.parent.mkdir(exist_ok=True, parents=True)

    if tts_save_path.exists():
        return str(tts_save_path)

    headers = {
        "Authorization": f"Basic {api_key}",
        "Content-Type": "application/json",
    }

    payload = {
        "text": text,
        "voiceId": voice_id,
        "modelId": model_id,
        "audioConfig": {
            "audioEncoding": "LINEAR16",
            "sampleRateHertz": sample_rate,
        },
        "deliveryMode": "BALANCED",
        "applyTextNormalization": "ON",
    }

    r = requests.post(
        "https://api.inworld.ai/tts/v1/voice",
        headers=headers,
        json=payload,
        timeout=300,
    )

    r.raise_for_status()
    data = r.json()
    wav_bytes = base64.b64decode(data["audioContent"])
    tts_save_path.write_bytes(wav_bytes)

    meta = {
        "text": text,
        "voice_id": voice_id,
        "usage": data.get("usage", {}),
    }

    tts_json_save_path.write_text(json.dumps(meta, indent=2))
    return str(tts_save_path)
