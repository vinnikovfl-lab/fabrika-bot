# setup.ps1 - автоматическая настройка проекта Fabrika_Bot

Write-Host "🔧 Установка проекта Fabrika_Bot..." -ForegroundColor Cyan

# 1. Проверка наличия Python 3.11
$pythonVersion = py -3.11 --version 2>$null
if (-not $pythonVersion) {
    Write-Host "❌ Python 3.11 не найден! Установите Python 3.11.8 (64-bit) с https://www.python.org/downloads/release/python-3118/" -ForegroundColor Red
    exit 1
}
Write-Host "✅ Найден $pythonVersion"

# 2. Удаляем старое окружение (если есть)
if (Test-Path ".venv") {
    Write-Host "🗑 Удаляем старое виртуальное окружение..."
    Remove-Item ".venv" -Recurse -Force
}

# 3. Создаём новое окружение
Write-Host "📦 Создаём новое виртуальное окружение (.venv)..."
py -3.11 -m venv .venv

# 4. Активируем окружение
Write-Host "⚡ Активируем окружение..."
. .\.venv\Scripts\Activate.ps1

# 5. Обновляем pip и базовые пакеты
Write-Host "⬆️ Обновляем pip/setuptools/wheel..."
pip install --upgrade pip setuptools wheel

# 6. Устанавливаем зависимости
Write-Host "📥 Устанавливаем зависимости..."
pip install aiogram==3.2.0 aiohttp==3.9.5 SQLAlchemy==2.0.21 alembic==1.12.0 python-dotenv==1.0.0

# 7. Прогоняем миграции
Write-Host "🗄 Запускаем alembic upgrade head..."
alembic upgrade head

# 8. Запускаем бота
Write-Host "🤖 Запускаем бота!"
python bot.py