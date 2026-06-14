"""
📝 Normalizer — нормализация русского текста перед TTS
Гибрид: нейронка (RUNorm + T5) если есть torch, иначе правила (regex)

Что делает:
- числа → слова: "150" → "сто пятьдесят"
- валюты: "150 руб." → "сто пятьдесят рублей"
- телефоны: "+7 999 123-45-67" → "плюс семь девятьсот девяносто девять..."
- аббревиатуры: "ООН" → "о он эн"
- латиница → произношение: "GPU" → "гпу" / "джи пи ю"
- даты, время, проценты, дроби

Включается/выключается через bot.normalization_disabled
"""

import time
import re
import logging

logger = logging.getLogger(__name__)


def _log(tag: str, msg: str):
    """Форматированный лог с таймстемпом"""
    t = time.strftime("%H:%M:%S")
    print(f"[{t}] [{tag}] {msg}")


# ===================== Правила (без torch) =====================

# Буквенное произношение русских букв (для аббревиатур)
PRONUNCIATION_MAP = {
    'А': 'а', 'Б': 'бэ', 'В': 'вэ', 'Г': 'гэ', 'Д': 'дэ',
    'Е': 'е', 'Ё': 'ё', 'Ж': 'жэ', 'З': 'зэ', 'И': 'и',
    'Й': 'ий', 'К': 'ка', 'Л': 'эл', 'М': 'эм', 'Н': 'эн',
    'О': 'о', 'П': 'пэ', 'Р': 'эр', 'С': 'эс', 'Т': 'тэ',
    'У': 'у', 'Ф': 'эф', 'Х': 'ха', 'Ц': 'цэ', 'Ч': 'чэ',
    'Ш': 'ша', 'Щ': 'ща', 'Ъ': 'твёрдый знак',
    'Ы': 'ы', 'Ь': 'мягкий знак',
    'Э': 'э', 'Ю': 'ю', 'Я': 'я',
}

# Латинские буквы → побуквенное произношение
LATIN_PRONUNCIATION = {
    'a': 'эй', 'b': 'би', 'c': 'си', 'd': 'ди', 'e': 'и',
    'f': 'эф', 'g': 'джи', 'h': 'эйч', 'i': 'ай', 'j': 'джей',
    'k': 'кей', 'l': 'эль', 'm': 'эм', 'n': 'эн', 'o': 'оу',
    'p': 'пи', 'q': 'кью', 'r': 'ар', 's': 'эс', 't': 'ти',
    'u': 'ю', 'v': 'ви', 'w': 'дабл-ю', 'x': 'экс', 'y': 'уай',
    'z': 'зэд',
}

# Единицы чисел (именительный падеж)
UNITS = ['', 'один', 'два', 'три', 'четыре', 'пять', 'шесть', 'семь', 'восемь', 'девять']
UNITS_F = ['', 'одна', 'две', 'три', 'четыре', 'пять', 'шесть', 'семь', 'восемь', 'девять']
TEENS = ['десять', 'одиннадцать', 'двенадцать', 'тринадцать', 'четырнадцать',
         'пятнадцать', 'шестнадцать', 'семнадцать', 'восемнадцать', 'девятнадцать']
TENS = ['', '', 'двадцать', 'тридцать', 'сорок', 'пятьдесят',
        'шестьдесят', 'семьдесят', 'восемьдесят', 'девяносто']
HUNDREDS = ['', 'сто', 'двести', 'триста', 'четыреста', 'пятьсот',
            'шестьсот', 'семьсот', 'восемьсот', 'девятьсот']

# Разряды (тысячи, миллионы, миллиарды)
THOUSAND = ['тысяча', 'тысячи', 'тысяч']
MILLION = ['миллион', 'миллиона', 'миллионов']
BILLION = ['миллиард', 'миллиарда', 'миллиардов']


def _plural_form(n: int, forms: list[str]) -> str:
    """Выбрать форму слова в зависимости от числа: 1 → forms[0], 2-4 → forms[1], 5+ → forms[2]"""
    if n % 100 in (11, 12, 13, 14):
        return forms[2]
    if n % 10 == 1:
        return forms[0]
    if n % 10 in (2, 3, 4):
        return forms[1]
    return forms[2]


