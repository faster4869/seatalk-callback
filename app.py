import hashlib
import requests
import json
import firebase_admin
from firebase_admin import credentials, db
from typing import Dict, Any, List
import os
from flask import Flask, request, jsonify



# settings
# WARNING: DO NOT hardcode your signing secret in a production environment.
# Instead, load it from a secure environment variable.
# 🚨 IMPORTANT: This has been updated with your new signing secret.
SIGNING_SECRET = b"KKeJjyfCOaxPFQXQE0KVKV_GbTFruCQq"

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

#Seatalk_APP驗證程序
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
    
def init_firebase():
    """
    從環境變數初始化 Firebase Admin SDK。
    Render 平台會將我們設定的秘密變數注入到執行環境中。
    """
    # 從環境變數 'FIREBASE_SERVICE_ACCOUNT_JSON' 讀取金鑰的 JSON 字串
    service_account_json_str = os.environ.get("FIREBASE_SERVICE_ACCOUNT_JSON")

    if not service_account_json_str:
        # 如果在部署環境中找不到這個變數，就拋出錯誤，避免應用程式啟動失敗
        raise ValueError("環境變數 'FIREBASE_SERVICE_ACCOUNT_JSON' 未設定。")

    # 將 JSON 字串解析成 Python 的字典
    service_account_info = json.loads(service_account_json_str)
    
    # 從字典初始化 credentials
    cred = credentials.Certificate(service_account_info)
    
    # 從環境變數讀取資料庫 URL
    db_url = os.environ.get("FIREBASE_DATABASE_URL")
    if not db_url:
        raise ValueError("環境變數 'FIREBASE_DATABASE_URL' 未設定。")
        
    firebase_admin.initialize_app(cred, {"databaseURL": db_url})
    print("Firebase Admin SDK 初始化成功。")

init_firebase()


# add_err_order 函式維持不變
def add_err_order(new_orders: List[Dict[str, str]]):
    """
    新增一個或多個包含 OrderSN 和 TN 的錯誤訂單記錄，並確保 TN 不重複。

    Args:
        new_orders (List[Dict[str, str]]):
            e.g. [{"OSN": "250903GE2XFARX", "TN": "TN001"},
                  {"OSN": "250903GE2XFARX", "TN": "TN002"}]
    """
    if not isinstance(new_orders, list) or not all(
        isinstance(order, dict) and "OSN" in order and "TN" in order
        for order in new_orders
    ):
        print("輸入格式不正確，請提供一個包含 {'OSN': '...', 'TN': '...'} 的列表。")
        return

    base_path = "vm_err_orders/OrderSN"
    grouped_orders: Dict[str, List[str]] = {}

    # Step 1: 依 OSN 分組
    for order in new_orders:
        order_sn = order["OSN"]
        tn = order["TN"]
        if order_sn not in grouped_orders:
            grouped_orders[order_sn] = []
        if tn not in grouped_orders[order_sn]:
            grouped_orders[order_sn].append(tn)

    # Step 2: 更新 DB
    for order_sn, new_tns in grouped_orders.items():
        ref = db.reference(f"{base_path}/{order_sn}")
        existing_tns = ref.get() or []

        if not isinstance(existing_tns, list):
            existing_tns = [existing_tns]

        updated_list = existing_tns.copy()
        added = False
        for tn in new_tns:
            if tn not in updated_list:
                updated_list.append(tn)
                print(f"將新 TN '{tn}' 加入到 OSN '{order_sn}'。")
                added = True
            else:
                print(f"TN '{tn}' 已存在於 OSN '{order_sn}'，跳過。")

        if added:
            ref.set(updated_list)
            print(f"已更新 OSN '{order_sn}' 的 TN 列表。")
        else:
            print(f"OSN '{order_sn}' 沒有新 TN 需要寫入。")

def bot_reply(content: str, group_id: str, thread_id: str = None ):


    app_id = os.environ.get("SEATALK_BOT_X10A_APP_ID")
    app_secret = os.environ.get("SEATALK_BOT_X10A_APP_SECRET")


    api_url = "https://openapi.seatalk.io/auth/app_access_token"

    headers = {
        "Content-Type": "application/json",
    }

    # 定義請求的資料
    payload = {"app_id": app_id, "app_secret": app_secret}

    try:
        response = requests.post(api_url, json=payload, headers=headers)
        response_data = response.json()
        access_token = response_data.get("app_access_token")

    except requests.exceptions.RequestException as e:
        print(f"Request failed")
    

    headers = {
        "Authorization": f"Bearer {access_token}",
        "Content-Type": "application/json"
    }
    message = {
        "tag": "text",
        "text": {
            "content": content
        }
    }
    if thread_id:
        message["thread_id"] = thread_id
    data = {
        "group_id": group_id,
        "message": message
    }
    api_url = "https://openapi.seatalk.io/messaging/v2/group_chat"
    response = requests.post(api_url, headers=headers, json=data)

    return response



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
            group_id = data["event"]["group_id"]
            plain_text = data["event"]["message"]["text"]["plain_text"]
            thread_id = data["event"]["message"]["message_id"]
            print("New mentioned message in group chat received.")
            print(f"收到的CallBack內容:\n{data}")
        
            # 檢查訊息是否以 "@X10A" 開頭，並移除可能的換行或空格
            if plain_text.strip().startswith('(Production)'):
                # 使用 \n 分割字串，並過濾出指定開頭的行
                lines = [line.strip() for line in plain_text.split('\n') if line.strip().startswith(('Order SN', '出貨失敗 TN'))]
            
                data_dict = {}
                for line in lines:
                    if line.startswith("Order SN"):
                        data_dict["OSN"] = line.split("：", 1)[1]  # 取冒號後面的部分
                    elif line.startswith("出貨失敗 TN"):
                        data_dict["TN"] = line.split("：", 1)[1]
            
                new_data = [data_dict]
                add_err_order(new_data)

                #group_id = "NzMwNTUzMTAzMzg3"
                bot_reply('販賣機Err清單已更新成功', group_id, thread_id)

            elif plain_text.strip().startswith('Hi Team'):
                 lines = [line.strip() for line in plain_text.split('\n') if line.strip().startswith(('Seller type', 'Return Reason', 'Username'))]

                 data_dict = {}

                 for line in lines:
                     if line.startswith("Seller type"):
                            data_dict["Seller type"] = line.split("：", 1)[1]  # 取冒號後面的部分
                     elif line.startswith("Return Reason"):
                            data_dict["Return Reason"] = line.split("：", 1)[1]
                     elif line.startswith("Username"):
                            data_dict["Username"] = line.split("：", 1)[1]

                 flow = "" #初始化flow變數
                 if "B2C" in data_dict["Seller type"].strip():
                     flow = "B2C"
                
                 content = f'已反應{flow}PIC<mention-tag target="seatalk://user?email=sylvia.lin@shopee.com"/>處理'
                 bot_reply(content, group_id, thread_id)
                 print(f"Parsed data: {data_dict}")

                
            else:
                print("訊息不是以指定關鍵字開頭，故略過處理。")
                #這邊後續要改成發送錯誤訊息給我，需要新增一個函式
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
