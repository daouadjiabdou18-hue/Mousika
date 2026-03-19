import aiosqlite
from datetime import datetime

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
            await db.execute("""
                CREATE TABLE IF NOT EXISTS cloned_voices (
                    id INTEGER PRIMARY KEY,
                    user_id INTEGER,
                    voice_name TEXT,
                    voice_id TEXT
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
    
    async def save_cloned_voice(self, user_id, name, voice_id):
        async with aiosqlite.connect(self.db_path) as db:
            await db.execute(
                "INSERT INTO cloned_voices (user_id, voice_name, voice_id) VALUES (?, ?, ?)",
                (user_id, name, voice_id)
            )
            await db.commit()
    
    async def get_stats(self):
        async with aiosqlite.connect(self.db_path) as db:
            async with db.execute("SELECT COUNT(*) FROM users") as c:
                users = (await c.fetchone())[0]
            async with db.execute("SELECT COUNT(*) FROM cloned_voices") as c:
                voices = (await c.fetchone())[0]
            return {"total_users": users, "total_requests": voices}
