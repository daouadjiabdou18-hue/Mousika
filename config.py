import os

class Config:
    BOT_TOKEN = os.getenv("BOT_TOKEN", "")
    ADMIN_ID = int(os.getenv("ADMIN_ID", "0"))
    FISH_AUDIO_API_KEY = os.getenv("FISH_AUDIO_API_KEY", "")
    TWOSHOT_API_KEY = os.getenv("TWOSHOT_API_KEY", "")
    MAX_DAILY_REQUESTS = 10
    MAX_TEXT_LENGTH = 500
