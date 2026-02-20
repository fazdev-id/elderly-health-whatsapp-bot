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
TWILIO_WHATSAPP_NUMBER = os.getenv("TWILIO_WHATSAPP_NUMBER", "whatsapp:+14155238886")  # default sandbox

OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")

EMERGENCY_CONTACT = os.getenv("EMERGENCY_CONTACT")  # e.g. whatsapp:+6281234567890

# Check required env vars
required_env = ["TWILIO_ACCOUNT_SID", "TWILIO_AUTH_TOKEN", "OPENAI_API_KEY", "EMERGENCY_CONTACT"]
missing = [var for var in required_env if not os.getenv(var)]
if missing:
    raise ValueError(f"Missing required environment variables: {', '.join(missing)}")

# ────────────────────────────────────────────────
#           TIMEZONE CONFIG – EASY TO CHANGE
# ────────────────────────────────────────────────
UTC_OFFSET_HOURS = int(os.getenv("UTC_OFFSET_HOURS", "7"))  # default WIB/UTC+7
TIMEZONE_LABEL = os.getenv("TIMEZONE_LABEL", "WIB")

# File for regular daily schedules
SCHEDULES_FILE = "schedules.json"

# ────────────────────────────────────────────────
#           GLOBAL VARIABLES
# ────────────────────────────────────────────────

twilio_client = Client(TWILIO_ACCOUNT_SID, TWILIO_AUTH_TOKEN)
openai_client = OpenAI(api_key=OPENAI_API_KEY)

# Custom reminders from chat (in-memory)
user_reminders = {}

# Scheduler for reminders
scheduler = BackgroundScheduler()
scheduler.start()

# ────────────────────────────────────────────────
#           LOAD REGULAR DAILY SCHEDULES FROM JSON
# ────────────────────────────────────────────────

def load_regular_schedules():
    """Load daily schedules from JSON and schedule them using APScheduler"""
    try:
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
                print(f"Scheduled daily reminder at {time_utc_str} UTC: {sched['message']}")
            except Exception as e:
                print(f"Error scheduling {sched}: {e}")

    except FileNotFoundError:
        print(f"File {SCHEDULES_FILE} not found. No regular schedules loaded.")
    except Exception as e:
        print(f"Error loading schedules: {e}")

def send_regular_reminder(message):
    """Send daily reminder to emergency contact (prototype)"""
    target_number = EMERGENCY_CONTACT
    send_whatsapp_message(target_number, message)
    print(f"Daily reminder sent to {target_number}: {message}")

# Load on startup
load_regular_schedules()

# ────────────────────────────────────────────────
#           HELPER FUNCTIONS
# ────────────────────────────────────────────────

def send_whatsapp_message(to_number, body):
    """Send WhatsApp message via Twilio"""
    try:
        twilio_client.messages.create(
            from_=TWILIO_WHATSAPP_NUMBER,
            body=body,
            to=to_number
        )
        print(f"Message sent to {to_number}: {body[:60]}...")
    except Exception as e:
        print(f"Failed to send to {to_number}: {e}")

def print_current_reminders():
    """Print all active custom reminders with full local date & time"""
    if not user_reminders:
        print("No custom reminders at the moment.")
        return

    print("\n=== ACTIVE CUSTOM REMINDERS (local time) ===")
    now_utc = datetime.now(timezone.utc)
    now_local = now_utc + timedelta(hours=UTC_OFFSET_HOURS)

    for user_number, reminders in user_reminders.items():
        print(f"User: {user_number}")
        if not reminders:
            print("  - No reminders")
            continue
        for idx, rem in enumerate(reminders, 1):
            local_time = rem["time"] + timedelta(hours=UTC_OFFSET_HOURS)
            local_str = local_time.strftime("%Y-%m-%d %H:%M") + f" {TIMEZONE_LABEL}"
            status = "PENDING" if local_time > now_local else "SHOULD HAVE BEEN SENT"
            print(f"  {idx}. [{status}] {local_str} → {rem['message']}")
    print("=======================================\n")

def check_and_send_reminders():
    """Check and send due custom reminders (times stored in UTC)"""
    now_utc = datetime.now(timezone.utc)
    for user_number, reminders in list(user_reminders.items()):
        remaining = []
        for rem in reminders:
            if rem["time"] <= now_utc:
                send_whatsapp_message(user_number, rem["message"])
                local_time_str = (rem["time"] + timedelta(hours=UTC_OFFSET_HOURS)).strftime("%Y-%m-%d %H:%M")
                print(f"Custom reminder sent to {user_number} at {local_time_str} {TIMEZONE_LABEL}: {rem['message']}")
                print_current_reminders()
            else:
                remaining.append(rem)
        user_reminders[user_number] = remaining

scheduler.add_job(check_and_send_reminders, 'interval', minutes=1)

# ────────────────────────────────────────────────
#                   MAIN WEBHOOK
# ────────────────────────────────────────────────

