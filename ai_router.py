import requests

class AIRouter:
    def __init__(self, api_key: str, base_url: str = "https://routellm.abacus.ai/v1/chat/completions"):
        """
        AI Router для автоматического выбора модели (Claude, GPT-4.1, DeepSeek и др.)
        :param api_key: API ключ RouteLLM
        :param base_url: конечная точка API (по умолчанию RouteLLM Completions)
        """
        self.api_key = api_key
        self.base_url = base_url

    def determine_model(self, task: str) -> str:
        """
        На основе описания задачи определяем модель.
        Используется только для логов, так как на самом деле RouteLLM сам выбирает модель.
        """
        task_lower = task.lower()

        if any(word in task_lower for word in ["архитектура", "menu", "структура", "ux", "дизайн"]):
            return "claude-3.5-sonnet"
        elif any(word in task_lower for word in ["бд", "sqlalchemy", "async", "crud", "подписк", "оплат", "заказ"]):
            return "gpt-4.1"
        elif any(word in task_lower for word in ["generate", "long code", "scaffold", "шаблон", "много кода"]):
            return "deepseek-coder"
        else:
            return "gpt-4.1"

    def send_request(self, task: str, context: str):
        """
        Отправка запроса в RouteLLM API.
        :param task: текст задачи
        :param context: общий проектный контекст
        :return: { success: bool, response: str | error: str }
        """
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json"
        }

        payload = {
            "model": "route-llm",
            "messages": [
                {"role": "system", "content": context},
                {"role": "user", "content": task}
            ],
            "stream": False   # 🔥 важно — получаем весь ответ сразу
        }

        try:
            response = requests.post(self.base_url, headers=headers, json=payload)
            response.raise_for_status()
            data = response.json()

            # Ответ приходит в стиле OpenAI: choices[0].message.content
            return {
                "success": True,
                "response": data.get("choices", [{}])[0].get("message", {}).get("content", "")
            }
        except Exception as e:
            return {"success": False, "error": str(e)}