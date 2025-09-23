import hashlib
import json
from typing import Dict, Any
from flask import Flask, request, jsonify

# settings
SIGNING_SECRET = b"DBJFu8MhySlaPkLgIvR0QGmfR2JfBVQ3"

# event list
EVENT_VERIFICATION = "event_verification"
NEW_BOT_SUBSCRIBER = "new_bot_subscriber"
MESSAGE_FROM_BOT_SUBSCRIBER = "message_from_bot_subscriber"
INTERACTIVE_MESSAGE_CLICK = "interactive_message_click"
BOT_ADDED_TO_GROUP_CHAT = "bot_added_to_group_chat"
BOT_REMOVED_FROM_GROUP_CHAT = "bot_removed_from_group_chat"
NEW_MENTIONED_MESSAGE_RECEIVED_FROM_GROUP_CHAT = "new_mentioned_message_received_from_group_chat"

app = Flask(__name__)

def is_valid_signature(signing_secret: bytes, body: bytes, signature: str) -> bool:
    # ref: https://open.seatalk.io/docs/server-apis-event-callback
    return hashlib.sha256(body + signing_secret).hexdigest() == signature

@app.route("/bot-callback", methods=["POST"])
def bot_callback_handler():
    body: bytes = request.get_data()
    signature: str = request.headers.get("signature")

    # 1. validate the signature
    if not is_valid_signature(SIGNING_SECRET, body, signature):
        return "", 400  # 驗證失敗回 400

    # 2. handle events
    data: Dict[str, Any] = json.loads(body)
    event_type: str = data.get("event_type", "")

    if event_type == EVENT_VERIFICATION:
        # 回傳 seatalk_challenge 的值
        challenge = data.get("event", {}).get("seatalk_challenge", "")
        return challenge, 200

    elif event_type == NEW_BOT_SUBSCRIBER:
        # TODO: 處理新訂閱者
        pass
    elif event_type == MESSAGE_FROM_BOT_SUBSCRIBER:
        # TODO: 處理訊息
        pass
    elif event_type == INTERACTIVE_MESSAGE_CLICK:
        # TODO: 處理互動訊息點擊
        pass
    elif event_type == BOT_ADDED_TO_GROUP_CHAT:
        # TODO: 處理加入群組
        pass
    elif event_type == BOT_REMOVED_FROM_GROUP_CHAT:
        # TODO: 處理被移出群組
        pass
    elif event_type == NEW_MENTIONED_MESSAGE_RECEIVED_FROM_GROUP_CHAT:
        # TODO: 處理群組@訊息
        pass
    else:
        pass

    # 一般事件處理完成後回傳空字串即可
    return "", 200

@app.route("/")
def index():
    return "Seatalk Callback Service is running!", 200

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=8080)

