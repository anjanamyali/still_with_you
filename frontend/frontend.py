from pathlib import Path

import gradio as gr
import requests

# =====================================================
# Backend URLs
# =====================================================

BACKEND_URL = "http://localhost:8970"

CHAT_URL = f"{BACKEND_URL}/chat"
HISTORY_URL = f"{BACKEND_URL}/history"
SPEAK_URL = f"{BACKEND_URL}/speak"
CLONE_VOICE_URL = f"{BACKEND_URL}/clone-voice"
VOICES_URL = f"{BACKEND_URL}/voices"
CONVERSATIONS_URL = f"{BACKEND_URL}/conversations"
NEW_CONVERSATION_URL = f"{BACKEND_URL}/new-conversation"

# =====================================================
# Helpers
# =====================================================

PROMPTS = ["""
Life has a funny way of surprising us. Sometimes things go exactly as planned, and other times they take a completely unexpected turn. Over the years, I've learned that growth often comes from those unexpected moments. They challenge us, teach us patience, and help us discover strengths we didn't know we had.
"""]


def _fetch_voices(username: str):
    """Returns (dropdown_choices, table_rows) for the given user."""
    try:
        response = requests.get(VOICES_URL, params={"username": username}, timeout=10)
        response.raise_for_status()
        voices = response.json()
        choices = [v["display_name"] for v in voices]
        table = [[v["display_name"], v.get("transcript", "")] for v in voices]
        return choices, table
    except Exception:
        return [], []


def _fetch_conversations(username: str):
    """Returns list of (label, value) tuples for Radio choices, newest first."""
    try:
        response = requests.get(
            CONVERSATIONS_URL, params={"username": username}, timeout=10
        )
        response.raise_for_status()
        convs = response.json().get("conversations", [])
        choices = []
        for c in convs:
            title = c.get("title") or "Untitled"
            label = title[:45] + ("…" if len(title) > 45 else "")
            choices.append((label, c["id"]))
        return choices
    except Exception:
        return []


# =====================================================
# Load Chat + Voices
# =====================================================


def load_chat_and_voices(username):
    if not username.strip():
        return (
            [],
            None,
            gr.update(choices=[], value=None),
            [],
            gr.update(choices=[], value=None),
            None,
        )

    conv_choices = _fetch_conversations(username)
    messages = []
    latest_assistant_id = None
    active_conv_id = None

    if conv_choices:
        active_conv_id = conv_choices[0][1]
        try:
            response = requests.post(
                HISTORY_URL,
                json={"username": username, "conversation_id": active_conv_id},
            )
            data = response.json()
            for msg in data.get("history", []):
                messages.append({"role": msg["role"], "content": msg["content"]})
                if msg["role"] == "assistant":
                    latest_assistant_id = msg["id"]
        except Exception as e:
            messages = [{"role": "assistant", "content": f"Error loading chat: {e}"}]

    choices, table = _fetch_voices(username)
    voice_update = gr.update(choices=choices, value=choices[0] if choices else None)
    conv_update = gr.update(choices=conv_choices, value=active_conv_id)

    return (
        messages,
        latest_assistant_id,
        voice_update,
        table,
        conv_update,
        active_conv_id,
    )


# =====================================================
# Refresh Voices
# =====================================================


def refresh_voices(username):
    if not username.strip():
        return gr.update(choices=[], value=None), []
    choices, table = _fetch_voices(username)
    return gr.update(choices=choices, value=choices[0] if choices else None), table


# =====================================================
# Conversation Management
# =====================================================


def select_conversation(username, conversation_id):
    """Load a specific conversation into the chatbot."""
    if not username or not conversation_id:
        return [], None, conversation_id

    messages = []
    latest_assistant_id = None

    try:
        response = requests.post(
            HISTORY_URL, json={"username": username, "conversation_id": conversation_id}
        )
        data = response.json()
        for msg in data.get("history", []):
            messages.append({"role": msg["role"], "content": msg["content"]})
            if msg["role"] == "assistant":
                latest_assistant_id = msg["id"]
    except Exception as e:
        messages = [{"role": "assistant", "content": f"Error: {e}"}]

    return messages, latest_assistant_id, conversation_id