def _number_to_words_ru(n: int, feminine: bool = False) -> str:
    """Конвертировать число (0 - 999 999 999 999) в слова"""
    if n == 0:
        return 'ноль'

    if n < 0:
        return f"минус {_number_to_words_ru(-n, feminine)}"

    def _under_1000(num: int, fem: bool = False) -> str:
        """Число до 999 в слова"""
        words = []
        h = num // 100
        if h:
            words.append(HUNDREDS[h])
        t = num % 100
        if 10 <= t <= 19:
            words.append(TEENS[t - 10])
        else:
            t_ten = t // 10
            t_one = t % 10
            if t_ten:
                words.append(TENS[t_ten])
            if t_one:
                words.append(UNITS_F[t_one] if fem else UNITS[t_one])
        return ' '.join(words)

    parts = []
    # Миллиарды
    b = n // 1_000_000_000
    if b:
        parts.append(f"{_under_1000(b)} {_plural_form(b, BILLION)}")
    # Миллионы
    m = (n % 1_000_000_000) // 1_000_000
    if m:
        parts.append(f"{_under_1000(m)} {_plural_form(m, MILLION)}")
    # Тысячи
    th = (n % 1_000_000) // 1_000
    if th:
        parts.append(f"{_under_1000(th, fem=True)} {_plural_form(th, THOUSAND)}")
    # Остаток
    remainder = n % 1_000
    if remainder:
        parts.append(_under_1000(remainder, feminine and not th))

    return ' '.join(parts)


def _expand_abbreviations(text: str) -> str:
    """Расшифровать аббревиатуры из заглавных букв"""
    def _replace_abbr(match):
        abbr = match.group(0)
        return ' '.join(PRONUNCIATION_MAP.get(ch, ch.lower()) for ch in abbr)

    # Ищем 2+ заглавных русских буквы подряд
    text = re.sub(r'\b[А-ЯЁ]{2,}\b', _replace_abbr, text)
    return text


def _expand_latin_word(text: str) -> str:
    """Расшифровать латинское слово побуквенно (для коротких слов/акронимов)"""
    def _replace_latin(match):
        word = match.group(0)
        # Если похоже на английское слово длиннее 4 букв — пытаемся прочитать по-русски
        # Иначе — побуквенно
        if len(word) <= 4:
            return ' '.join(LATIN_PRONUNCIATION.get(ch.lower(), ch) for ch in word)
        # Длинные слова оставляем как есть (или можно простую кириллизацию)
        return word

    # Ищем латинские слова 2-4 буквы (акронимы вроде GPU, CPU, USB)
    text = re.sub(r'\b[a-zA-Z]{2,4}\b', _replace_latin, text)
    return text


def _currency_normalize(text: str) -> str:
    """Нормализовать валюты: 150 руб. → сто пятьдесят рублей"""
    def _currency_replacer(match):
        amount_str = match.group(1)
        currency_type = match.group(2).lower()

        # Парсим число
        if '.' in amount_str:
            main_part, frac_part = amount_str.split('.')
            main_n = int(main_part) if main_part else 0
            frac_n = int(frac_part.ljust(2, '0')[:2])
        else:
            main_n = int(amount_str)
            frac_n = 0

        if 'руб' in currency_type or '₽' in currency_type:
            main_word = _number_to_words_ru(main_n, feminine=False)
            main_unit = _plural_form(main_n, ['рубль', 'рубля', 'рублей'])
            if frac_n:
                frac_word = _number_to_words_ru(frac_n, feminine=True)
                frac_unit = _plural_form(frac_n, ['копейка', 'копейки', 'копеек'])
                return f"{main_word} {main_unit} {frac_word} {frac_unit}"
            return f"{main_word} {main_unit}"

        if 'доллар' in currency_type or '$' in currency_type or 'usd' in currency_type.lower():
            main_word = _number_to_words_ru(main_n, feminine=False)
            main_unit = _plural_form(main_n, ['доллар', 'доллара', 'долларов'])
            if frac_n:
                frac_word = _number_to_words_ru(frac_n, feminine=False)
                frac_unit = _plural_form(frac_n, ['цент', 'цента', 'центов'])
                return f"{main_word} {main_unit} {frac_word} {frac_unit}"
            return f"{main_word} {main_unit}"

        if 'евро' in currency_type or '€' in currency_type:
            main_word = _number_to_words_ru(main_n, feminine=False)
            return f"{main_word} евро"

        return match.group(0)

    # Русские валюты
    text = re.sub(r'(\d+(?:\.\d{1,2})?)\s*(руб(?:лей|ля|ль|\.)?|₽)', _currency_replacer, text, flags=re.IGNORECASE)
    # Доллары
    text = re.sub(r'(\d+(?:\.\d{1,2})?)\s*(доллар(?:ов|а|ы|\.)?|\$|usd)', _currency_replacer, text, flags=re.IGNORECASE)
    # Евро
    text = re.sub(r'(\d+(?:\.\d{1,2})?)\s*(евро|€)', _currency_replacer, text, flags=re.IGNORECASE)
    return text


