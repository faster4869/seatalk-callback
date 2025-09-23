from flask import Flask, request, jsonify

app = Flask(__name__)

@app.route("/callback", methods=["POST"])
def seatalk_callback():
    data = request.json

    # 驗證 SeaTalk callback
    if "seatalk_challenge" in data:
        return data["seatalk_challenge"], 200  # 原封不動回傳
       
    # 一般事件處理
    print("收到 SeaTalk Callback:", data)
    return jsonify({"status":"ok"}), 200

@app.route("/")
def index():
    return "Seatalk Callback Service is running!", 200

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=8080)
