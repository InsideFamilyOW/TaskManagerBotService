-- Миграция для оптимизации пагинации и ускорения запросов
-- Дата: 2026-01-16
-- Описание: Добавляет составные индексы для оптимизации пагинации пользователей и задач

-- ==============================================
-- ИНДЕКСЫ ДЛЯ ПОЛЬЗОВАТЕЛЕЙ
-- ==============================================

-- Индекс для пагинации активных пользователей с сортировкой по дате создания
CREATE INDEX IF NOT EXISTS idx_users_active_created 
ON users(is_active, created_at DESC) 
WHERE is_active = TRUE;

-- Индекс для пагинации пользователей по роли с сортировкой
CREATE INDEX IF NOT EXISTS idx_users_role_active_created 
ON users(role, is_active, created_at DESC) 
WHERE is_active = TRUE;

-- Индекс для быстрого подсчета пользователей по роли
CREATE INDEX IF NOT EXISTS idx_users_role_active 
ON users(role, is_active) 
WHERE is_active = TRUE;

-- ==============================================
-- ИНДЕКСЫ ДЛЯ ЗАДАЧ (уже есть в models.py, но дублируем для безопасности)
-- ==============================================

-- Индекс для пагинации задач байера
CREATE INDEX IF NOT EXISTS idx_tasks_creator_status_date 
ON tasks(created_by_id, status, created_at DESC);

-- Индекс для пагинации задач исполнителя  
CREATE INDEX IF NOT EXISTS idx_tasks_executor_status_date 
ON tasks(executor_id, status, created_at DESC);

-- Индекс для поиска PENDING задач от конкретных баеров (для исполнителя)
CREATE INDEX IF NOT EXISTS idx_tasks_status_creator_date 
ON tasks(status, created_by_id, created_at DESC) 
WHERE status = 'pending';

-- ==============================================
-- ИНДЕКСЫ ДЛЯ НАЗНАЧЕНИЙ ИСПОЛНИТЕЛЕЙ
-- ==============================================

-- Индекс для быстрого поиска баеров исполнителя
CREATE INDEX IF NOT EXISTS idx_executor_buyer_assignments_executor 
ON executor_buyer_assignments(executor_id, created_at DESC);

-- Индекс для быстрого поиска исполнителей баера
CREATE INDEX IF NOT EXISTS idx_executor_buyer_assignments_buyer 
ON executor_buyer_assignments(buyer_id, created_at DESC);

-- ==============================================
-- ANALYZE ДЛЯ ОБНОВЛЕНИЯ СТАТИСТИКИ
-- ==============================================

ANALYZE users;
ANALYZE tasks;
ANALYZE executor_buyer_assignments;