def _phone_normalize(text: str) -> str:
    """Нормализовать номера телефонов"""
    def _phone_replacer(match):
        digits = re.sub(r'\D', '', match.group(0))
        if len(digits) == 11 and digits.startswith('8'):
            return '+7 ' + ' '.join(_number_to_words_ru(int(d) if d.isdigit() else 0) for d in digits[1:])
        if len(digits) == 11 and digits.startswith('7'):
            return 'плюс семь ' + ' '.join(_number_to_words_ru(int(d) if d.isdigit() else 0) for d in digits[1:])
        if len(digits) == 10:
            return ' '.join(_number_to_words_ru(int(d) if d.isdigit() else 0) for d in digits)
        return match.group(0)

    text = re.sub(r'(?:\+7|8)\s*\(?\d{3}\)?[\s-]?\d{3}[\s-]?\d{2}[\s-]?\d{2}', _phone_replacer, text)
    return text


def _number_normalize(text: str) -> str:
    """Нормализовать числа в тексте"""
    def _number_replacer(match):
        num_str = match.group(0)
        # Пропускаем если это часть даты, времени, процентов
        prev_char = text[max(0, match.start()-1):match.start()]
        next_char = text[match.end():match.end()+1] if match.end() < len(text) else ''

        # Пропускаем проценты
        if next_char == '%':
            return f"{_number_to_words_ru(int(num_str))} процентов"

        # Пропускаем дроби
        if '.' in num_str:
            parts = num_str.split('.')
            if len(parts) == 2 and len(parts[1]) <= 2:
                main = _number_to_words_ru(int(parts[0]))
                frac = ' '.join(_number_to_words_ru(int(d)) for d in parts[1])
                return f"{main} целых {frac} сотых"

        # Обычное целое число
        try:
            n = int(num_str)
            if n > 999_999_999_999:
                # Огромные числа — побуквенно
                return ' '.join(_number_to_words_ru(int(d)) for d in num_str)
            return _number_to_words_ru(n)
        except ValueError:
            return num_str

    # Заменяем числа, которые не часть слова
    text = re.sub(r'(?<!\w)\d{1,12}(?!\w)(?!\s*[.:]\d)', _number_replacer, text)
    return text


def _percent_normalize(text: str) -> str:
    """Нормализовать проценты"""
    text = re.sub(r'(\d+)\s*%', lambda m: f"{_number_to_words_ru(int(m.group(1)))} процентов", text)
    return text


def rule_normalize(text: str) -> str:
    """Нормализация текста правилами (без нейронки)"""
    original = text
    text = _expand_abbreviations(text)
    text = _expand_latin_word(text)
    text = _currency_normalize(text)
    text = _phone_normalize(text)
    text = _percent_normalize(text)
    text = _number_normalize(text)
    # Убираем лишние пробелы
    text = re.sub(r'\s+', ' ', text).strip()
    return text


# ===================== Нормалайзер =====================

