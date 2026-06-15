# 🤖 Настройки AI
# DeepSeek API — читается из .env (переменные AI_ENDPOINT, AI_MODEL, AI_API_KEY)
# Если не заданы — используются значения по умолчанию

import os

AI_ENDPOINT = os.getenv("AI_ENDPOINT", "https://api.deepseek.com/v1")
AI_MODEL = os.getenv("AI_MODEL", "deepseek-v4-flash")
AI_API_KEY = os.getenv("AI_API_KEY", "")

# === Поиск ===
TAVILY_API_KEY = os.getenv("TAVILY_API_KEY", "")

# === Whisper STT ===
WHISPER_MODEL = "small"         # размер модели: tiny, base, small, medium, large-v3
WHISPER_DEVICE = "cpu"         # cpu или cuda
WHISPER_COMPUTE_TYPE = "int8"  # int8, float16, float32 (на CPU — int8, на CUDA — float16)

# === AI Response ===
AI_MAX_TOKENS_VOICE = 400    # макс токенов для голосовых ответов (!скажи, !дежурь, !слушай)
AI_MAX_TOKENS_CHAT = 1024      # макс токенов для текстового чата (!чат)
AI_TEMPERATURE = 0.8           # креативность: 0.0 = строго, 1.0 = креатив, 2.0 = безумие
