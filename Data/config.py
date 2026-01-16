import os
import sys
from dotenv import load_dotenv

# Загружаем переменные окружения из .env файла
load_dotenv()

# Telegram ID администраторов (можно указать через запятую в .env)
ADMIN_TG_ID_STR = os.getenv("ADMIN_TG_ID", "")
ADMIN_TG_ID = [int(id.strip()) for id in ADMIN_TG_ID_STR.split(",") if id.strip()]

# Токен бота
BOT_TOKEN = os.getenv("BOT_TOKEN", "")

# URL подключения к базе данных
DATABASE_URL = os.getenv("DATABASE_URL", "")


def validate_config():
    """Проверяет наличие обязательных переменных окружения"""
    errors = []
    
    if not BOT_TOKEN or BOT_TOKEN == "your_bot_token_here":
        errors.append("❌ BOT_TOKEN не установлен! Установите токен бота в .env файле.")
    
    if not DATABASE_URL or DATABASE_URL == "postgresql+asyncpg://user:password@host:port/database":
        errors.append("❌ DATABASE_URL не установлен! Установите URL базы данных в .env файле.")
    
    if not ADMIN_TG_ID:
        errors.append("⚠️ ADMIN_TG_ID не установлен! Бот будет работать без администраторов.")
    
    if errors:
        print("\n" + "=" * 60)
        print("⚠️ ОШИБКИ КОНФИГУРАЦИИ:")
        print("=" * 60)
        for error in errors:
            print(error)
        print("=" * 60)
        print("\n📝 Создайте файл .env в корне проекта на основе .env.example")
        print("   и заполните все необходимые переменные окружения.\n")
        
        # Критические ошибки останавливают запуск
        critical_errors = [e for e in errors if not e.startswith("⚠️")]
        if critical_errors:
            sys.exit(1)


# Проверяем конфигурацию при импорте модуля
validate_config()
