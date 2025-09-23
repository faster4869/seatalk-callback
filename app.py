import hashlib
import json
from typing import Dict, Any
from flask import Flask, request, jsonify

SIGNING_SECRET = b"DBJFu8MhySlaPkLgIvR0QGmfR2JfBVQ3"

# SeaTalk 事件列表
EVENT_VERIFICATION = "event_verification"
NEW_BOT_SUBSCRIBER = "new_bot_subscriber"
MESSAGE_FROM_BOT_SUBSCRIBER = "message_from_bot_subscriber"
INTERACTIVE_MESSAGE_CLICK = "interactive_message_click"
BOT_ADDED_TO_GROUP_CHAT = "bot_added_to_group_chat"
BOT_REMOVED_FROM_GROUP_CHAT = "bot_removed_from_group_chat"
NEW_MENTIONED_MESSAGE_RECEIVED_FROM_GROUP_CHAT = "new_mentioned_message_received_from_group_chat"

app = Flask(__name__)

def is_valid_signature(signing_secret: bytes, body: bytes, signature: str) -> bool:
    if not signature:
        return False
    return hashlib.sha256(body + signing_secret).hexdigest() == signature

@app.route("/bot-callback", methods=["POST"])
def bot_callback_handler():
    body: bytes = request.get_data()
    data: Dict[str, Any] = json.loads(body)
    event_type: str = data.get("event_type", "")

    # 驗證事件
    if event_type == EVENT_VERIFICATION:
        challenge = data.get("event", {}).get("seatalk_challenge", "")
        return challenge, 200

    # 一般事件簽名驗證
    signature: str = request.headers.get("signature")
    if not is_valid_signature(SIGNING_SECRET, body, signature):
        return "", 400

    # 處理其他事件
    if event_type == NEW_BOT_SUBSCRIBER:
        print("新訂閱者事件:", data)
    elif event_type == MESSAGE_FROM_BOT_SUBSCRIBER:
        print("訂閱者訊息:", data)
    elif event_type == INTERACTIVE_MESSAGE_CLICK:
        print("互動訊息點擊:", data)
    elif event_type == BOT_ADDED_TO_GROUP_CHAT:
        print("加入群組:", data)
    elif event_type == BOT_REMOVED_FROM_GROUP_CHAT:
        print("移出群組:", data)
    elif event_type == NEW_MENTIONED_MESSAGE_RECEIVED_FROM_GROUP_CHAT:
        print("群組@訊息:", data)
    else:
        print("其他事件:", data)

    return "", 200

@app.route("/")
def index():
    return "Seatalk Callback Service is running!", 200

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=8080)
