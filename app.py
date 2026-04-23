import hashlib
import requests
import json
import firebase_admin
from firebase_admin import credentials, db
from typing import Dict, Any, List
import os
import time
from flask import Flask, request, jsonify
import gspread
from google.oauth2.service_account import Credentials

# settings
SIGNING_SECRET = b"vhlIrg0Zi_P-EVVK5_x9PZfMnwQvzDNP"

# event list
EVENT_VERIFICATION = "event_verification"
NEW_BOT_SUBSCRIBER = "new_bot_subscriber"
MESSAGE_FROM_BOT_SUBSCRIBER = "message_from_bot_subscriber"
INTERACTIVE_MESSAGE_CLICK = "interactive_message_click"
BOT_ADDED_TO_GROUP_CHAT = "bot_added_to_group_chat"
BOT_REMOVED_FROM_GROUP_CHAT = "bot_removed_from_group_chat"
NEW_MENTIONED_MESSAGE_RECEIVED_FROM_GROUP_CHAT = "new_mentioned_message_received_from_group_chat"

app = Flask(__name__)

# =====================
# Firebase 初始化（維持原本邏輯）
# =====================
def is_valid_signature(signing_secret: bytes, body: bytes, signature: str) -> bool:
    calculated_signature = hashlib.sha256(body + signing_secret).hexdigest()
    return calculated_signature == signature

def init_firebase():
    service_account_json_str = os.environ.get("FIREBASE_SERVICE_ACCOUNT_JSON")
    if not service_account_json_str:
        raise ValueError("環境變數 'FIREBASE_SERVICE_ACCOUNT_JSON' 未設定。")
    service_account_info = json.loads(service_account_json_str)
    cred = credentials.Certificate(service_account_info)
    db_url = os.environ.get("FIREBASE_DATABASE_URL")
    if not db_url:
        raise ValueError("環境變數 'FIREBASE_DATABASE_URL' 未設定。")
    firebase_admin.initialize_app(cred, {"databaseURL": db_url})
    print("Firebase Admin SDK 初始化成功。")

init_firebase()

# =====================
# SeaTalk 共用函式
# =====================
def get_access_token() -> str:
    app_id = os.environ.get("SEATALK_BOT_APP_ID")
    app_secret = os.environ.get("SEATALK_BOT_APP_SECRET")
    response = requests.post(
        "https://openapi.seatalk.io/auth/app_access_token",
        json={"app_id": app_id, "app_secret": app_secret}
    )
    return response.json().get("app_access_token")

def get_employee_code(email: str, access_token: str) -> str:
    response = requests.get(
        f"https://openapi.seatalk.io/contacts/v2/user/info?email={email}",
        headers={"Authorization": f"Bearer {access_token}"}
    )
    data = response.json()
    print(f"get_employee_code response: {data}")
    return data.get("employee_code")

def build_leave_card(leave_data: dict) -> dict:
    return {
        "elements": [
            {
                "element_type": "title",
                "title": {
                    "text": "📋 請假審核申請"
                }
            },
            {
                "element_type": "description",
                "description": {
                    "format": 1,
                    "text": f"**員工**：{leave_data['employee_name']}\n**假別**：{leave_data['leave_type']}\n**開始時間**：{leave_data['start_datetime']}\n**結束時間**：{leave_data['end_datetime']}\n**原因**：{leave_data['reason']}"
                }
            },
            {
                "element_type": "button",
                "button": {
                    "button_type": "callback",
                    "text": "✅ Approve",
                    "value": json.dumps({"action": "approve", "request_id": leave_data["request_id"]})
                }
            },
            {
                "element_type": "button",
                "button": {
                    "button_type": "callback",
                    "text": "❌ 資料錯誤",
                    "value": json.dumps({"action": "reject", "reason": "資料錯誤", "request_id": leave_data["request_id"]})
                }
            },
            {
                "element_type": "button",
                "button": {
                    "button_type": "callback",
                    "text": "🚫 禁止休假",
                    "value": json.dumps({"action": "reject", "reason": "禁止休假", "request_id": leave_data["request_id"]})
                }
            }
        ]
    }

