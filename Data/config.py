import os
import sys
from pathlib import Path
from dotenv import load_dotenv, dotenv_values


def _load_env_from_project_root() -> Path:
    """
    Load .env from the project root независимо от текущего cwd.

    Частая причина "BOT_TOKEN не установлен" при наличии .env:
    запуск из IDE/ярлыка/абсолютным путём с cwd != корень проекта.
    """
    project_root = Path(__file__).resolve().parent.parent  # Data/ -> project root
    env_path = project_root / ".env"

    # Не перетираем реальные переменные окружения, если они уже заданы.
    if env_path.exists():
        load_dotenv(dotenv_path=env_path, override=False)

        # If the environment contains empty values (e.g. BOT_TOKEN=""), python-dotenv
        # will not overwrite them with override=False. Fill blanks from .env.
        values = dotenv_values(dotenv_path=env_path)
        for k, v in values.items():
            if not k or v is None:
                continue

            # UTF-8 BOM in .env can be parsed as part of the first key name on Windows.
            # Normalize it so "BOT_TOKEN" is found even if the file starts with BOM.
            nk = k.lstrip("\ufeff")
            if os.environ.get(nk, "").strip() == "":
                os.environ[nk] = str(v)
    else:
        load_dotenv(override=False)

    return env_path


ENV_PATH = _load_env_from_project_root()

ADMIN_TG_ID_STR = os.getenv("ADMIN_TG_ID", "")
ADMIN_TG_ID = [int(id.strip()) for id in ADMIN_TG_ID_STR.split(",") if id.strip()]

BOT_TOKEN = os.getenv("BOT_TOKEN", "")

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
        
        critical_errors = [e for e in errors if not e.startswith("⚠️")]
        print(f"\nℹ️ Диагностика: cwd={os.getcwd()}")
        print(f"ℹ️ Диагностика: ожидаемый .env={str(ENV_PATH)} (exists={ENV_PATH.exists()})")

        if critical_errors:
            sys.exit(1)


validate_config()
