from flask import Flask, request
from twilio.twiml.messaging_response import MessagingResponse
from twilio.rest import Client
from openai import OpenAI
import os
import json
from datetime import datetime, timedelta, timezone
from apscheduler.schedulers.background import BackgroundScheduler
import re
from dotenv import load_dotenv

# Load environment variables from .env file
load_dotenv()

app = Flask(__name__)

# ────────────────────────────────────────────────
#               CONFIGURATION – LOADED FROM .env
# ────────────────────────────────────────────────
TWILIO_ACCOUNT_SID = os.getenv("TWILIO_ACCOUNT_SID")
TWILIO_AUTH_TOKEN  = os.getenv("TWILIO_AUTH_TOKEN")
TWILIO_WHATSAPP_NUMBER = os.getenv("TWILIO_WHATSAPP_NUMBER", "whatsapp:+14155238886")

OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
EMERGENCY_CONTACT = os.getenv("EMERGENCY_CONTACT")

# Check required env vars
required_env = ["TWILIO_ACCOUNT_SID", "TWILIO_AUTH_TOKEN", "OPENAI_API_KEY", "EMERGENCY_CONTACT"]
missing = [var for var in required_env if not os.getenv(var)]
if missing:
    raise ValueError(f"Missing required environment variables: {', '.join(missing)}")

# ────────────────────────────────────────────────
#           TIMEZONE CONFIG
# ────────────────────────────────────────────────
UTC_OFFSET_HOURS = int(os.getenv("UTC_OFFSET_HOURS", "7"))
TIMEZONE_LABEL = os.getenv("TIMEZONE_LABEL", "WIB")

# Files for storage
SCHEDULES_FILE = "schedules.json" # Diisi oleh dev
REMAINDER_FILE = "remainder.json" # Hasil buat baru dari chat

# ────────────────────────────────────────────────
#           GLOBAL VARIABLES
# ────────────────────────────────────────────────
twilio_client = Client(TWILIO_ACCOUNT_SID, TWILIO_AUTH_TOKEN)
openai_client = OpenAI(api_key=OPENAI_API_KEY)

# Custom reminders from chat
user_reminders = {}

# Scheduler for reminders
scheduler = BackgroundScheduler()
scheduler.start()

# ────────────────────────────────────────────────
#           PERSISTENCE HELPERS (JSON)
# ────────────────────────────────────────────────

def load_user_reminders_from_file():
    """Memuat pengingat kustom dari remainder.json saat startup"""
    global user_reminders
    try:
        if os.path.exists(REMAINDER_FILE):
            with open(REMAINDER_FILE, 'r') as f:
                data = json.load(f)
                for user_number, reminders in data.items():
                    user_reminders[user_number] = []
                    for rem in reminders:
                        user_reminders[user_number].append({
                            "time": datetime.fromisoformat(rem["time"]),
                            "message": rem["message"]
                        })
            print(f"Loaded existing reminders from {REMAINDER_FILE}")
    except Exception as e:
        print(f"Error loading {REMAINDER_FILE}: {e}")

def save_user_reminders_to_file():
    """Menyimpan pengingat kustom ke remainder.json agar permanen"""
    try:
        data_to_save = {}
        for user_number, reminders in user_reminders.items():
            data_to_save[user_number] = []
            for rem in reminders:
                data_to_save[user_number].append({
                    "time": rem["time"].isoformat(),
                    "message": rem["message"]
                })
        with open(REMAINDER_FILE, 'w') as f:
            json.dump(data_to_save, f, indent=4)
    except Exception as e:
        print(f"Error saving to {REMAINDER_FILE}: {e}")

# ────────────────────────────────────────────────
#           LOAD REGULAR DAILY SCHEDULES
# ────────────────────────────────────────────────

def load_regular_schedules():
    """Load daily schedules from schedules.json (Developer-defined)"""
    try:
        if os.path.exists(SCHEDULES_FILE):
            with open(SCHEDULES_FILE, 'r') as f:
                data = json.load(f)
            schedules = data.get("global_daily_reminders", [])

            for sched in schedules:
                if not sched.get("active", False):
                    continue

                time_utc_str = sched.get("time_utc")
                if not time_utc_str:
                    continue

                try:
                    hour, minute, second = map(int, time_utc_str.split(":"))
                    scheduler.add_job(
                        send_regular_reminder,
                        'cron',
                        hour=hour,
                        minute=minute,
                        second=second,
                        args=[sched["message"]],
                        id=f"daily_{sched['message'][:20]}",
                        replace_existing=True
                    )
                    print(f"Scheduled daily reminder: {time_utc_str} UTC")
                except Exception as e:
                    print(f"Error scheduling {sched}: {e}")
    except Exception as e:
        print(f"Error loading {SCHEDULES_FILE}: {e}")