def new_chat(username):
    """Reserve a fresh conversation ID without persisting until first message."""
    if not username.strip():
        return [], None, gr.update(value=None), None

    conv_id = None
    try:
        response = requests.post(NEW_CONVERSATION_URL, json={"username": username})
        conv_id = response.json()["conversation_id"]
    except Exception:
        pass

    return [], None, gr.update(value=None), conv_id


# =====================================================
# Send Message
# =====================================================


def send_message(username, message, history, conversation_id):
    if not username.strip():
        history.append({"role": "assistant", "content": "Please enter a username."})
        return history, "", None, gr.update(), conversation_id

    if not message.strip():
        return history, "", None, gr.update(), conversation_id

    try:
        response = requests.post(
            CHAT_URL,
            json={
                "username": username,
                "message": message,
                "conversation_id": conversation_id,
            },
        )
        result = response.json()
        history.append({"role": "user", "content": message})
        history.append({"role": "assistant", "content": result["response"]})
        new_conv_id = result.get("conversation_id", conversation_id)

        conv_choices = _fetch_conversations(username)
        conv_update = gr.update(choices=conv_choices, value=new_conv_id)

        return history, "", result["message_id"], conv_update, new_conv_id
    except Exception as e:
        history.append({"role": "assistant", "content": f"Error: {e}"})
        return history, "", None, gr.update(), conversation_id


# =====================================================
# Listen
# =====================================================


def listen(username, message_id, selected_voice, conversation_id):
    if not username or not message_id:
        return None

    if not selected_voice:
        gr.Warning("Please select a voice first.")
        return None

    try:
        response = requests.post(
            SPEAK_URL,
            json={
                "username": username,
                "message_id": message_id,
                "display_name": selected_voice,
                "conversation_id": conversation_id,
            },
        )
        result = response.json()
        return result["audio_file"]
    except Exception as e:
        print(e)
        return None


# =====================================================
# Clear Chat
# =====================================================


def clear_chat(username, conversation_id):
    if username and conversation_id:
        try:
            requests.delete(
                f"{BACKEND_URL}/conversations/{username}/{conversation_id}", timeout=5
            )
        except Exception:
            pass
    conv_choices = (
        _fetch_conversations(username) if username and username.strip() else []
    )
    conv_update = gr.update(choices=conv_choices, value=None)
    return [], None, None, conv_update, None


# =====================================================
# Upload Voice
# =====================================================


def upload_audio(username, display_name, audio_path, transcript):
    if not username.strip():
        return "Please enter a username first.", []

    if not display_name.strip():
        return "Please enter a voice name.", []

    if audio_path is None:
        return "Please record audio first.", []

    try:
        with open(audio_path, "rb") as f:
            response = requests.post(
                CLONE_VOICE_URL,
                files={"audio": (Path(audio_path).name, f, "audio/wav")},
                data={
                    "username": username,
                    "display_name": display_name,
                    "transcription": transcript,
                },
                timeout=60,
            )
        response.raise_for_status()
        _, table = _fetch_voices(username)
        return "Upload successful!", table
    except Exception as e:
        return f"Upload failed: {e}", []


# =====================================================
# UI
# =====================================================

