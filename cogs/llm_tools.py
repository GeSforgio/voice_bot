"""
🛠️ LLM Tools — инструменты для LangChain tool calling
DeepSeek v4 Flash сам решает когда вызывать эти функции

Поиск: Tavily (основной) → DuckDuckGo (фолбэк если нет TAVILY_API_KEY)

Логи с таймстемпами и замерами времени каждого вызова.
"""

import time
import ai_config
from langchain_core.tools import tool


def _log(tag: str, msg: str):
    """Форматированный лог с таймстемпом"""
    t = time.strftime("%H:%M:%S")
    print(f"[{t}] [{tag}] {msg}")


# ===== Tavily (основной поиск) =====
_TAVILY_AVAILABLE = bool(ai_config.TAVILY_API_KEY)
if _TAVILY_AVAILABLE:
    from langchain_tavily import TavilySearch
    _tavily = TavilySearch(max_results=5)
else:
    from ddgs import DDGS


@tool
def web_search(query: str) -> str:
    """
    Искать в интернете.
    Используй ЭТОТ ИНСТРУМЕНТ ОБЯЗАТЕЛЬНО когда пользователь просит: 
    - найти что-то в интернете, погуглить, поискать
    - показать ссылки, топ сайтов, топ страниц
    - узнать актуальные новости, даты, события, факты
    - проверить информацию, которой у тебя нет в знаниях
    - запросил конкретный поисковый запрос
    НЕ пытайся угадать или выдумать — всегда ищи через этот инструмент.
    """
    t_start = time.time()
    provider = "Tavily" if _TAVILY_AVAILABLE else "DDGS"
    _log("TOOL", f"→ web_search (query=\"{query[:60]}\", provider={provider})")
    try:
        if _TAVILY_AVAILABLE:
            # Tavily — быстрый, чистый результат для LLM
            results = _tavily.invoke(query)
            # TavilySearch возвращает строку — просто возвращаем
            result = results if results else "Ничего не найдено."
        else:
            # Фолбэк на DuckDuckGo
            with DDGS() as ddgs:
                raw = list(ddgs.text(query, max_results=5))
            if not raw:
                result = "Ничего не найдено."
            else:
                formatted = []
                for r in raw:
                    title = r.get("title", "")
                    body = r.get("body", "")
                    link = r.get("link", "")
                    formatted.append(f"- {title}: {body} ({link})")
                result = "\n".join(formatted[:5])
        elapsed = time.time() - t_start
        _log("TOOL", f"← web_search: {elapsed:.1f}с ({len(result)} символов)")
        return result
    except Exception as e:
        elapsed = time.time() - t_start
        _log("TOOL", f"← web_search: {elapsed:.1f}с — ОШИБКА: {e}")
        return f"Ошибка поиска: {e}"


@tool
def get_weather(city: str = None) -> str:
    """
    Узнать погоду в городе.
    Если город не указан — определяет по IP.
    """
    import urllib.request
    import urllib.parse

    t_start = time.time()
    loc = city or "по IP"
    _log("TOOL", f"→ get_weather (city=\"{loc}\")")
    try:
        if city:
            url = f"https://wttr.in/{urllib.parse.quote(city)}?format=%l:+%t+%C+%w+%h&lang=ru"
        else:
            url = "https://wttr.in/?format=%l:+%t+%C+%w+%h&lang=ru"

        with urllib.request.urlopen(url, timeout=10) as resp:
            result = resp.read().decode("utf-8").strip()
        elapsed = time.time() - t_start
        _log("TOOL", f"← get_weather: {elapsed:.1f}с ({len(result)} символов)")
        return result
    except Exception as e:
        elapsed = time.time() - t_start
        _log("TOOL", f"← get_weather: {elapsed:.1f}с — ОШИБКА: {e}")
        return f"Не удалось узнать погоду: {e}"


TOOLS = [web_search, get_weather]


# ===== Tavily Extract (читать страницу) =====
if _TAVILY_AVAILABLE:

    @tool
    def read_url(url: str) -> str:
        """
        Посетить веб-сайт по URL и прочитать его содержимое.
        Используй ЭТОТ ИНСТРУМЕНТ ОБЯЗАТЕЛЬНО когда пользователь просит:
        - зайти на сайт, открыть страницу, посмотреть что там
        - узнать рейтинг, цену, информацию с конкретного сайта
        - прочитать статью, новость, документацию по ссылке
        - получить актуальные данные с какого-либо веб-сайта
        Передай ПОЛНЫЙ URL (с https://). Пример: https://kinopoisk.ru
        НЕ выдумывай содержимое сайта — всегда используй этот инструмент.
        """
        t_start = time.time()
        _log("TOOL", f"→ read_url (url=\"{url[:60]}\")")
        try:
            from tavily import TavilyClient
            client = TavilyClient(api_key=ai_config.TAVILY_API_KEY)
            response = client.extract(urls=url, extract_depth="advanced")
            results = response.get("results", [])
            if results:
                content = results[0].get("raw_content", "")
                if content:
                    result = content[:3000]
                    elapsed = time.time() - t_start
                    _log("TOOL", f"← read_url: {elapsed:.1f}с ({len(result)} символов)")
                    return result
        except Exception:
            pass  # Пробуем фолбэк через поиск

        # Фолбэк: не смогли прочитать страницу — ищем в интернете
        # Преобразуем URL в поисковый запрос (используем полный путь)
        search_query = url
        for prefix in ["https://", "http://", "www."]:
            search_query = search_query.replace(prefix, "")
        # Убираем лишние слеши в конце
        search_query = search_query.rstrip("/")
        # Заменяем / на пробелы для читаемого поискового запроса
        search_query = search_query.replace("/", " ")
        # Убираем .ru .com
        for tld in [".ru", ".com", ".net", ".org"]:
            search_query = search_query.replace(tld, "")

        fallback = web_search.invoke({"query": search_query})
        elapsed = time.time() - t_start
        _log("TOOL", f"← read_url: {elapsed:.1f}с — фолбэк на поиск")
        return fallback

    TOOLS = [web_search, get_weather, read_url]
