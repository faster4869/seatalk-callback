import hashlib
import json
from typing import Dict, Any

from flask import Flask, request, jsonify

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

        if event_type == EVENT_VERIFICATION:
            # For event verification, return the 'event' field from the payload as a JSON object.
            return jsonify({"event": data.get("event")})
        
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
            print("New mentioned message in group chat received.")
            pass
        
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
