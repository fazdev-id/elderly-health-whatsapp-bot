# Elderly Health Assistant – WhatsApp Chatbot

A low-budget, academic prototype of a WhatsApp chatbot designed specifically for elderly users (60+).  
It provides friendly conversations, medication/hydration reminders, emergency alerts, and daily scheduled health tips.

Built for portfolio demonstration (simulated client: India, focus on elderly healthcare).

## Features

- Natural, warm conversations powered by OpenAI (gpt-4.1-nano – very cost-effective)
- Custom reminders set by user (absolute time or "in X minutes")
- Daily recurring reminders loaded from `schedules.json` (e.g., medicine, water, meals)
- Emergency keyword detection – instantly alerts family/contact
- Configurable timezone (default: WIB/UTC+7)
- Full logging in terminal: shows all active reminders with date & time
- Supports multiple reminders per user
- Always replies in simple English (configurable via prompt)

## Tech Stack

- **Backend**: Python + Flask
- **WhatsApp Integration**: Twilio Sandbox (free for testing)
- **AI**: OpenAI API (gpt-4.1-nano)
- **Scheduler**: APScheduler (for both custom & daily reminders)
- **Configuration**: `.env` + `schedules.json`

## Prerequisites

- Python 3.10+
- Twilio account with WhatsApp Sandbox enabled
- OpenAI API key with sufficient credits
- ngrok (free) for local testing

## Installation & Setup

1. Clone the repository:
   ```bash
   git clone https://github.com/yourusername/elderly-health-whatsapp-bot.git
   cd elderly-health-whatsapp-bot
   ```

2. Create and activate virtual environment:
   ```bash
   python -m venv venv
   source venv/bin/activate    # On Windows: venv\Scripts\activate
   ```

3. Install dependencies:
   ```bash
   pip install -r requirements.txt
   ```

4. Create `.env` file from `.env.example` and fill your credentials:
   ```
   TWILIO_ACCOUNT_SID=ACxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx
   TWILIO_AUTH_TOKEN=xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx
   TWILIO_WHATSAPP_NUMBER=whatsapp:+14155238886
   OPENAI_API_KEY=sk-xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx
   EMERGENCY_CONTACT=whatsapp:+628xxxxxxxxxx
   UTC_OFFSET_HOURS=7
   TIMEZONE_LABEL=WIB
   ```

5. (Optional) Customize daily reminders in `schedules.json`

6. Run the server:
   ```bash
   python app.py
   ```

7. Expose localhost to the internet using ngrok:
   ```bash
   ngrok http 5000
   ```

8. In Twilio Console → WhatsApp Sandbox → set "When a message comes in" to:
   ```
   https://xxxx.ngrok-free.app/webhook
   Method: POST
   ```

9. Join the sandbox from your phone: send `join <your-sandbox-code>` to the Twilio number

## How to Test

- Normal chat: "How are you today?"
- Set reminder: "Remind me take medicine at 21:00" or "Remind me drink water in 10 minutes"
- Emergency: Send "help" or "emergency"
- Check terminal logs: see active reminders with full date/time

## Demo

(Video Demo Coming Soon)

### Screenshots

(Screenshots coming soon)

## Limitations & Future Ideas

- Custom reminders are in-memory (lost on restart) → can add JSON/SQLite persistence
- Daily reminders sent only to emergency contact → can extend to all known users
- No user authentication or multi-timezone support yet

## License

MIT License – free to use, modify, and learn from.

Made with ❤️ by FazDev (February 2026)  
For academic/portfolio purposes.
```