import shutil
import tempfile
from pathlib import Path
from typing import Optional

from core import (
    clone_voice,
    delete_conversation,
    generate_llm_response,
    list_conversations,
    list_saved_voices,
    load_conversation_messages,
    load_history,
    new_conversation_id,
    next_message_id,
    save_conversation_messages,
    save_history,
    synthesize,
)
from fastapi import FastAPI, File, Form, HTTPException, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

app = FastAPI(title="Gemma Voice Chatbot")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


class ChatRequest(BaseModel):
    username: str
    message: str
    conversation_id: Optional[str] = None


class SpeakRequest(BaseModel):
    username: str
    message_id: int
    display_name: str
    conversation_id: Optional[str] = None


class HistoryRequest(BaseModel):
    username: str
    conversation_id: Optional[str] = None


class NewConversationRequest(BaseModel):
    username: str


@app.get("/")
def root():
    return {"status": "running"}


@app.get("/conversations")
def get_conversations(username: str):
    return {"conversations": list_conversations(username)}


@app.post("/new-conversation")
def create_new_conversation(req: NewConversationRequest):
    conv_id = new_conversation_id()
    return {"conversation_id": conv_id}


@app.post("/chat")
def chat(req: ChatRequest):
    conv_id = req.conversation_id or new_conversation_id()
    history = load_conversation_messages(req.username, conv_id)
    user_id = next_message_id(history)
    history.append({"id": user_id, "role": "user", "content": req.message})
    answer = generate_llm_response(history)
    assistant_id = next_message_id(history)
    history.append({"id": assistant_id, "role": "assistant", "content": answer})
    save_conversation_messages(req.username, conv_id, history)
    return {"response": answer, "message_id": assistant_id, "conversation_id": conv_id}


@app.post("/history")
def history(req: HistoryRequest):
    if req.conversation_id:
        msgs = load_conversation_messages(req.username, req.conversation_id)
    else:
        msgs = load_history(req.username)
    return {"history": msgs}


@app.post("/speak")
def speak(req: SpeakRequest):
    if req.conversation_id:
        history = load_conversation_messages(req.username, req.conversation_id)
    else:
        history = load_history(req.username)

    target = None
    for msg in history:
        if msg["id"] == req.message_id and msg["role"] == "assistant":
            target = msg
            break

    if target is None:
        raise HTTPException(status_code=404, detail="Message not found")

    audio_path = synthesize(
        username=req.username, display_name=req.display_name, text=target["content"]
    )
    return {"audio_file": audio_path}


@app.delete("/history/{username}")
def clear_history(username: str):
    save_history(username, [])
    return {"status": "cleared"}


@app.delete("/conversations/{username}/{conversation_id}")
def remove_conversation(username: str, conversation_id: str):
    delete_conversation(username, conversation_id)
    return {"status": "deleted"}


@app.get("/voices")
def get_voices(username: str):
    return list_saved_voices(username)


@app.post("/select-voices")
def get_saved_voices(
    username: str = Form(...),
):
    return {"voices": list_saved_voices(username)}


@app.post("/clone-voice")
def clone_voice_api(
    audio: UploadFile = File(...),
    display_name: str = Form(...),
    username: str = Form(...),
    transcription: str = Form(...),
    lang_code: str = Form("EN_US"),
):
    temp_audio_path = None

    try:
        suffix = Path(audio.filename).suffix or ".wav"

        with tempfile.NamedTemporaryFile(
            delete=False,
            suffix=suffix,
        ) as tmp_file:
            shutil.copyfileobj(audio.file, tmp_file)
            temp_audio_path = tmp_file.name

        voice_id = clone_voice(
            audio_file=temp_audio_path,
            username=username,
            display_name=display_name,
            transcription=transcription,
            lang_code=lang_code,
        )

        return {
            "success": True,
            "voice_id": voice_id,
            "display_name": display_name,
        }

    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=str(e),
        )

    finally:
        if temp_audio_path and Path(temp_audio_path).exists():
            Path(temp_audio_path).unlink(missing_ok=True)


if __name__ == "__main__":

    import uvicorn

    uvicorn.run(app, host="0.0.0.0", port=8970)
