-- Миграция для оптимизации индексов базы данных
-- Дата: 2026-01-16
-- Описание: Добавление составных индексов для ускорения запросов с пагинацией и фильтрацией

-- Добавляем составные индексы для оптимизации запросов задач

-- Индекс для быстрого получения задач байера с фильтрацией по статусу и сортировкой
CREATE INDEX IF NOT EXISTS idx_tasks_creator_status_date 
ON tasks(created_by_id, status, created_at DESC);

-- Индекс для быстрого получения задач исполнителя с фильтрацией по статусу и сортировкой
CREATE INDEX IF NOT EXISTS idx_tasks_executor_status_date 
ON tasks(executor_id, status, created_at DESC);

-- Индекс для получения PENDING задач от конкретных баеров (для исполнителей)
CREATE INDEX IF NOT EXISTS idx_tasks_status_creator_date 
ON tasks(status, created_by_id, created_at DESC);

-- Оптимизация индекса для пользователей (роль + активность + направление)
CREATE INDEX IF NOT EXISTS idx_users_role_active_direction 
ON users(role, is_active, direction);

-- Индекс для быстрого подсчета активных пользователей по роли
CREATE INDEX IF NOT EXISTS idx_users_role_active 
ON users(role, is_active);

COMMENT ON INDEX idx_tasks_creator_status_date IS 'Оптимизация запросов задач байера с фильтрацией';
COMMENT ON INDEX idx_tasks_executor_status_date IS 'Оптимизация запросов задач исполнителя с фильтрацией';
COMMENT ON INDEX idx_tasks_status_creator_date IS 'Оптимизация запросов PENDING задач для исполнителей';
COMMENT ON INDEX idx_users_role_active_direction IS 'Быстрый поиск исполнителей по направлению';
COMMENT ON INDEX idx_users_role_active IS 'Быстрый подсчет пользователей по роли';

