"""Модуль для инициализации базы данных"""
from sqlalchemy import text
from db.engine import engine
from db.models import Base
from log import logger


# Оптимизация SQL-запросов для проверки существования таблиц и колонок
# Используем более эффективные запросы и объединяем их, где это возможно
async def migrate_database():
    """Выполняет необходимые миграции базы данных"""
    try:
        async with engine.begin() as conn:
            # Проверяем и исправляем колонку role (делаем её nullable)
            try:
                await conn.execute(text(
                    "ALTER TABLE users ALTER COLUMN role DROP NOT NULL;"
                ))
                logger.info("✅ Миграция: колонка role теперь nullable")
                print("✅ Миграция: колонка role теперь nullable")
            except Exception as e:
                error_msg = str(e).lower()
                if "does not exist" in error_msg or "column" in error_msg:
                    logger.info("ℹ️ Миграция role: уже применена или таблица не существует")
                else:
                    logger.warning(f"⚠️ Предупреждение при миграции: {e}")

            # Миграция: добавляем каскадное удаление для внешних ключей tasks
            tables_to_update = [
                ("messages", "task_id"),
                ("task_files", "task_id"),
                ("task_logs", "task_id"),
                ("task_corrections", "task_id"),
                ("task_rejections", "task_id"),
            ]

            for table_name, column_name in tables_to_update:
                try:
                    # Проверяем существование таблицы и внешнего ключа в одном запросе
                    check_table_and_constraint = await conn.execute(text(
                        f"SELECT EXISTS (SELECT FROM information_schema.tables WHERE table_name = '{table_name}') AS table_exists,"
                        f"(SELECT COUNT(*) FROM information_schema.key_column_usage WHERE table_name = '{table_name}' AND column_name = '{column_name}') > 0 AS constraint_exists;"
                    ))
                    result = check_table_and_constraint.fetchone()

                    if not result["table_exists"]:
                        logger.info(f"ℹ️ Таблица {table_name} не существует, пропускаем миграцию")
                        continue

                    if not result["constraint_exists"]:
                        logger.info(f"ℹ️ Внешний ключ для {table_name}.{column_name} не найден, возможно уже удален")
                        continue

                    # Удаляем старое ограничение и добавляем новое с CASCADE
                    await conn.execute(text(
                        f"ALTER TABLE {table_name} DROP CONSTRAINT IF EXISTS {table_name}_{column_name}_fkey;"
                        f"ALTER TABLE {table_name} ADD CONSTRAINT {table_name}_{column_name}_fkey FOREIGN KEY ({column_name}) REFERENCES tasks(id) ON DELETE CASCADE;"
                    ))
                    logger.info(f"✅ Обновлено ограничение {table_name}_{column_name}_fkey с CASCADE")

                except Exception as e:
                    logger.warning(f"⚠️ Ошибка при миграции {table_name}.{column_name}: {e}")

            # Миграция: удаляем столбец max_tasks из таблицы users (если он ещё существует)
            try:
                await conn.execute(text(
                    """
                    DO $$
                    BEGIN
                        IF EXISTS (
                            SELECT 1
                            FROM information_schema.columns
                            WHERE table_name = 'users'
                              AND column_name = 'max_tasks'
                        ) THEN
                            ALTER TABLE users DROP COLUMN max_tasks;
                        END IF;
                    END $$;
                    """
                ))
                logger.info("✅ Миграция: столбец max_tasks удален из таблицы users (если существовал)")
            except Exception as e:
                logger.warning(f"⚠️ Ошибка при удалении столбца max_tasks: {e}")

            # Миграция: добавляем столбец is_available для исполнителей
            try:
                await conn.execute(text(
                    """
                    ALTER TABLE users
                    ADD COLUMN IF NOT EXISTS is_available BOOLEAN NOT NULL DEFAULT TRUE;
                    """
                ))
                logger.info("✅ Миграция: столбец is_available добавлен в таблицу users")
            except Exception as e:
                logger.warning(f"⚠️ Ошибка при добавлении столбца is_available: {e}")

            # Миграция: индекс для быстрого поиска доступных исполнителей
            try:
                await conn.execute(text(
                    """
                    DO $$
                    BEGIN
                        IF NOT EXISTS (
                            SELECT 1
                            FROM pg_class c
                            JOIN pg_namespace n ON n.oid = c.relnamespace
                            WHERE c.relname = 'idx_users_role_available'
                              AND c.relkind = 'i'
                        ) THEN
                            CREATE INDEX idx_users_role_available
                                ON users (role, is_available);
                        END IF;
                    END $$;
                    """
                ))
                logger.info("✅ Миграция: индекс idx_users_role_available создан (или уже существовал)")
            except Exception as e:
                logger.warning(f"⚠️ Ошибка при создании индекса idx_users_role_available: {e}")

    except Exception as e:
        logger.warning(f"⚠️ Ошибка при выполнении миграций: {type(e).__name__}: {str(e)}")


async def create_tables():
    """Создает все таблицы в базе данных"""
    try:
        logger.info("Начинаю создание таблиц в базе данных...")
        
        async with engine.begin() as conn:
            # Создаем все таблицы
            await conn.run_sync(Base.metadata.create_all)
        
        logger.info("✅ Все таблицы успешно созданы в базе данных")
        print("✅ Все таблицы успешно созданы в базе данных")
        
        # Выполняем миграции
        await migrate_database()
        
    except Exception as e:
        logger.error(f"❌ Ошибка при создании таблиц: {type(e).__name__}: {str(e)}")
        print(f"❌ Ошибка при создании таблиц: {type(e).__name__}: {str(e)}")
        raise

