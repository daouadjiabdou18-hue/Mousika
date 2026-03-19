import asyncio
import logging
import tempfile
import os
from datetime import datetime

from telegram import Update, InlineKeyboardMarkup, InlineKeyboardButton
from telegram.ext import (
    Application, CommandHandler, CallbackQueryHandler,
    MessageHandler, filters, ContextTypes, ConversationHandler
)

from config import Config
from database import Database
from services.fish_audio import FishAudioService
from services.music_generator import MusicGenerator
from utils.keyboards import *
from utils.helpers import *

logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

TTS_TEXT, TTS_VOICE_SELECT, MUSIC_PROMPT, MUSIC_GENRE, CLONE_VOICE = range(5)

class AIBot:
    def __init__(self):
        self.db = Database()
        self.fish_audio = FishAudioService()
        self.music_gen = MusicGenerator()
    
    async def start(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        user = update.effective_user
        await self.db.add_user(user.id, user.username or "", user.first_name or "")
        
        welcome_text = (
            f"🤖 أهلاً {user.first_name}!\n\n"
            "🎙️ *بوت الذكاء الاصطناعي للصوت والموسيقى*\n\n"
            "✨ المميزات:\n"
            "• 🎙️ تحويل النص لصوت طبيعي\n"
            "• 🎵 توليد أغاني كاملة\n"
            "• 🎭 استنساخ صوتك الشخصي\n\n"
            f"📊 لديك *{Config.MAX_DAILY_REQUESTS}* طلبات مجانية يومياً"
        )
        
        await update.message.reply_text(
            welcome_text,
            reply_markup=main_menu_keyboard(),
            parse_mode="Markdown"
        )
    
    async def button_handler(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        query = update.callback_query
        await query.answer()
        data = query.data
        
        if data == "tts":
            await query.edit_message_text(
                "📝 أرسل النص (500 حرف max):",
                reply_markup=InlineKeyboardMarkup([[
                    InlineKeyboardButton("🔙 رجوع", callback_data="back_main")
                ]])
            )
            return TTS_TEXT
            
        elif data == "music":
            await query.edit_message_text("🎵 اختر النوع:", reply_markup=music_genres_keyboard())
            return MUSIC_GENRE
            
        elif data == "clone_voice":
            await query.edit_message_text(
                "🎭 أرسل تسجيل صوتي (10-30 ثانية):",
                reply_markup=InlineKeyboardMarkup([[
                    InlineKeyboardButton("🔙 رجوع", callback_data="back_main")
                ]])
            )
            return CLONE_VOICE
            
        elif data == "my_stats":
            await self.show_user_stats(update, context)
            
        elif data == "help":
            await self.show_help(update, context)
            
        elif data == "back_main":
            await query.edit_message_text("القائمة:", reply_markup=main_menu_keyboard())
            return ConversationHandler.END
            
        elif data.startswith("genre_"):
            genre = data.replace("genre_", "")
            context.user_data["genre"] = genre
            await query.edit_message_text(f"✅ النوع: {genre}\n📝 أرسل الوصف:")
            return MUSIC_PROMPT
            
        elif data.startswith("admin_"):
            await self.admin_handler(update, context, data)
            
        return ConversationHandler.END
    
    async def handle_tts(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        user_id = update.effective_user.id
        text = update.message.text
        
        if len(text) > 500:
            await update.message.reply_text("❌ طويل جداً!")
            return TTS_TEXT
        
        if not await self.db.check_daily_limit(user_id, Config.MAX_DAILY_REQUESTS):
            await update.message.reply_text("❌ تجاوزت الحد اليومي!")
            return ConversationHandler.END
        
        processing = await update.message.reply_text("⏳ جاري التوليد...")
        
        try:
            audio = await self.fish_audio.text_to_speech(text)
            if audio:
                with tempfile.NamedTemporaryFile(suffix=".mp3", delete=False) as tmp:
                    tmp.write(audio)
                    tmp_path = tmp.name
                
                with open(tmp_path, "rb") as f:
                    await update.message.reply_voice(f, reply_markup=main_menu_keyboard())
                
                os.unlink(tmp_path)
                await self.db.increment_usage(user_id)
                await processing.delete()
            else:
                await processing.edit_text("❌ فشل التوليد")
        except Exception as e:
            await processing.edit_text(f"❌ خطأ: {str(e)}")
        
        return ConversationHandler.END
    
    async def handle_music(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        user_id = update.effective_user.id
        prompt = update.message.text
        genre = context.user_data.get("genre", "pop")
        
        if not await self.db.check_daily_limit(user_id, Config.MAX_DAILY_REQUESTS):
            await update.message.reply_text("❌ تجاوزت الحد!")
            return ConversationHandler.END
        
        processing = await update.message.reply_text("🎵 جاري التوليد (قد يستغرق دقيقة)...")
        
        try:
            result = await self.music_gen.generate_with_twoshot(prompt, genre)
            if result:
                await update.message.reply_audio(
                    audio=result["audio_url"],
                    title="AI Song",
                    reply_markup=main_menu_keyboard()
                )
                await self.db.increment_usage(user_id)
                await processing.delete()
            else:
                await processing.edit_text("❌ فشل التوليد")
        except Exception as e:
            await processing.edit_text(f"❌ خطأ: {str(e)}")
        
        context.user_data.pop("genre", None)
        return ConversationHandler.END
    
    async def handle_clone(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        user_id = update.effective_user.id
        
        if not update.message.voice and not update.message.audio:
            await update.message.reply_text("❌ أرسل صوتاً!")
            return CLONE_VOICE
        
        file = await (update.message.voice or update.message.audio).get_file()
        processing = await update.message.reply_text("🎭 جاري الاستنساخ...")
        
        try:
            data = await file.download_as_bytearray()
            voice_id = await self.fish_audio.clone_voice(bytes(data), f"user_{user_id}")
            
            if voice_id:
                await self.db.save_cloned_voice(user_id, "My Voice", voice_id)
                await processing.edit_text("✅ تم الاستنساخ!", reply_markup=main_menu_keyboard())
            else:
                await processing.edit_text("❌ فشل الاستنساخ")
        except Exception as e:
            await processing.edit_text(f"❌ خطأ: {str(e)}")
        
        return ConversationHandler.END
    
    async def show_user_stats(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        user_id = update.effective_user.id
        user = await self.db.get_user(user_id)
        
        text = f"📊 إحصائياتك\n\nالطلبات: {user['total_requests']}\nاليوم: {user['daily_count']}/{Config.MAX_DAILY_REQUESTS}"
        await update.callback_query.edit_message_text(text, reply_markup=main_menu_keyboard())
    
    async def show_help(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        help_text = (
            "❓ المساعدة\n\n"
            "🎙️ تحويل نص: أرسل أي نص\n"
            "🎵 توليد أغنية: اختر النوع ثم الوصف\n"
            "🎭 استنساخ: أرسل تسجيل 10-30 ثانية\n\n"
            f"📊 الحد: {Config.MAX_DAILY_REQUESTS}/يوم"
        )
        await update.callback_query.edit_message_text(help_text, reply_markup=main_menu_keyboard())
    
    async def admin_handler(self, update: Update, context: ContextTypes.DEFAULT_TYPE, data: str):
        if update.effective_user.id != Config.ADMIN_ID:
            return
        
        if data == "admin_stats":
            stats = await self.db.get_stats()
            text = f"📊 إحصائيات\n\nالمستخدمين: {stats['total_users']}\nالطلبات: {stats['total_requests']}"
            await update.callback_query.edit_message_text(text)
    
    async def admin_cmd(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        if update.effective_user.id != Config.ADMIN_ID:
            return
        await update.message.reply_text("⚙️ لوحة التحكم", reply_markup=admin_keyboard())
    
    async def cancel(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        await update.message.reply_text("❌ تم الإلغاء", reply_markup=main_menu_keyboard())
        return ConversationHandler.END
    
    def setup(self, app: Application):
        app.add_handler(CommandHandler("start", self.start))
        app.add_handler(CommandHandler("admin", self.admin_cmd))
        
        tts_conv = ConversationHandler(
            entry_points=[CallbackQueryHandler(self.button_handler, pattern="^tts$")],
            states={TTS_TEXT: [MessageHandler(filters.TEXT & ~filters.COMMAND, self.handle_tts)]},
            fallbacks=[CommandHandler("cancel", self.cancel)]
        )
        app.add_handler(tts_conv)
        
        music_conv = ConversationHandler(
            entry_points=[CallbackQueryHandler(self.button_handler, pattern="^music$")],
            states={
                MUSIC_GENRE: [CallbackQueryHandler(self.button_handler, pattern="^genre_")],
                MUSIC_PROMPT: [MessageHandler(filters.TEXT & ~filters.COMMAND, self.handle_music)]
            },
            fallbacks=[CommandHandler("cancel", self.cancel)]
        )
        app.add_handler(music_conv)
        
        clone_conv = ConversationHandler(
            entry_points=[CallbackQueryHandler(self.button_handler, pattern="^clone_voice$")],
            states={CLONE_VOICE: [MessageHandler(filters.VOICE | filters.AUDIO, self.handle_clone)]},
            fallbacks=[CommandHandler("cancel", self.cancel)]
        )
        app.add_handler(clone_conv)
        
        app.add_handler(CallbackQueryHandler(self.button_handler, pattern="^(back_|my_stats|help|admin_)"))
    
    async def post_init(self, app: Application):
        await self.db.init()

def main():
    bot = AIBot()
    app = Application.builder().token(Config.BOT_TOKEN).build()
    app.post_init = bot.post_init
    bot.setup(app)
    app.run_polling()

if __name__ == "__main__":
    main()
