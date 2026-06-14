"""
🤖 LLM Client — фабрика LangChain ChatOpenAI для DeepSeek
Централизованное создание LLM для ai_cog и voice_cog
"""

from langchain_openai import ChatOpenAI
import ai_config


def create_llm(max_tokens: int = None) -> ChatOpenAI:
    """Создать LangChain ChatOpenAI с DeepSeek-конфигом"""
    return ChatOpenAI(
        model=ai_config.AI_MODEL,
        api_key=ai_config.AI_API_KEY,
        base_url=ai_config.AI_ENDPOINT,
        temperature=ai_config.AI_TEMPERATURE,
        max_tokens=max_tokens or ai_config.AI_MAX_TOKENS_CHAT,
        timeout=60,
        max_retries=0,
        extra_body={"thinking": {"type": "disabled"}},
    )
