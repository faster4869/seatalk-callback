import hashlib
import json
from typing import Dict, Any

from flask import Flask, request, jsonify

class FirebaseClient:
    def __init__(self, base_url, auth=None):
        self.base_url = base_url.rstrip("/")
        self.auth = auth

    def _make_url(self, path):
        url = f"{self.base_url}/{path}.json"
        if self.auth:
            url += f"?auth={self.auth}"
        return url

    def get(self, path):
        resp = requests.get(self._make_url(path))
        return resp.json()

    def set(self, path, data):
        resp = requests.put(self._make_url(path), json=data)
        return resp.json()

    def update(self, path, data):
        resp = requests.patch(self._make_url(path), json=data)
        return resp.json()

    def push(self, path, data):
        resp = requests.post(self._make_url(path), json=data)
        return resp.json()

    def delete(self, path):
        resp = requests.delete(self._make_url(path))
        return resp.status_code == 200

# settings
# WARNING: DO NOT hardcode your signing secret in a production environment.
# Instead, load it from a secure environment variable.
# 🚨 IMPORTANT: This has been updated with your new signing secret.
SIGNING_SECRET = b"vhlIrg0Zi_P-EVVK5_x9PZfMnwQvzDNP"

# event list
# ref: https://open.seatalk.io/docs/list-of-events
EVENT_VERIFICATION = "event_verification"
NEW_BOT_SUBSCRIBER = "new_bot_subscriber"
MESSAGE_FROM_BOT_SUBSCRIBER = "message_from_bot_subscriber"
INTERACTIVE_MESSAGE_CLICK = "interactive_message_click"
BOT_ADDED_TO_GROUP_CHAT = "bot_added_to_group_chat"
BOT_REMOVED_FROM_GROUP_CHAT = "bot_removed_from_group_chat"
NEW_MENTIONED_MESSAGE_RECEIVED_FROM_GROUP_CHAT = "new_mentioned_message_received_from_group_chat"

app = Flask(__name__)


def is_valid_signature(signing_secret: bytes, body: bytes, signature: str) -> bool:
    """
    Validates the signature of the incoming request using SHA256.
    
    Args:
        signing_secret: The bot's signing secret as bytes.
        body: The raw request body as bytes.
        signature: The signature string from the request header.
        
    Returns:
        True if the signature is valid, False otherwise.
    """
    # Use the SHA256 algorithm as specified by the Seatalk documentation.
    # The signature must be calculated on the raw body + signing secret.
    calculated_signature = hashlib.sha256(body + signing_secret).hexdigest()
    return calculated_signature == signature

def add_err_order(client, new_order_sns):
    """
    讀取現有的 vm_err_orders/OrderSN 陣列，並新增一個或多個訂單號碼。

    Args:
        client (FirebaseClient): 你的 FirebaseClient 實例。
        new_order_sns (str or list): 要新增的一個或多個訂單號碼。
    """
    # 確保 new_order_sns 是可迭代的列表，以便於處理
    if isinstance(new_order_sns, str):
        new_order_sns = [new_order_sns]
    elif not isinstance(new_order_sns, list):
        print("輸入格式不正確，請提供一個字串或列表。")
        return

    path = "vm_err_orders/OrderSN"
    
    # 1. 讀取現有的 OrderSN 陣列
    existing_list = client.get(path)

    # 處理讀取到的資料格式
    if existing_list is None:
        # 如果路徑不存在或資料為空，則建立一個新陣列
        existing_list = []
        print("資料庫中沒有現有的訂單號碼，將建立新陣列。")
    elif isinstance(existing_list, dict):
        # 如果資料庫中的資料是字典格式 (e.g., {"0": "...", "1": "..."})，則轉換成列表
        existing_list = list(existing_list.values())
        
    added_count = 0
    
    # 2. 遍歷要新增的訂單號碼列表，並逐一檢查和新增
    for order_sn in new_order_sns:
        if order_sn not in existing_list:
            existing_list.append(order_sn)
            print(f"成功將新的訂單號碼 {order_sn} 加入。")
            added_count += 1
        else:
            print(f"訂單號碼 {order_sn} 已存在，無需重複新增。")
            
    # 3. 如果有任何新的訂單號碼被加入，才將更新後的列表寫回資料庫
    if added_count > 0:
        response = client.set(path, existing_list)
        print("更新後的資料寫入資料庫:", response)
    else:
        print("沒有新的訂單號碼需要寫入。")


