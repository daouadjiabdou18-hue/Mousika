import os
import sys

# ========== التحقق من المتغيرات قبل كل شيء ==========
BOT_TOKEN = os.environ.get("BOT_TOKEN", "").strip()
FISH_AUDIO_API_KEY = os.environ.get("FISH_AUDIO_API_KEY", "").strip()
ADMIN_ID = os.environ.get("ADMIN_ID", "0").strip()

print("=" * 50)
print("🔍 Checking environment variables...")
print(f"BOT_TOKEN exists: {'Yes' if BOT_TOKEN else 'No'}")
print(f"BOT_TOKEN length: {len(BOT_TOKEN)}")
print(f"FISH_AUDIO_API_KEY exists: {'Yes' if FISH_AUDIO_API_KEY else 'No'}")
print(f"ADMIN_ID: {ADMIN_ID}")
print("=" * 50)

if not BOT_TOKEN:
    print("❌ ERROR: BOT_TOKEN is not set!")
    print("Please add BOT_TOKEN to Railway Variables")
    sys.exit(1)

if ":" not in BOT_TOKEN:
    print("❌ ERROR: BOT_TOKEN is invalid!")
    print("Token should be like: 123456789:ABCdefGHIjklMNOpqrsTUVwxyz")
    sys.exit(1)

print("✅ BOT_TOKEN is valid, starting bot...")

# ========== بقية الاستيرادات ==========
import asyncio
import logging
import tempfile
import aiosqlite
from datetime import datetime
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    Application, CommandHandler, CallbackQueryHandler,
    MessageHandler, filters, ContextTypes, ConversationHandler
)
import aiohttp

# ========== الإعدادات ==========
MAX_DAILY_REQUESTS = 10

# ========== لوحات المفاتيح ==========
def main_menu_keyboard():
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("🎙️ تحويل نص لصوت", callback_data="tts")],
        [InlineKeyboardButton("❓ المساعدة", callback_data="help")]
    ])

# ========== قاعدة البيانات ==========
class Database:
    def __init__(self, db_path="bot.db"):
        self.db_path = db_path
    
    async def init(self):
        async with aiosqlite.connect(self.db_path) as db:
            await db.execute("""
                CREATE TABLE IF NOT EXISTS users (
                    user_id INTEGER PRIMARY KEY,
                    username TEXT,
                    daily_count INTEGER DEFAULT 0,
                    last_request DATE,
                    total_requests INTEGER DEFAULT 0
                )
            """)
            await db.commit()
    
    async def add_user(self, user_id, username, first_name):
        async with aiosqlite.connect(self.db_path) as db:
            await db.execute(
                "INSERT OR IGNORE INTO users (user_id, username, first_name) VALUES (?, ?, ?)",
                (user_id, username, first_name)
            )
            await db.commit()
    
    async def check_daily_limit(self, user_id, limit):
        today = datetime.now().date()
        async with aiosqlite.connect(self.db_path) as db:
            async with db.execute("SELECT daily_count, last_request FROM users WHERE user_id = ?", (user_id,)) as c:
                row = await c.fetchone()
                if not row:
                    return True
                count, last = row
                if last != today.isoformat():
                    await db.execute("UPDATE users SET daily_count = 0, last_request = ? WHERE user_id = ?", (today.isoformat(), user_id))
                    await db.commit()
                    return True
                return count < limit
    
    async def increment_usage(self, user_id):
        today = datetime.now().date()
        async with aiosqlite.connect(self.db_path) as db:
            await db.execute(
                "UPDATE users SET daily_count = daily_count + 1, total_requests = total_requests + 1, last_request = ? WHERE user_id = ?",
                (today.isoformat(), user_id)
            )
            await db.commit()

# ========== Fish Audio ==========
class FishAudioService:
    def __init__(self):
        self.key = FISH_AUDIO_API_KEY
        self.url = "https://api.fish.audio/v1/tts"
    
    async def text_to_speech(self, text):
        if not self.key:
            return None
        headers = {"Authorization": f"Bearer {self.key}", "Content-Type": "application/json"}
        payload = {"text": text, "format": "mp3", "latency": "normal"}
        
        async with aiohttp.ClientSession() as s:
            async with s.post(self.url, json=payload, headers=headers, timeout=30) as r:
                if r.status == 200:
                    return await r.read()
                return None

# ========== البوت ==========
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

TTS_TEXT = 0

class AIBot:
    def __init__(self):
        self.db = Database()
        self.fish = FishAudioService()
    
    async def start(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        user = update.effective_user
        await self.db.add_user(user.id, user.username or "", user.first_name or "")
        
        await update.message.reply_text(
            f"🤖 أهلاً {user.first_name}!\n\n"
            "🎙️ أرسل نصاً لتحويله لصوت\n"
            f"📊 {MAX_DAILY_REQUESTS} طلبات/يوم",
            reply_markup=main_menu_keyboard()
        )
    
    async def button(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        query = update.callback_query
        await query.answer()
        data = query.data
        
        if data == "tts":
            await query.edit_message_text("📝 أرسل النص:")
            return TTS_TEXT
        elif data == "help":
            await query.edit_message_text("📝 أرسل أي نص", reply_markup=main_menu_keyboard())
        
        return ConversationHandler.END
    
    async def handle_tts(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        user_id = update.effective_user.id
        text = update.message.text
        
        if len(text) > 500:
            await update.message.reply_text("❌ طويل جداً!")
            return TTS_TEXT
        
        if not await self.db.check_daily_limit(user_id, MAX_DAILY_REQUESTS):
            await update.message.reply_text("❌ تجاوزت الحد!")
            return ConversationHandler.END
        
        msg = await update.message.reply_text("⏳ جاري التحويل...")
        
        try:
            audio = await self.fish.text_to_speech(text)
            if audio:
                with tempfile.NamedTemporaryFile(suffix=".mp3", delete=False) as tmp:
                    tmp.write(audio)
                    tmp_path = tmp.name
                
                with open(tmp_path, "rb") as f:
                    await update.message.reply_voice(f, reply_markup=main_menu_keyboard())
                
                os.unlink(tmp_path)
                await self.db.increment_usage(user_id)
                await msg.delete()
            else:
                await msg.edit_text("❌ فشل التحويل. تحقق من FISH_AUDIO_API_KEY")
        except Exception as e:
            await msg.edit_text(f"❌ خطأ: {str(e)}")
        
        return ConversationHandler.END

def main():
    bot = AIBot()
    app = Application.builder().token(BOT_TOKEN).build()
    
    app.add_handler(CommandHandler("start", bot.start))
    
    app.add_handler(ConversationHandler(
        entry_points=[CallbackQueryHandler(bot.button, pattern="^tts$")],
        states={TTS_TEXT: [MessageHandler(filters.TEXT & ~filters.COMMAND, bot.handle_tts)]},
        fallbacks=[CommandHandler("cancel", lambda u,c: u.message.reply_text("❌ إلغاء"))]
    ))
    
    app.add_handler(CallbackQueryHandler(bot.button, pattern="^(help|back_main)"))
    
    app.post_init = lambda app: bot.db.init()
    
    print("✅ Bot started successfully!")
    app.run_polling()

if __name__ == "__main__":
    main()
