import asyncio
import logging
import tempfile
import os
import aiosqlite
from datetime import datetime
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    Application, CommandHandler, CallbackQueryHandler,
    MessageHandler, filters, ContextTypes, ConversationHandler
)
import aiohttp

# ========== الإعدادات ==========
BOT_TOKEN = os.getenv("BOT_TOKEN", "")
ADMIN_ID = int(os.getenv("ADMIN_ID", "0"))
FISH_AUDIO_API_KEY = os.getenv("FISH_AUDIO_API_KEY", "")
TWOSHOT_API_KEY = os.getenv("TWOSHOT_API_KEY", "")
MAX_DAILY_REQUESTS = 10

# ========== لوحات المفاتيح ==========
def main_menu_keyboard():
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("🎙️ تحويل نص لصوت", callback_data="tts"),
         InlineKeyboardButton("🎵 توليد أغنية", callback_data="music")],
        [InlineKeyboardButton("🎭 استنساخ صوتي", callback_data="clone_voice"),
         InlineKeyboardButton("📊 احصائياتي", callback_data="my_stats")],
        [InlineKeyboardButton("❓ المساعدة", callback_data="help")]
    ])

def music_genres_keyboard():
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("🎸 روك", callback_data="genre_rock"),
         InlineKeyboardButton("🎹 بوب", callback_data="genre_pop")],
        [InlineKeyboardButton("🎤 هيب هوب", callback_data="genre_hip-hop"),
         InlineKeyboardButton("🎻 كلاسيكية", callback_data="genre_classical")],
        [InlineKeyboardButton("🔙 رجوع", callback_data="back_main")]
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
                    first_name TEXT,
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
    
    async def get_user(self, user_id):
        async with aiosqlite.connect(self.db_path) as db:
            db.row_factory = aiosqlite.Row
            async with db.execute("SELECT * FROM users WHERE user_id = ?", (user_id,)) as c:
                row = await c.fetchone()
                return dict(row) if row else None
    
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
    
    async def get_stats(self):
        async with aiosqlite.connect(self.db_path) as db:
            async with db.execute("SELECT COUNT(*) FROM users") as c:
                users = (await c.fetchone())[0]
            return {"total_users": users, "total_requests": 0}

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

TTS_TEXT, MUSIC_PROMPT, MUSIC_GENRE, CLONE_VOICE = range(4)

class AIBot:
    def __init__(self):
        self.db = Database()
        self.fish = FishAudioService()
    
    async def start(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        user = update.effective_user
        await self.db.add_user(user.id, user.username or "", user.first_name or "")
        
        await update.message.reply_text(
            f"🤖 أهلاً {user.first_name}!\n\n"
            "🎙️ تحويل نص ← صوت\n"
            "🎵 توليد أغاني\n"
            f"📊 {MAX_DAILY_REQUESTS} طلبات/يوم",
            reply_markup=main_menu_keyboard()
        )
    
    async def button(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        query = update.callback_query
        await query.answer()
        data = query.data
        
        if data == "tts":
            await query.edit_message_text("📝 أرسل النص:", reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 رجوع", callback_data="back_main")]]))
            return TTS_TEXT
            
        elif data == "music":
            await query.edit_message_text("🎵 اختر النوع:", reply_markup=music_genres_keyboard())
            return MUSIC_GENRE
            
        elif data == "my_stats":
            user = await self.db.get_user(update.effective_user.id)
            text = f"📊 طلباتك: {user['total_requests'] if user else 0}\nاليوم: {user['daily_count'] if user else 0}/{MAX_DAILY_REQUESTS}"
            await query.edit_message_text(text, reply_markup=main_menu_keyboard())
            
        elif data == "help":
            await query.edit_message_text("📝 أرسل نصاً لتحويله\n🎵 اختر نوعاً ثم أرسل وصفاً", reply_markup=main_menu_keyboard())
            
        elif data == "back_main":
            await query.edit_message_text("القائمة:", reply_markup=main_menu_keyboard())
            
        elif data.startswith("genre_"):
            context.user_data["genre"] = data.replace("genre_", "")
            await query.edit_message_text("📝 أرسل وصف الأغنية:")
            return MUSIC_PROMPT
        
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
                await msg.edit_text("❌ فشل التحويل")
        except Exception as e:
            await msg.edit_text(f"❌ خطأ: {str(e)}")
        
        return ConversationHandler.END
    
    async def handle_music(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        await update.message.reply_text("🎵 قريباً!", reply_markup=main_menu_keyboard())
        return ConversationHandler.END
    
    async def cancel(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        await update.message.reply_text("❌ تم الإلغاء", reply_markup=main_menu_keyboard())
        return ConversationHandler.END

# ========== التشغيل ==========
def main():
    bot = AIBot()
    app = Application.builder().token(8762789105:AAHpHmY9sWUZXj38yXzYMtaWAJkXV9dysFo).build()
    
    app.add_handler(CommandHandler("start", bot.start))
    
    app.add_handler(ConversationHandler(
        entry_points=[CallbackQueryHandler(bot.button, pattern="^tts$")],
        states={TTS_TEXT: [MessageHandler(filters.TEXT & ~filters.COMMAND, bot.handle_tts)]},
        fallbacks=[CommandHandler("cancel", bot.cancel)]
    ))
    
    app.add_handler(ConversationHandler(
        entry_points=[CallbackQueryHandler(bot.button, pattern="^music$")],
        states={
            MUSIC_GENRE: [CallbackQueryHandler(bot.button, pattern="^genre_")],
            MUSIC_PROMPT: [MessageHandler(filters.TEXT & ~filters.COMMAND, bot.handle_music)]
        },
        fallbacks=[CommandHandler("cancel", bot.cancel)]
    ))
    
    app.add_handler(CallbackQueryHandler(bot.button, pattern="^(my_stats|help|back_main)"))
    
    app.post_init = lambda app: bot.db.init()
    
    print("🤖 Bot running...")
    app.run_polling()

if __name__ == "__main__":
    main()
