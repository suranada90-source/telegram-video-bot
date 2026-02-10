import logging
import threading
import uuid
import json
import os
import asyncio
from flask import Flask, render_template_string, request, jsonify
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup, WebAppInfo
from telegram.constants import ParseMode
from telegram.ext import ApplicationBuilder, ContextTypes, CommandHandler, MessageHandler, CallbackQueryHandler, filters

# --- CONFIGURATION ---
TOKEN = TOKEN = os.environ.get("BOT_TOKEN")

# වැදගත්: Hugging Face Space එක හැදුවාම ලැබෙන URL එක මෙතනට දාන්න.
# දැනට මේක හිස්ව තියන්න, Space එක හැදුවට පස්සේ අපි මේක Update කරමු.
# Format: https://USERNAME-SPACE_NAME.hf.space
WEB_APP_URL = "https://YOUR_USERNAME-SPACE_NAME.hf.space"

ADMIN_ID = 6240794508
BOT_USERNAME = "sara2026_bot"

# --- AD LINKS ---
AD_LINK_1 = "https://otieu.com/4/10295571"
AD_LINK_2 = "https://www.effectivegatecpm.com/zi8sezrcn?key=87bd75d5ef8fc716516e24f598f71cee"

# --- GLOBAL VARIABLES ---
bot_app = None
bot_loop = None

# --- DATABASE ---
DB_FILE = "video_db.json"
video_storage = {}
verified_users = {}

if os.path.exists(DB_FILE):
    try:
        with open(DB_FILE, 'r') as f:
            video_storage = json.load(f)
        print(f"✅ Loaded {len(video_storage)} videos.")
    except Exception as e:
        print(f"❌ Error loading DB: {e}")

def save_database():
    try:
        with open(DB_FILE, 'w') as f:
            json.dump(video_storage, f)
    except Exception as e:
        print(f"❌ Error saving DB: {e}")

# --- FLASK SERVER ---
app = Flask(__name__)

HTML_TEMPLATE = """
<!DOCTYPE html>
<html>
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Verification</title>
    <script src="https://telegram.org/js/telegram-web-app.js"></script>
    <script src="https://cdn.tailwindcss.com"></script>
    <style>
        body { background: #121212; color: white; display: flex; flex-direction: column; align-items: center; justify-content: center; height: 100vh; font-family: sans-serif; padding: 20px; text-align: center; }
        .btn {
            background: #e11d48; color: white; font-weight: bold; padding: 15px 30px;
            border-radius: 12px; border: none; cursor: pointer; margin-top: 20px;
            font-size: 18px; width: 80%;
        }
        .btn:active { transform: scale(0.95); }
    </style>
</head>
<body>

    <h1 id="title" class="text-xl font-bold mb-4">Click to Unlock</h1>
    <p class="text-gray-400 mb-6">Please open the link to verify.</p>

    <!-- Button is always visible now -->
    <button id="adBtn" class="btn">
        🔴 OPEN LINK
    </button>

    <p id="status" class="mt-4 text-yellow-500 hidden">Checking...</p>

    <script>
        const tg = window.Telegram.WebApp;
        tg.expand();

        const urlParams = new URLSearchParams(window.location.search);
        const videoId = urlParams.get('id');
        const step = urlParams.get('step') || '1';

        const userId = tg.initDataUnsafe.user ? tg.initDataUnsafe.user.id : null;

        const link1 = "{{ link1 }}";
        const link2 = "{{ link2 }}";

        let targetLink = link1;
        let btnText = "🔴 OPEN LINK";

        if (step === '2') {
            targetLink = link2;
            btnText = "🎬 WATCH VIDEO";
        }

        const btn = document.getElementById('adBtn');
        btn.innerText = btnText;

        btn.onclick = function() {
            // 1. Ad Link Open karanawa (Manual Click nisa Block wenne na)
            tg.openLink(targetLink);

            btn.style.display = 'none';
            document.getElementById('status').style.display = 'block';
            document.getElementById('status').innerText = "Verifying...";

            // 2. Thathpara 8k idala Server ekata kiyanawa (Ad eka Load wenna Time denawa)
            setTimeout(() => {
                fetch('/submit', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({
                        user_id: userId,
                        video_id: videoId,
                        step: step
                    })
                }).then(response => {
                    document.getElementById('status').innerText = "✅ Verified!";
                    setTimeout(() => {
                        tg.close();
                    }, 1000);
                }).catch(error => {
                    console.error('Error:', error);
                    document.getElementById('status').innerText = "Error! Try again.";
                    btn.style.display = 'block';
                });
            }, 8000); // 8 Seconds Delay
        };
    </script>
</body>
</html>
"""

