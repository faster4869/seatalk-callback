from flask import Flask, request, jsonify

app = Flask(__name__)

@app.route("/callback", methods=["POST"])
def seatalk_callback():
    data = request.json
    print("收到 SeaTalk Callback:", data)

    # TODO: 這裡可以依 event_type 處理不同邏輯
    return jsonify({"status": "ok"}), 200

@app.route("/")
def index():
    return "Seatalk Callback Service is running!", 200
