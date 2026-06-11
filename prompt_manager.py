"""
📦 PromptManager — менеджер промптов для Пиздуна
Автоматически сканирует папку prompts/, подгружает все промпты
Позволяет переключать промпт для каждого пользователя отдельно
"""

import os
import importlib
import importlib.util


class PromptManagerError(Exception):
    """Кастомная ошибка менеджера промптов"""
    pass


class PromptManager:
    """Менеджер промптов — загрузка, хранение, переключение"""

    def __init__(self, prompts_dir: str = "prompts"):
        self.prompts_dir = prompts_dir
        self.prompts: dict[str, dict] = {}       # {name: {name, description, prompt}}
        self.default_prompt: str | None = None    # имя промпта по умолчанию
        self.user_prompts: dict[int, str] = {}    # {user_id: prompt_name}

        if not os.path.isdir(prompts_dir):
            raise PromptManagerError(
                f"Папка с промптами не найдена: {prompts_dir}"
            )

        self._load_prompts()

    # ===== Загрузка =====

    def _load_prompts(self) -> None:
        """Просканировать prompts/ и загрузить все .py (кроме __init__)"""
        prompt_files = [
            f for f in os.listdir(self.prompts_dir)
            if f.endswith(".py") and f != "__init__.py"
        ]

        if not prompt_files:
            raise PromptManagerError(
                f"В папке {self.prompts_dir} нет файлов с промптами!"
            )

        for filename in sorted(prompt_files):
            module_name = filename[:-3]  # отрезаем .py
            filepath = os.path.join(self.prompts_dir, filename)

            try:
                spec = importlib.util.spec_from_file_location(module_name, filepath)
                module = importlib.util.module_from_spec(spec)
                spec.loader.exec_module(module)

                name = getattr(module, "NAME", module_name)
                description = getattr(module, "DESCRIPTION", module_name)
                prompt = getattr(module, "PROMPT", None)

                if not prompt:
                    print(f"[WARN] Промпт {filename}: не найден PROMPT, пропускаю")
                    continue

                self.prompts[name] = {
                    "name": name,
                    "description": description,
                    "prompt": prompt,
                }
                print(f"[OK] Загружен промпт: {name} — {description}")

            except Exception as e:
                print(f"[ERROR] Не удалось загрузить {filename}: {e}")

        # Первый загруженный — по умолчанию
        if self.prompts and not self.default_prompt:
            self.default_prompt = list(self.prompts.keys())[0]
            print(f"[OK] Промпт по умолчанию: {self.default_prompt}")

    # ===== API =====

    def list_prompts(self) -> list[dict]:
        """Вернуть [{name, description}, ...] для всех промптов"""
        return [
            {"name": name, "description": data["description"]}
            for name, data in self.prompts.items()
        ]

    def get_prompt(self, user_id: int | None = None) -> str:
        """Вернуть текст промпта для пользователя (или дефолтный)"""
        name = self.default_prompt
        if user_id and user_id in self.user_prompts:
            name = self.user_prompts[user_id]

        prompt_data = self.prompts.get(name)
        if not prompt_data:
            # Фолбек на первый попавшийся
            first = list(self.prompts.values())[0]
            return first["prompt"]

        return prompt_data["prompt"]

    def set_prompt(self, user_id: int, name: str) -> tuple[bool, str]:
        """Переключить промпт для пользователя.
        Возвращает (успех, сообщение)."""
        if name not in self.prompts:
            available = ", ".join(self.prompts.keys())
            return False, (
                f"Промпт «{name}» не найден.\n"
                f"Доступны: {available}"
            )

        self.user_prompts[user_id] = name
        desc = self.prompts[name]["description"]
        return True, f"Промпт сменён на «{name}» ({desc})"

    def get_current_name(self, user_id: int | None = None) -> str:
        """Вернуть имя активного промпта для пользователя"""
        if user_id and user_id in self.user_prompts:
            return self.user_prompts[user_id]
        return self.default_prompt or "?"

    def get_current_description(self, user_id: int | None = None) -> str:
        """Вернуть описание активного промпта"""
        name = self.get_current_name(user_id)
        data = self.prompts.get(name)
        return data["description"] if data else "?"

    def reload(self) -> None:
        """Перезагрузить все промпты из папки (без перезапуска бота)"""
        self.prompts.clear()
        self.user_prompts.clear()
        self.default_prompt = None
        self._load_prompts()
