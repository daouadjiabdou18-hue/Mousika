from telegram import InlineKeyboardButton, InlineKeyboardMarkup

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

def admin_keyboard():
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("📊 إحصائيات", callback_data="admin_stats")]
    ])

