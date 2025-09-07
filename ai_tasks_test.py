from ai_router import AIRouter
from config import ROUTELLM_API_KEY, PROJECT_CONTEXT

# Инициализация роутера
router = AIRouter(api_key=ROUTELLM_API_KEY)

def run_test_task():
    print("🚀 Тест задачи через RouteLLM → Claude\n")

    task = (
        "Спроектируй раздел menu_posts: нужны inline-кнопки "
        "'📅 Текущая неделя', '📦 Архив', '📊 Итоги недели'. "
        "Код раздели: обработка событий в handlers/posts.py, "
        "inline-клавиатура в menus/posts_menu.py."
    )

    result = router.send_request(task, PROJECT_CONTEXT)

    print("\n=== РЕЗУЛЬТАТ ===")
    if result["success"]:
        print(result["response"])
    else:
        print("❌ Ошибка:", result["error"])

if __name__ == "__main__":
    run_test_task()