# auto_bot_webhook.py
# Telegram Auto Response Bot for Trading Groups + Live Prices (BTC, ETH, BNB, SOL, XAU/USD) via yfinance
# Webhook version for cloud deployment (Railway)

import os
import json
import datetime
import asyncio
import yfinance as yf
from telegram import Update, Bot
from telegram.ext import Application, CommandHandler, MessageHandler, ChatMemberHandler, ContextTypes, filters

# =========================
# Load bot credentials from environment variables
# =========================
TOKEN = os.getenv("TOKEN")
WEBHOOK_URL = os.getenv("WEBHOOK_URL")  # e.g., https://your-app.up.railway.app/{TOKEN}
GROUP_ID = os.getenv("GROUP_ID")

if not TOKEN or not WEBHOOK_URL or not GROUP_ID:
    raise ValueError("TOKEN, WEBHOOK_URL, or GROUP_ID not set in environment variables!")

GROUP_ID = int(GROUP_ID)

# =========================
# File paths
# =========================
PRICES_FILE = "prices.json"
RESPONSES_FILE = "responses.json"

# =========================
# Ensure JSON files exist
# =========================
if not os.path.exists(RESPONSES_FILE):
    default_responses = {
        "hello": "👋 Welcome to our Trading Group! Type 'help' for commands.",
        "help": "📌 Commands:\n- /price: Check live prices\n- deposit: How to deposit funds\n- withdraw: Withdrawal guide",
        "_welcome": "👋 Welcome {name} to our Trading Group!",
        "_reload_success": "🔄 Responses reloaded successfully!"
    }
    with open(RESPONSES_FILE, "w", encoding="utf-8") as f:
        json.dump(default_responses, f, indent=4, ensure_ascii=False)

if not os.path.exists(PRICES_FILE):
    with open(PRICES_FILE, "w", encoding="utf-8") as f:
        json.dump({}, f)

# =========================
# Market tickers
# =========================
TICKERS = {
    "BTC": "BTC-USD",
    "ETH": "ETH-USD",
    "BNB": "BNB-USD",
    "SOL": "SOL-USD",
    "XAU": "GC=F"
}

# =========================
# Load last prices
# =========================
def load_last_prices():
    try:
        with open(PRICES_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    except:
        return {}

def save_last_prices(prices):
    with open(PRICES_FILE, "w", encoding="utf-8") as f:
        json.dump(prices, f, indent=4)

last_prices = load_last_prices()

# =========================
# Load responses
# =========================
def load_responses():
    try:
        with open(RESPONSES_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    except:
        return {}

responses = load_responses()

# =========================
# Fetch live market prices
# =========================
def get_market_prices():
    global last_prices
    prices = {}
    for name, ticker in TICKERS.items():
        try:
            df = yf.Ticker(ticker).history(period="1d", interval="1m")
            if df.empty:
                raise ValueError("No data returned")
            current_price = round(float(df["Close"].iloc[-1]), 2)

            # Arrow logic
            if name not in last_prices:
                arrow = " ➡️"
            else:
                arrow = " 🔼" if current_price > last_prices[name] else " 🔽" if current_price < last_prices[name] else " ➡️"

            last_prices[name] = current_price
            prices[name] = (current_price, arrow)
        except Exception as e:
            print(f"Error fetching {ticker}: {e}")
            prices[name] = (None, " ❓")
    save_last_prices(last_prices)
    return prices

# =========================
# Format market message
# =========================
def format_market_message(prices, title="💹 Live Market Prices"):
    now = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    message = f"{title} ({now}):\n\n"
    for coin, (price, arrow) in prices.items():
        if price is not None:
            symbol = "💰" if coin=="BTC" else "💎" if coin=="ETH" else "🟡" if coin=="BNB" else "🟣" if coin=="SOL" else "🏅"
            message += f"{symbol} {coin}/USD: ${price:,.2f}{arrow}\n"
        else:
            message += f"⚠️ {coin}/USD: N/A{arrow}\n"
    message += "\n🚨 Trade Safely!"
    return message

# =========================
# Telegram Handlers
# =========================
async def handle_price_request(update: Update, context: ContextTypes.DEFAULT_TYPE):
    prices = get_market_prices()
    message = format_market_message(prices)
    await update.message.reply_text(message)

async def auto_reply(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not update.message or not update.message.text:
        return
    msg = update.message.text.lower()
    if "price" in msg or msg.startswith("/price"):
        await handle_price_request(update, context)
        return
    for keyword, reply in responses.items():
        if keyword.startswith("_"):
            continue
        if keyword in msg:
            await update.message.reply_text(reply)
            return

async def welcome(update: Update, context: ContextTypes.DEFAULT_TYPE):
    result = update.chat_member
    new_status = result.new_chat_member.status
    old_status = result.old_chat_member.status
    if old_status in ("left", "kicked") and new_status == "member":
        new_user = result.new_chat_member.user
        welcome_message = responses.get("_welcome", "👋 Welcome {name}!")
        welcome_message = welcome_message.replace("{name}", new_user.mention_html())
        await context.bot.send_message(
            chat_id=update.chat_member.chat.id,
            text=welcome_message,
            parse_mode="HTML"
        )

async def reload_responses(update: Update, context: ContextTypes.DEFAULT_TYPE):
    global responses
    responses = load_responses()
    await update.message.reply_text(responses.get("_reload_success", "Reloaded!"))

# =========================
# Scheduled updates
# =========================
async def scheduled_market_update(app: Application):
    target_times = [(9,0),(12,0),(18,0)]
    sent_today = set()
    while True:
        now = datetime.datetime.now()
        for hour, minute in target_times:
            key = (now.date(), hour, minute)
            if now.hour == hour and now.minute == minute and key not in sent_today:
                prices = get_market_prices()
                message = format_market_message(prices, "📊 Market Update")
                await app.bot.send_message(chat_id=GROUP_ID, text=message)
                sent_today.add(key)
        if now.hour == 0 and now.minute == 0:
            sent_today.clear()
        await asyncio.sleep(30)

# =========================
# Main
# =========================
def main():
    app = Application.builder().token(TOKEN).build()
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, auto_reply))
    app.add_handler(ChatMemberHandler(welcome, ChatMemberHandler.CHAT_MEMBER))
    app.add_handler(CommandHandler("price", handle_price_request))
    app.add_handler(CommandHandler("reload", reload_responses))

    # Start scheduled market updates
    async def on_startup(_):
        asyncio.create_task(scheduled_market_update(app))
    app.post_init = on_startup

    # Start webhook
    print("🤖 Bot is running with webhook...")
    app.run_webhook(
        listen="0.0.0.0",
        port=int(os.environ.get("PORT", 8443)),
        webhook_url=f"{WEBHOOK_URL}/{TOKEN}"
    )

if __name__ == "__main__":
    main()