def send_regular_reminder(message):
    """Send daily reminder to emergency contact"""
    send_whatsapp_message(EMERGENCY_CONTACT, message)

# ────────────────────────────────────────────────
#           HELPER FUNCTIONS
# ────────────────────────────────────────────────

def send_whatsapp_message(to_number, body):
    try:
        twilio_client.messages.create(
            from_=TWILIO_WHATSAPP_NUMBER,
            body=body,
            to=to_number
        )
        print(f"Message sent to {to_number}")
    except Exception as e:
        print(f"Failed to send to {to_number}: {e}")

def check_and_send_reminders():
    """Check due custom reminders and update remainder.json if sent"""
    now_utc = datetime.now(timezone.utc)
    changed = False
    for user_number, reminders in list(user_reminders.items()):
        remaining = []
        for rem in reminders:
            if rem["time"] <= now_utc:
                send_whatsapp_message(user_number, rem["message"])
                changed = True
            else:
                remaining.append(rem)
        user_reminders[user_number] = remaining
    
    if changed:
        save_user_reminders_to_file()

# Schedule the check every 1 minute
scheduler.add_job(check_and_send_reminders, 'interval', minutes=1)

# Startup sequence: Load schedules and existing reminders
load_regular_schedules()
load_user_reminders_from_file()

# ────────────────────────────────────────────────
#                MAIN WEBHOOK
# ────────────────────────────────────────────────

@app.route("/webhook", methods=["POST"])
def whatsapp_webhook():
    incoming_msg = request.values.get("Body", "").strip()
    from_number = request.values.get("From", "")
    profile_name = request.values.get("ProfileName", "User")

    resp = MessagingResponse()
    response_text = "Sorry, I didn't quite understand. Could you try again? 😊"

    lower_msg = incoming_msg.lower()

    # Emergency detection
    emergency_keywords = ["emergency", "help", "urgent", "pain", "chest pain", "can't breathe", "darurat", "tolong", "sakit dada"]
    if any(word in lower_msg for word in emergency_keywords):
        alert_text = f"!!! EMERGENCY ALERT !!!\nFrom: {profile_name} ({from_number})\nMessage: {incoming_msg}"
        send_whatsapp_message(EMERGENCY_CONTACT, alert_text)
        response_text = "I've sent an urgent message to your emergency contact. Please stay calm. ❤️"

    else:
        try:
            now_utc = datetime.now(timezone.utc)
            current_user_time = now_utc + timedelta(hours=UTC_OFFSET_HOURS)
            current_str = current_user_time.strftime("%H:%M %Y-%m-%d") + f" {TIMEZONE_LABEL}"

            system_prompt = (
                f"The user is in {TIMEZONE_LABEL}. Current time is {current_str}.\n"
                "You are a kind health assistant for elderly. Always reply in simple, warm English.\n"
                "Output ONLY valid JSON with this structure:\n"
                "{\n"
                '  "reply": "your message",\n'
                '  "reminder": {"time": "HH:MM", "message": "..."} or null\n'
                "}"
            )

            completion = openai_client.chat.completions.create(
                model="gpt-4.1-nano",
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": incoming_msg}
                ],
                temperature=0.6,
                response_format={"type": "json_object"}
            )

            parsed = json.loads(completion.choices[0].message.content)
            response_text = parsed.get("reply", "I'm here to help! 😊")

            reminder_data = parsed.get("reminder")
            if reminder_data and isinstance(reminder_data, dict):
                time_str = reminder_data.get("time")
                msg = reminder_data.get("message", "Reminder! 😊")

                if time_str and re.match(r"^\d{2}:\d{2}$", time_str):
                    try:
                        hour, minute = map(int, time_str.split(":"))
                        remind_utc = now_utc.replace(hour=hour, minute=minute, second=0, microsecond=0)
                        remind_utc -= timedelta(hours=UTC_OFFSET_HOURS)

                        if remind_utc < now_utc:
                            remind_utc += timedelta(days=1)

                        if from_number not in user_reminders:
                            user_reminders[from_number] = []

                        user_reminders[from_number].append({
                            "time": remind_utc, 
                            "message": msg
                        })
                        
                        # Save to remainder.json immediately
                        save_user_reminders_to_file()
                        
                        response_text += f"\n\n(Reminder set for {time_str} {TIMEZONE_LABEL} 😊)"
                    except Exception as e:
                        print(f"Reminder error: {e}")

        except Exception as e:
            print("Error:", e)
            response_text = "I got a bit confused. Could you say that again? 😅"

    resp.message(response_text)
    return str(resp)

# ────────────────────────────────────────────────
#                RUN SERVER
# ────────────────────────────────────────────────

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000, debug=True)