import hashlib
import json
import requests

from typing import Dict, Any, List

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

def add_err_order(client: FirebaseClient, new_orders: List[Dict[str, str]]):
    """
    新增一個或多個包含 OrderSN 和 TN 的錯誤訂單記錄，並確保TN不重複。

    Args:
        client (FirebaseClient): 你的 FirebaseClient 實例。
        new_orders (List[Dict[str, str]]): 包含 OrderSN 和 TN 的訂單列表，例如：
                                            [{'OSN': '2509170Q5BKFNJ3', 'TN': 'TN001'},
                                             {'OSN': '2509170Q5BKFNJ3', 'TN': 'TN002'}]
    """
    # 檢查輸入格式
    if not isinstance(new_orders, list) or not all(isinstance(order, dict) and 'OSN' in order and 'TN' in order for order in new_orders):
        print("輸入格式不正確，請提供一個包含{'OSN': '...', 'TN': '...'}字典的列表。")
        return

    base_path = "vm_err_orders/OrderSN"
    # 步驟 1: 將輸入的訂單按 OSN 分組
    grouped_orders: Dict[str, List[str]] = {}
    for order in new_orders:
        order_sn = order['OSN']
        tn = order['TN']
        if order_sn not in grouped_orders:
            grouped_orders[order_sn] = []
        if tn not in grouped_orders[order_sn]:
            grouped_orders[order_sn].append(tn)
    
    print("已將所有輸入的TN按OSN分組。")
    
    # 步驟 2: 遍歷每個 OSN，讀取現有資料並合併
    added_count = 0
    for order_sn, new_tns in grouped_orders.items():
        # 讀取現有 TN 列表
        existing_tns = client.get(f"{base_path}/{order_sn}")
        
        # 處理資料格式
        if existing_tns is None:
            existing_tns = []
        elif not isinstance(existing_tns, list):
            existing_tns = [existing_tns]
        
        updated_list = existing_tns.copy()
        
        # 檢查並新增 TN，確保不重複
        for tn in new_tns:
            if tn not in updated_list:
                updated_list.append(tn)
                added_count += 1
                print(f"將新 TN '{tn}' 加入到 OSN '{order_sn}'。")
            else:
                print(f"TN '{tn}' 已存在於 OSN '{order_sn}'，跳過。")

        # 寫回資料庫
        if len(updated_list) > len(existing_tns):
            client.set(f"{base_path}/{order_sn}", updated_list)
            print(f"已更新 OSN '{order_sn}' 的 TN 列表。")
        else:
            print(f"OSN '{order_sn}' 沒有新 TN 需要寫入。")
            
    if added_count == 0:
        print("沒有任何新訂單或 TN 需要寫入資料庫。")


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
                # 使用 \n 分割字串，並過濾出指定開頭的行
                lines = [line.strip() for line in plain_text.split('\n') if line.strip().startswith(('Order SN', '出貨失敗TN'))]
            
                data_dict = {}
                for line in lines:
                    if line.startswith("Order SN"):
                        data_dict["OSN"] = line.split("：", 1)[1]  # 取冒號後面的部分
                    elif line.startswith("出貨失敗TN"):
                        data_dict["TN"] = line.split("：", 1)[1]
            
                new_data = [data_dict]

                client = FirebaseClient("https://shopee-vm-api-default-rtdb.firebaseio.com")
                add_err_order(client, new_data)

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