@app.route('/')
def index():
    return render_template_string(HTML_TEMPLATE, link1=AD_LINK_1, link2=AD_LINK_2)

@app.route('/submit', methods=['POST'])
def submit():
    data = request.json
    user_id = data.get('user_id')
    video_id = data.get('video_id')
    step = data.get('step')

    print(f"🔄 Signal Received: User={user_id}, Step={step}")

    if bot_loop and bot_app:
        asyncio.run_coroutine_threadsafe(process_verification(user_id, video_id, step), bot_loop)
        return jsonify({"status": "success"})
    else:
        return jsonify({"status": "error", "message": "Bot not ready"}), 500

def run_flask():
    # Wadagath: Hugging Face sandaha Port 7860 bawitha kala yuthumai
    app.run(host='0.0.0.0', port=7860)

# --- TELEGRAM BOT LOGIC ---
logging.basicConfig(level=logging.INFO)

async def process_verification(user_id, vid_id, step):
    if not user_id: return

    try:
        if step == '1':
            if user_id not in verified_users:
                verified_users[user_id] = []
            if str(vid_id) not in verified_users[user_id]:
                verified_users[user_id].append(str(vid_id))

            await bot_app.bot.send_message(
                chat_id=user_id,
                text="✅ **Step 1 Complete!**\nNow click the 2nd button to watch the video.",
                parse_mode=ParseMode.MARKDOWN
            )

        elif step == '2':
            is_verified = False
            if user_id in verified_users and str(vid_id) in verified_users[user_id]:
                is_verified = True

            if is_verified:
                file_id = video_storage.get(vid_id)
                if file_id:
                    await bot_app.bot.send_message(chat_id=user_id, text="🎉 **Success! Sending Video...**")
                    await bot_app.bot.send_video(
                        chat_id=user_id,
                        video=file_id,
                        caption="Here is your video!",
                        protect_content=True
                    )
                else:
                    await bot_app.bot.send_message(chat_id=user_id, text="❌ Video not found in database.")
            else:
                await bot_app.bot.send_message(chat_id=user_id, text="⚠️ **Please complete Step 1 first!**")

    except Exception as e:
        print(f"❌ Async Error: {e}")

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    global bot_loop
    if bot_loop is None:
        bot_loop = asyncio.get_running_loop()
        print("✅ Bot Loop Captured!")

    if context.args and context.args[0].startswith('v_'):
        vid_id = context.args[0].replace('v_', '')

        link_1 = f"{WEB_APP_URL}?id={vid_id}&step=1"
        link_2 = f"{WEB_APP_URL}?id={vid_id}&step=2"

        keyboard = [
            [InlineKeyboardButton("🔴 1. Click to Unlock", web_app=WebAppInfo(url=link_1))],
            [InlineKeyboardButton("🎬 2. Get Video", web_app=WebAppInfo(url=link_2))]
        ]

        await update.message.reply_text(
            "🔒 **LOCKED CONTENT**\n\nComplete both steps to unlock the video.",
            parse_mode=ParseMode.MARKDOWN,
            reply_markup=InlineKeyboardMarkup(keyboard)
        )
    else:
        await update.message.reply_text(f"👋 Bot is running!\nID: `{update.effective_user.id}`", parse_mode=ParseMode.MARKDOWN)

async def handle_video_upload(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    if user_id != ADMIN_ID: return

    video = update.message.video or update.message.document
    if not video: return

    vid_id = str(uuid.uuid4())[:8]
    video_storage[vid_id] = video.file_id
    save_database()

    bot_link = f"https://t.me/{BOT_USERNAME}?start=v_{vid_id}"

    await update.message.reply_text(
        f"✅ **Video Saved!**\n\nLink: `{bot_link}`",
        parse_mode=ParseMode.MARKDOWN
    )

if __name__ == '__main__':
    flask_thread = threading.Thread(target=run_flask)
    flask_thread.daemon = True
    flask_thread.start()

    application = ApplicationBuilder().token(TOKEN).build()
    bot_app = application

    application.add_handler(CommandHandler('start', start))
    application.add_handler(MessageHandler(filters.VIDEO | filters.Document.ALL, handle_video_upload))

    print("Bot is running...")
    application.run_polling()