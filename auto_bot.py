# auto_bot.py
# Telegram Auto Response Bot for Trading Groups + Live Prices (BTC, ETH, BNB, SOL, XAU/USD) via yfinance

import warnings
warnings.simplefilter(action='ignore', category=FutureWarning)
warnings.simplefilter(action='ignore', category=UserWarning)

import json
import yfinance as yf
import datetime
import asyncio
from telegram import Update
from telegram.ext import Application, MessageHandler, ChatMemberHandler, CommandHandler, filters, ContextTypes

# ✅ Bot token + group ID
TOKEN = "YOUR_BOT_TOKEN_HERE"
GROUP_ID = -1001234567890

# Market tickers
TICKERS = {
    "BTC": "BTC-USD",
    "ETH": "ETH-USD",
    "BNB": "BNB-USD",
    "SOL": "SOL-USD",
    "XAU": "GC=F"  # Gold futures
}

# File to store last prices
PRICES_FILE = "prices.json"

# Track last prices
last_prices = {}

# 🔹 Load last prices from JSON
def load_last_prices():
    try:
        with open(PRICES_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        return {}

# 🔹 Save last prices to JSON
def save_last_prices(prices):
    try:
        with open(PRICES_FILE, "w", encoding="utf-8") as f:
            json.dump(prices, f, indent=4)
    except Exception as e:
        print(f"Error saving prices.json: {e}")

# Load responses from JSON
def load_responses():
    try:
        with open("responses.json", "r", encoding="utf-8") as f:
            return json.load(f)
    except FileNotFoundError:
        default_data = {
            "hello": "👋 Welcome to our Trading Group! Type 'help' for commands.",
            "help": "📌 Commands:\n- /price: Check live prices\n- deposit: How to deposit funds\n- withdraw: Withdrawal guide",
            "_welcome": "👋 Welcome {name} to our Trading Group!",
            "_reload_success": "🔄 Responses reloaded successfully!"
        }
        with open("responses.json", "w", encoding="utf-8") as f:
            json.dump(default_data, f, indent=4, ensure_ascii=False)
        return default_data

responses = load_responses()
last_prices = load_last_prices()  # ✅ Load saved prices at startup

# Fetch live market prices with arrows
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
                if current_price > last_prices[name]:
                    arrow = " 🔼"
                elif current_price < last_prices[name]:
                    arrow = " 🔽"
                else:
                    arrow = " ➡️"

            last_prices[name] = current_price
            prices[name] = (current_price, arrow)

        except Exception as e:
            print(f"Error fetching {ticker}: {e}")
            prices[name] = (None, " ❓")

    save_last_prices(last_prices)  # ✅ Save updated prices
    return prices

# Format market update message
def format_market_message(prices, title="💹 Live Market Prices"):
    now = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    message = f"{title} ({now}):\n\n"
    for coin, (price, arrow) in prices.items():
        if price is not None:
            symbol = "💰" if coin=="BTC" else "💎" if coin=="ETH" else "🟡" if coin=="BNB" else "🟣" if coin=="SOL" else "🏅"
            message += f"{symbol} {coin}/USD: ${price:,.2f}{arrow}\n"
        else:
            message += f"⚠️ {coin}/USD: N/A{arrow}\n"
    # ✅ Add safety message at the end
    message += "\n🚨 Trade Safely!"
    return message

# Send scheduled updates
async def send_market_update(app: Application):
    prices = get_market_prices()
    message = format_market_message(prices, "📊 Market Update")
    await app.bot.send_message(chat_id=GROUP_ID, text=message)

# Background scheduler
async def schedule_updates(app: Application):
    target_times = [(9, 0), (12, 0), (18, 0)]
    sent_today = set()
    while True:
        now = datetime.datetime.now()
        for hour, minute in target_times:
            if now.hour == hour and now.minute == minute:
                key = (now.date(), hour, minute)
                if key not in sent_today:
                    await send_market_update(app)
                    sent_today.add(key)
        if now.hour == 0 and now.minute == 0:
            sent_today.clear()
        await asyncio.sleep(30)

# Handle /price
async def handle_price_request(update: Update, context: ContextTypes.DEFAULT_TYPE):
    prices = get_market_prices()
    message = format_market_message(prices)
    await update.message.reply_text(message)

# Auto replies
async def auto_reply(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.message is None or update.message.text is None:
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

# Welcome new members
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

# Reload /reload
async def reload_responses(update: Update, context: ContextTypes.DEFAULT_TYPE):
    global responses
    responses = load_responses()
    await update.message.reply_text(responses.get("_reload_success", "Reloaded!"))

# Main bot
def main():
    app = Application.builder().token(TOKEN).build()
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, auto_reply))
    app.add_handler(ChatMemberHandler(welcome, ChatMemberHandler.CHAT_MEMBER))
    app.add_handler(CommandHandler("price", handle_price_request))
    app.add_handler(CommandHandler("reload", reload_responses))

    # Start scheduler properly
    async def on_startup(_):
        asyncio.create_task(schedule_updates(app))
    app.post_init = on_startup

    print("🤖 Bot is running... Press Ctrl+C to stop.")
    app.run_polling()

if __name__ == "__main__":
    main()