@app.route("/webhook", methods=["POST"])
def whatsapp_webhook():
    incoming_msg = request.values.get("Body", "").strip()
    from_number = request.values.get("From", "")
    profile_name = request.values.get("ProfileName", "User")

    print(f"\nMessage from {from_number} ({profile_name}): {incoming_msg}")
    print_current_reminders()

    resp = MessagingResponse()
    response_text = "Sorry, I didn't quite understand. Could you try again? 😊"

    lower_msg = incoming_msg.lower()

    # Emergency detection
    emergency_keywords = ["emergency", "help", "urgent", "pain", "chest pain", "can't breathe", "darurat", "tolong", "sakit dada"]
    if any(word in lower_msg for word in emergency_keywords):
        alert_text = f"!!! EMERGENCY ALERT !!!\nFrom: {profile_name} ({from_number})\nMessage: {incoming_msg}"
        send_whatsapp_message(EMERGENCY_CONTACT, alert_text)
        response_text = (
            "I've sent an urgent message to your emergency contact. "
            "Please stay calm. I'm here with you — what else can I do right now? ❤️"
        )

    else:
        try:
            now_utc = datetime.now(timezone.utc)
            current_user_time = now_utc + timedelta(hours=UTC_OFFSET_HOURS)
            current_str = current_user_time.strftime("%H:%M %Y-%m-%d") + f" {TIMEZONE_LABEL} (UTC{'+' if UTC_OFFSET_HOURS >= 0 else ''}{UTC_OFFSET_HOURS})"

            system_prompt = (
                f"The user is in timezone UTC{'+' if UTC_OFFSET_HOURS >= 0 else ''}{UTC_OFFSET_HOURS} ({TIMEZONE_LABEL}). "
                f"Current time for the user is {current_str}.\n"
                "Always base relative times (e.g. 'in 5 minutes', 'dalam 10 menit', 'at 3 pm') on THIS current time.\n"
                "Output the resulting local time as HH:MM in 24-hour format.\n"
                "\n"
                "You are a very kind, patient, and friendly health assistant for elderly people aged 60+.\n"
                "ALWAYS reply in simple, warm ENGLISH only — no matter what language the user uses.\n"
                "Do NOT use Indonesian or any other language unless explicitly asked.\n"
                "Use very easy words, short sentences, warm tone. Add emojis when it feels natural 😊.\n"
                "Never scare or worry the user. Always be supportive and offer more help.\n"
                "\n"
                "Your ENTIRE response MUST be valid JSON with this exact structure:\n"
                "{\n"
                '  "reply": "short, friendly message to send to the user",\n'
                '  "reminder": null  OR  {"time": "HH:MM" (24-hour format, e.g. "14:30"), "message": "reminder text to send later"}\n'
                "}\n"
                "Rules for 'reminder':\n"
                "- Set only if user clearly asks to set a reminder, alarm, or schedule.\n"
                "- 'time' MUST be the local HH:MM (24-hour) based on the current time provided above.\n"
                "- If relative time is given, calculate from the current time and output local HH:MM.\n"
                "- 'message' should be short, clear, and warm.\n"
                "- If no reminder is requested, use null.\n"
                "Output ONLY the JSON. No extra text, no markdown, no explanations."
            )

            completion = openai_client.chat.completions.create(
                model="gpt-4.1-nano",
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": incoming_msg}
                ],
                temperature=0.6,
                max_completion_tokens=200,
                response_format={"type": "json_object"}
            )

            raw_json = completion.choices[0].message.content.strip()
            parsed = json.loads(raw_json)

            response_text = parsed.get("reply", "Sorry, I didn't understand 😅. Could you say it again?")

            reminder_data = parsed.get("reminder")
            if reminder_data and isinstance(reminder_data, dict):
                time_str = reminder_data.get("time")
                msg = reminder_data.get("message", "Reminder from your assistant 😊")

                if time_str and re.match(r"^\d{2}:\d{2}$", time_str):
                    try:
                        hour, minute = map(int, time_str.split(":"))

                        now_utc = datetime.now(timezone.utc)
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

                        local_time_str = time_str
                        print(f"Custom reminder set for {from_number} at {local_time_str} {TIMEZONE_LABEL}: {msg}")
                        response_text += f"\n\n(Reminder set for {local_time_str} {TIMEZONE_LABEL} 😊)"
                        print_current_reminders()

                    except Exception as e:
                        print(f"Reminder error: {e}")
                        response_text += "\n\n(I tried to set the reminder but had a small issue 😅)"

        except json.JSONDecodeError as e:
            print(f"JSON parse error: {e}")
            response_text = "Sorry, something went wrong on my side 😅. Try again?"
        except Exception as e:
            print("OpenAI error:", e)
            response_text = "Sorry, I got a bit confused just now 😅. Could you please say it again?"

    resp.message(response_text)
    return str(resp)

# ────────────────────────────────────────────────

if __name__ == "__main__":
    print("Server running... Open another terminal and run: ngrok http 5000")
    app.run(host="0.0.0.0", port=5000, debug=True)