@app.route("/", methods=["GET"])
def home():
    """
    A simple home page to confirm the app is running.
    """
    return "Seatalk Bot Callback Handler is running. Please use the /bot-callback endpoint for POST requests."


@app.route("/bot-callback", methods=["POST"])
def bot_callback_handler():
    """
    Handles incoming webhook events from Seatalk.
    
    This function validates the request signature, handles different event types,
    and returns an appropriate response.
    """
    body: bytes = request.get_data()
    # Safely get the signature and strip any potential leading/trailing whitespace.
    signature: str = request.headers.get("signature", "").strip()

    # 1. Validate the signature for security.
    if not signature or not is_valid_signature(SIGNING_SECRET, body, signature):
        # Return a 403 Forbidden status for invalid signatures.
        return "Invalid signature", 403
        
    # 2. Handle events from the webhook.
    # Use a try-except block to handle potential JSON decoding errors.
    try:
        data: Dict[str, Any] = json.loads(body)
        event_type: str = data.get("event_type", "")
        
        # Log the event type for debugging purposes.
        print(f"Received event type: {event_type}")

        # The verification request sends a 'seatalk_challenge' parameter directly.
        seatalk_challenge = data.get("seatalk_challenge")
        if seatalk_challenge:
            print("Received seatalk_challenge for verification.")
            return seatalk_challenge
            
        if event_type == EVENT_VERIFICATION:
            # For event verification, return the 'event' field from the payload as a plain text string.
            event_data = data.get("event")
            if event_data:
                return event_data
            else:
                return "Verification event data not found.", 400
        
        elif event_type == NEW_BOT_SUBSCRIBER:
            # Handle new bot subscriber event.
            # Example: Send a welcome message to the new subscriber.
            print("New bot subscriber event received.")
            pass
        
        elif event_type == MESSAGE_FROM_BOT_SUBSCRIBER:
            # Handle direct message from a bot subscriber.
            # Example: Process the message content and respond.
            print("Message from bot subscriber event received.")
            pass
        
        elif event_type == INTERACTIVE_MESSAGE_CLICK:
            # Handle interactive message click event.
            # Example: Update the message or trigger an action.
            print("Interactive message click event received.")
            pass
        
        elif event_type == BOT_ADDED_TO_GROUP_CHAT:
            # Handle bot added to group chat event.
            # Example: Announce the bot's presence in the group.
            print("Bot added to group chat event received.")
            pass
        
        elif event_type == BOT_REMOVED_FROM_GROUP_CHAT:
            # Handle bot removed from group chat event.
            # Example: Clean up group-related data.
            print("Bot removed from group chat event received.")
            pass
        
        elif event_type == NEW_MENTIONED_MESSAGE_RECEIVED_FROM_GROUP_CHAT:
            # Handle new mentioned message in group chat.
            # Example: Process the mention and respond to the user.
            print(data)
            plain_text = data["event"]["message"]["text"]["plain_text"]
            print(plain_text)
            print("New mentioned message in group chat received.")
        
            # 檢查訊息是否以 "@X10A" 開頭，並移除可能的換行或空格
            if plain_text.strip().startswith('@X10A'):
                # 使用 \n 分割字串，並過濾掉空字串
                lines = [line.strip() for line in plain_text.split('\n') if line.strip()]
        
                # 移除列表中的第一個元素 (即 @X10A 指令本身)
                if lines:
                    client = FirebaseClient("https://shopee-vm-api-default-rtdb.firebaseio.com")
                    order_sn_list = lines[1:]
                    add_err_order(client, order_sn_list)
                    print("解析出的訂單號碼列表:", order_sn_list)
                else:
                    order_sn_list = []
                    print("訊息格式不正確，未找到訂單號碼。")
            else:
                print("訊息不是以 '@X10A' 指令開頭，略過處理。")
        
        else:
            # Log unknown event types.
            print(f"Unknown event type: {event_type}")
            pass
    
    except json.JSONDecodeError:
        # Return a 400 Bad Request status if the body is not valid JSON.
        return "Invalid JSON in request body", 400

    # According to Seatalk docs, return an empty string with a 200 OK status
    # for all successfully handled events.
    return "", 200

if __name__ == "__main__":
    # In a production environment, use a WSGI server like Gunicorn.
    # This is for local development only.
    app.run(debug=True)
