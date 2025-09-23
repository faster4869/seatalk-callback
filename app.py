from flask import Flask, request, jsonify

app = Flask(__name__)

@app.route("/callback", methods=["POST"])
def seatalk_callback():
    data = request.json
    print("收到 SeaTalk Callback:", data)

    # 這裡可以依 event_type 做不同處理
    # SeaTalk 驗證要求回傳 200 + JSON
    return jsonify({"status":"ok"}), 200

@app.route("/")
def index():
    return "Seatalk Callback Service is running!", 200

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=8080)
