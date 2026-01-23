-- Добавление флага доступности исполнителя для получения новых задач
ALTER TABLE users
    ADD COLUMN IF NOT EXISTS is_available BOOLEAN NOT NULL DEFAULT TRUE;

-- Индекс для быстрого поиска доступных исполнителей по роли
CREATE INDEX IF NOT EXISTS idx_users_role_available
    ON users (role, is_available);