with gr.Blocks(title="Still With You") as demo:

    gr.HTML('<h2 style="text-align: center;">STILL WITH YOU</h2>')

    latest_message_id = gr.State(None)
    current_conversation_id = gr.State(None)

    with gr.Row():
        username = gr.Textbox(
            label="Username",
            placeholder="Enter username...",
            scale=4,
        )
        load_btn = gr.Button("Load", scale=1)

    with gr.Row(equal_height=False):

        # ----- Sidebar -----
        with gr.Column(scale=1, min_width=220):
            new_chat_btn = gr.Button("+ New Chat", variant="primary")
            conversations_list = gr.Radio(
                label="History",
                choices=[],
                value=None,
                interactive=True,
            )

        # ----- Main content -----
        with gr.Column(scale=3):

            with gr.Tab("Chat"):

                with gr.Row():
                    voice_selector = gr.Dropdown(
                        label="Active Voice",
                        choices=[],
                        interactive=True,
                        scale=4,
                    )
                    refresh_btn = gr.Button("Refresh Voices", scale=1)

                chatbot = gr.Chatbot(label="Conversation", height=500)

                message = gr.Textbox(
                    label="",
                    placeholder="Type a message...",
                    show_label=False,
                )

                with gr.Row():
                    send_btn = gr.Button("Send", variant="primary")
                    listen_btn = gr.Button("🔊 Listen")
                    clear_btn = gr.Button("Clear")

                audio_player = gr.Audio(
                    label="Generated Speech", type="filepath", autoplay=True
                )

            with gr.Tab("Voices"):

                gr.Markdown("### Add New Voice")

                display_name_input = gr.Textbox(
                    label="Voice Name",
                    placeholder="e.g. Anjana",
                )

                transcript_box = gr.Textbox(
                    value=PROMPTS[0],
                    label="Read the following text aloud",
                    lines=3,
                    interactive=False,
                )

                audio_input = gr.Audio(
                    sources=["microphone"],
                    type="filepath",
                    label="Record Audio",
                )

                upload_btn = gr.Button("Upload Voice", variant="primary")

                upload_status = gr.Textbox(label="Status", interactive=False)

                gr.Markdown("### Saved Voices")

                voices_table = gr.Dataframe(
                    headers=["Voice Name", "Transcript"],
                    label="Saved Voices",
                    interactive=False,
                )

    # ==================================
    # Events
    # ==================================

    load_btn.click(
        fn=load_chat_and_voices,
        inputs=[username],
        outputs=[
            chatbot,
            latest_message_id,
            voice_selector,
            voices_table,
            conversations_list,
            current_conversation_id,
        ],
    )

    new_chat_btn.click(
        fn=new_chat,
        inputs=[username],
        outputs=[
            chatbot,
            latest_message_id,
            conversations_list,
            current_conversation_id,
        ],
    )

    conversations_list.change(
        fn=select_conversation,
        inputs=[username, conversations_list],
        outputs=[chatbot, latest_message_id, current_conversation_id],
    )

    refresh_btn.click(
        fn=refresh_voices,
        inputs=[username],
        outputs=[voice_selector, voices_table],
    )

    send_btn.click(
        fn=send_message,
        inputs=[username, message, chatbot, current_conversation_id],
        outputs=[
            chatbot,
            message,
            latest_message_id,
            conversations_list,
            current_conversation_id,
        ],
    )

    message.submit(
        fn=send_message,
        inputs=[username, message, chatbot, current_conversation_id],
        outputs=[
            chatbot,
            message,
            latest_message_id,
            conversations_list,
            current_conversation_id,
        ],
    )

    listen_btn.click(
        fn=listen,
        inputs=[username, latest_message_id, voice_selector, current_conversation_id],
        outputs=[audio_player],
    )

    clear_btn.click(
        fn=clear_chat,
        inputs=[username, current_conversation_id],
        outputs=[
            chatbot,
            latest_message_id,
            audio_player,
            conversations_list,
            current_conversation_id,
        ],
    )

    upload_btn.click(
        fn=upload_audio,
        inputs=[username, display_name_input, audio_input, transcript_box],
        outputs=[upload_status, voices_table],
    )


# =====================================================
# Launch
# =====================================================

if __name__ == "__main__":
    demo.launch(
        server_name="0.0.0.0", server_port=7890, share=True, allowed_paths=["../data"]
    )
