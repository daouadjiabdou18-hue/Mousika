hereimport aiohttp

class MusicGenerator:
    def __init__(self):
        from config import Config
        self.key = Config.TWOSHOT_API_KEY
    
    async def generate_with_twoshot(self, prompt, genre):
        if not self.key:
            return None
        # تبسيط - يحتاج API حقيقي
        return None