def send_leave_request_card(manager_employee_code: str, leave_data: dict):
    """發送請假審核互動卡片給主管"""
    access_token = get_access_token()
    bot_id = os.environ.get("SEATALK_BOT_ID")
    print(f"sending payload: bot_id={bot_id}, to_employee_code={manager_employee_code}")

    card = build_leave_card(leave_data)

    payload = {
        "bot_id": bot_id,
        "to_employee_code": manager_employee_code,
        "message_type": "interactive_card",
        "content": json.dumps(card)
    }

    response = requests.post(
        "https://openapi.seatalk.io/messaging/v2/bot/send_single_chat",
        headers={
            "Authorization": f"Bearer {access_token}",
            "Content-Type": "application/json"
        },
        json=payload
    )
    print(f"send_leave_request_card response: {response.json()}")
    return response.json()

# =====================
# Google Sheets 寫入（審核完成後記錄）
# =====================
def write_to_sheets(leave_data: dict, action: str, reason: str):
    """審核完成後寫一筆記錄到 Google Sheets"""
    try:
        service_account_info = json.loads(os.environ.get("FIREBASE_SERVICE_ACCOUNT_JSON"))
        scopes = ["https://www.googleapis.com/auth/spreadsheets"]
        creds = Credentials.from_service_account_info(service_account_info, scopes=scopes)
        gc = gspread.authorize(creds)

        sheet_id = os.environ.get("LEAVE_SHEET_ID")
        sheet = gc.open_by_key(sheet_id).worksheet("休假記錄")

        sheet.append_row([
            leave_data.get("created_at", ""),
            leave_data.get("employee_name", ""),
            leave_data.get("employee_email", ""),
            leave_data.get("leave_type", ""),
            leave_data.get("start_datetime", ""),
            leave_data.get("end_datetime", ""),
            leave_data.get("manager_email", ""),
            "approved" if action == "approve" else "rejected",
            reason,
            time.strftime("%Y-%m-%d %H:%M:%S")
        ])
        print("Google Sheets 寫入成功")
    except Exception as e:
        print(f"Google Sheets 寫入失敗: {e}")

# =====================
# 新 Route：接收請假申請
# =====================
@app.route("/leave/apply/test", methods=["POST"])
def leave_apply_test():
    try:
        leave_data = {
            "request_id": f"LEAVE_{int(time.time())}",
            "employee_email": "chris.chouyh@shopee.com",
            "employee_name": "Chris",
            "leave_type": "特休",
            "start_datetime": "2026-05-01 09:00",
            "end_datetime": "2026-05-01 18:00",
            "reason": "家庭因素",
            "status": "pending",
            "created_at": time.strftime("%Y-%m-%d %H:%M:%S")
        }

        access_token = get_access_token()
        bot_id = os.environ.get("SEATALK_BOT_ID")
        card = build_leave_card(leave_data)  

        payload = {
            "employee_code": "247857",
            "message": {
                "tag": "interactive_message",
                "interactive_message": build_leave_card(leave_data)
            },
            "usable_platform": "mobile"
        }

        response = requests.post(
            "https://openapi.seatalk.io/messaging/v2/single_chat",
            headers={
                "Authorization": f"Bearer {access_token}",
                "Content-Type": "application/json"
            },
            json=payload
        )
        result = response.json()
        print(f"send card result: {result}")
        return jsonify({"status": "ok", "seatalk_response": result}), 200

    except Exception as e:
        print(f"leave_apply_test error: {e}")
        return jsonify({"status": "error", "message": str(e)}), 500
        
@app.route("/leave/apply", methods=["POST"])
def leave_apply():
    """接收 AppSheet 送出的請假申請"""
    try:
        data = request.get_json()
        print(f"收到請假申請: {data}")

        # 產生唯一 request_id
        request_id = f"LEAVE_{int(time.time())}"

        # 查主管對應表
        manager_ref = db.reference(f"employee_manager_map/{data['employee_email'].replace('.', '_').replace('@', '_at_')}")
        manager_data = manager_ref.get()

        if not manager_data:
            return jsonify({"status": "error", "message": "找不到對應主管"}), 400

        # 組合請假資料
        leave_data = {
            "request_id": request_id,
            "employee_email": data["employee_email"],
            "employee_name": data["employee_name"],
            "manager_email": manager_data["manager_email"],
            "leave_type": data["leave_type"],
            "start_datetime": data["start_datetime"],
            "end_datetime": data["end_datetime"],
            "reason": data["reason"],
            "status": "pending",
            "created_at": time.strftime("%Y-%m-%d %H:%M:%S")
        }

        # 寫入 Firebase
        db.reference(f"leave_requests/{request_id}").set(leave_data)

        # 發送卡片給主管
        send_leave_request_card(manager_data["manager_email"], leave_data)

        return jsonify({"status": "ok", "request_id": request_id}), 200

    except Exception as e:
        print(f"leave_apply error: {e}")
        return jsonify({"status": "error", "message": str(e)}), 500