class Normalizer:
    """Нормалайзер текста для TTS.

    Режимы:
    - neural=True: полный RUNorm с T5-моделями (нужен torch)
    - neural=False: только правила (чистый Python, без зависимостей)

    Ленивая загрузка: модель грузится при первом вызове norm()
    """

    def __init__(self, model_size: str = "small", device: str = "cpu"):
        self.model_size = model_size
        self.device = device
        self._model = None
        self._neural = False
        self._loaded = False
        self._forced_rule = True  # по умолчанию rule-based (быстро, без зависимостей)

    def set_mode(self, mode: str) -> str:
        """Переключить режим нормализации.

        mode='neural' — нейронная (RUNorm T5), нужен torch
        mode='rule' — только правила (чистый Python)
        Возвращает сообщение для пользователя.
        """
        mode = mode.lower().strip()

        if mode == "neural":
            if not self._model:
                # Пробуем загрузить нейронку
                self._loaded = False  # сброс, чтобы _load перепробовал
                t_start = time.time()
                try:
                    import torch  # noqa: F401
                    from runorm import RUNorm
                    _log("NORM", f"Загружаю RUNorm neural ({self.model_size}) на {self.device}...")
                    self._model = RUNorm()
                    self._model.load(model_size=self.model_size, device=self.device)
                    self._neural = True
                    self._loaded = True
                    self._forced_rule = False
                    elapsed = time.time() - t_start
                    _log("NORM", f"RUNorm neural загружен за {elapsed:.1f}с")
                    return f"🧠 Переключён на нейронную нормализацию (загрузка {elapsed:.1f}с)"
                except ImportError:
                    return "❌ Нейронная нормализация недоступна: не хватает зависимостей (torch / runorm / transformers)"
                except Exception as e:
                    return f"❌ Нейронная нормализация не загрузилась: {e}"
            else:
                # Уже загружена — просто переключаем
                self._neural = True
                self._forced_rule = False
                return "🧠 Переключён на нейронную нормализацию"

        if mode == "rule":
            self._forced_rule = True
            self._neural = False
            return "📏 Переключён на rule-based нормализацию (числа/валюты/телефоны правилами)"

        return f"❌ Неизвестный режим «{mode}». Доступны: neural, rule"

    def _load(self):
        """Загрузить нормалайзер (лениво, при первом вызове).

        Если юзер принудительно включил rule — не трогаем нейронку.
        """
        if self._loaded:
            return

        t_start = time.time()

        # Если юзер выбрал rule — даже не пробуем нейронку
        if self._forced_rule:
            self._neural = False
            self._loaded = True
            elapsed = time.time() - t_start
            _log("NORM", f"Rule-based (принудительно) за {elapsed*1000:.0f}мс")
            return

        # Пробуем загрузить RUNorm с нейронкой
        try:
            import torch  # noqa: F401
            from runorm import RUNorm
            _log("NORM", f"Загружаю RUNorm neural ({self.model_size}) на {self.device}...")
            self._model = RUNorm()
            self._model.load(model_size=self.model_size, device=self.device)
            self._neural = True
            self._loaded = True
            elapsed = time.time() - t_start
            _log("NORM", f"RUNorm neural загружен за {elapsed:.1f}с")
        except ImportError:
            _log("NORM", "torch/runorm не найден → rule-based")
            self._neural = False
            self._loaded = True
        except Exception as e:
            _log("NORM", f"Neural не загрузился ({e}) → rule-based")
            self._neural = False
            self._loaded = True

        if not self._neural:
            elapsed = time.time() - t_start
            _log("NORM", f"Rule-based нормализатор готов за {elapsed*1000:.0f}мс")

    def norm(self, text: str) -> str:
        """Нормализовать текст для синтеза речи"""
        if not text or not text.strip():
            return text

        self._load()
        t_start = time.time()

        if self._neural:
            # Полная нейронная нормализация
            try:
                result = self._model.norm(text)
            except Exception as e:
                _log("NORM", f"Neural error: {e} → fallback на rule-based")
                self._neural = False
                result = rule_normalize(text)
        else:
            # Rule-based нормализация
            result = rule_normalize(text)

        elapsed = time.time() - t_start
        if text != result:
            _log("NORM", f"«{text[:60]}...» → «{result[:60]}...» ({elapsed*1000:.0f}мс)")
        return result

    @property
    def mode(self) -> str:
        """Вернуть текущий режим: neural или rule"""
        if self._forced_rule:
            return "rule (forced)"
        return "neural" if self._neural else "rule"

    @property
    def status(self) -> str:
        """Статус нормалайзера для показа пользователю"""
        if self._forced_rule:
            mode_str = "📏 Rule-based (принудительно)"
        elif self._neural:
            mode_str = "🧠 Нейронная (RUNorm T5)"
        else:
            mode_str = "📏 По правилам (regex)"
        if not self._loaded and not self._forced_rule:
            return f"{mode_str} | ⏳ Не загружен"
        return f"{mode_str} | Модель: {self.model_size}"
