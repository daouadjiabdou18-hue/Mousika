import aiohttp

class FishAudioService:
    def __init__(self):
        from config import Config
        self.key = Config.FISH_AUDIO_API_KEY
        self.url = "https://api.fish.audio/v1/tts"
    
    async def text_to_speech(self, text):
        headers = {"Authorization": f"Bearer {self.key}", "Content-Type": "application/json"}
        payload = {"text": text, "format": "mp3", "latency": "normal"}
        
        async with aiohttp.ClientSession() as s:
            async with s.post(self.url, json=payload, headers=headers, timeout=30) as r:
                if r.status == 200:
                    return await r.read()
                return None
    
    async def clone_voice(self, audio_data, name):
        # تبسيط - يحتاج API حقيقي
        return None