# =====================
# 原本的 bot-callback（加上 INTERACTIVE_MESSAGE_CLICK 處理）
# =====================
@app.route("/bot-callback", methods=["POST"])
def bot_callback_handler():
    body: bytes = request.get_data()
    signature: str = request.headers.get("signature", "").strip()

    if not signature or not is_valid_signature(SIGNING_SECRET, body, signature):
        return "Invalid signature", 403

    try:
        data: Dict[str, Any] = json.loads(body)
        event_type: str = data.get("event_type", "")
        print(f"Received event type: {event_type}")

        seatalk_challenge = data.get("seatalk_challenge")
        if seatalk_challenge:
            return seatalk_challenge

        if event_type == EVENT_VERIFICATION:
            event_data = data.get("event", {})
            challenge = event_data.get("seatalk_challenge")
            if challenge:
                return jsonify({"seatalk_challenge": challenge})
            return "Verification event data not found.", 400

        elif event_type == INTERACTIVE_MESSAGE_CLICK:
            event_data = data.get("event", {})
            # 取得按鈕的 value（我們塞的 JSON 字串）
            raw_value = event_data.get("interactive_info", {}).get("value", "{}")
            click_data = json.loads(raw_value)

            action = click_data.get("action")
            request_id = click_data.get("request_id")
            reason = click_data.get("reason", "")

            print(f"互動點擊 - action: {action}, request_id: {request_id}, reason: {reason}")

            if not request_id:
                return "", 200

            # 從 Firebase 取出請假資料
            leave_ref = db.reference(f"leave_requests/{request_id}")
            leave_data = leave_ref.get()

            if not leave_data:
                print(f"找不到 request_id: {request_id}")
                return "", 200

            # 更新 Firebase 狀態
            leave_ref.update({
                "status": "approved" if action == "approve" else "rejected",
                "reject_reason": reason,
                "reviewed_at": time.strftime("%Y-%m-%d %H:%M:%S")
            })

            # 寫入 Google Sheets
            write_to_sheets(leave_data, action, reason)

            print(f"審核完成 - {request_id}: {action}")

        # 以下維持原本邏輯不動
        elif event_type == NEW_BOT_SUBSCRIBER:
            print("New bot subscriber event received.")
            pass

        elif event_type == MESSAGE_FROM_BOT_SUBSCRIBER:
            print("Message from bot subscriber event received.")
            pass

        elif event_type == BOT_ADDED_TO_GROUP_CHAT:
            print("Bot added to group chat event received.")
            pass

        elif event_type == BOT_REMOVED_FROM_GROUP_CHAT:
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
                 lines = [line.strip() for line in plain_text.split('\n') if line.strip().startswith(('Seller Type', 'Return Status','Return Reason', 'Seller Username'))]

                 data_dict = {}

                 for line in lines:
                     if line.startswith("Seller Type"):
                            data_dict["Seller Type"] = line.split("：", 1)[1]  # 取冒號後面的部分

                     elif line.startswith("Return Status"):
                            normalized_line = line.replace("：", ":").strip()
                            data_dict["Return Status"] = normalized_line.split(":", 1)[1].strip()

                     elif line.startswith("Return Reason"):
                            normalized_line = line.replace("：", ":").strip()
                            data_dict["Return Reason"] = normalized_line.split(":", 1)[1].strip()

                     elif line.startswith("Seller Username"):
                            normalized_line = line.replace("：", ":").strip()
                            data_dict["Seller Username"] = normalized_line.split(":", 1)[1].strip()

                 special_seller_list = [
                    "fe_amart",
                    "digitalcitytw",
                    "senao.tw",
                    "daikin_senao",
                    "samsung_he",
                    "sakuyo_Japan",
                    "bianco_senao",
                    "MegaKing_senao",
                    "panasonic_senao",
                    "shopee_pass",
                    "esim_go",
                    "shopee24h",
                    "shopee24h_hb",
                    "shopee24h_el",
                    "asus_official_store",
                    "outsourcing_24h",
                    "thebestofkaohsiung",
                    "foodie.select",
                    "game_official",
                    "game_quick",
                    "google.tw",
                    "oppo_official",
                    "realmetw",
                    "shopee_consumables",
                    "sp_games",
                    "ticket_service",
                    "topbrandtw",
                    "shopee_choice_hl",
                    "apple.tw",
                    "asiawifi"
                ]
                 flow = "" #初始化flow變數
                 mention_tag = ""#初始化mention_tag變數

                 print(f"解析後的資料字典: {data_dict}")
                 if "Requested" in data_dict.get("Return Status", "").strip():
                     
                     mention_tag = "<mention-tag target=\"seatalk://user?email=ziv.hung@shopee.com\"/><mention-tag target=\"seatalk://user?email=sharon.chuic@shopee.com\"/>"
                     content = f'{mention_tag}\n此案件需協助推送到Judging，請PIC協助確認案件內容!'
                     bot_reply(content, group_id, thread_id)

                 elif "Judging" in data_dict.get("Return Status", "").strip() or "Processing" in data_dict.get("Return Status", "").strip():
                    if data_dict.get("Seller Username", "").strip() in special_seller_list:
                        flow = "Mall 特賣"
                        mention_tag = "<mention-tag target=\"seatalk://user?email=lynne.chung@shopee.com\"/><mention-tag target=\"seatalk://user?email=vivian.liu@shopee.com\"/>"
                        content = f'{mention_tag}\n此為{flow}案件，請PIC協助確認案件內容!'
                        bot_reply(content, group_id, thread_id)

                    else:
                        reason = data_dict.get("Return Reason", "").strip()
                        if "包裹未送達／無法取件" in reason:
                            flow = "Flow A"
                            mention_tag = "<mention-tag target=\"seatalk://user?email=vivian.liu@shopee.com\"/><mention-tag target=\"seatalk://user?email=lynne.chung@shopee.com\"/>"
                            content = f'{mention_tag}\n此為{flow}案件，請PIC協助確認案件內容!'
                            bot_reply(content, group_id, thread_id)

                        elif "商品缺件／賣家通知缺貨" in reason:
                            flow = "Flow B"
                            mention_tag = "<mention-tag target=\"seatalk://user?email=tina.tang@shopee.com\"/><mention-tag target=\"seatalk://user?email=jennifer.su@shopee.com\"/>"
                            content = f'{mention_tag}\n此為{flow}案件，請PIC協助確認案件內容!'
                            bot_reply(content, group_id, thread_id)
                        else:
                            flow = "Flow C"
                            mention_tag = "<mention-tag target=\"seatalk://user?email=sharon.chuic@shopee.com\"/><mention-tag target=\"seatalk://user?email=ziv.hung@shopee.com\"/>"
                            content = f'{mention_tag}\n此為{flow}案件，請PIC協助確認案件內容!'
                            bot_reply(content, group_id, thread_id)
                
                 elif "Accepted" in data_dict.get("Return Status", "").strip() or "Seller dispute" in data_dict.get("Return Status", "").strip() or "Seller Dispute" in data_dict.get("Return Status", "").strip():

                     if "C2C" in data_dict.get("Seller Type", "").strip():
                         flow = "C2C Dispute"
                         mention_tag = "<mention-tag target=\"seatalk://user?email=alice.cheng@shopee.com\"/><mention-tag target=\"seatalk://user?email=janice.lin@shopee.com\"/>"
                         content = f'{mention_tag}\n此為{flow}案件，請PIC協助確認案件內容!'
                         bot_reply(content, group_id, thread_id)

                     elif "Mall" in data_dict.get("Seller Type", "").strip():
                         flow = "Mall Dispute"
                         mention_tag = "<mention-tag target=\"seatalk://user?email=shin.lee@shopee.com\"/>"
                         #移除Amelie，待後續加上
                         content = f'{mention_tag}\n此為{flow}案件，請PIC協助確認案件內容!'
                         bot_reply(content, group_id, thread_id)

                     elif "CB" in data_dict.get("Seller Type", "").strip():
                         flow = "CB Dispute"
                         mention_tag = "<mention-tag target=\"seatalk://user?email=queenie.chien@shopee.com\"/><mention-tag target=\"seatalk://user?email=winnie.hsu@shopee.com\"/>"
                         content = f'{mention_tag}\n此為{flow}案件，請PIC協助確認案件內容!'
                         bot_reply(content, group_id, thread_id)
                     
                 else:   
                    content = f'Return Status內容有誤，無法判定通知對象，請重新確認格式'
                    bot_reply(content, group_id, thread_id)


                
            else:

                content = '訊息內容未以指定關鍵字開頭，請重新確認格式'
                bot_reply(content, group_id, thread_id)

        else:
            print(f"Unknown event type: {event_type}")

    except json.JSONDecodeError:
        return "Invalid JSON in request body", 400

    return "", 200

if __name__ == "__main__":
    app.run(debug=True)
