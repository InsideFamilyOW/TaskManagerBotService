-- Миграция: создание таблицы для связи исполнителей и баеров
-- Дата: 2025-01-12

CREATE TABLE IF NOT EXISTS executor_buyer_assignments (
    executor_id INTEGER NOT NULL,
    buyer_id INTEGER NOT NULL,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    created_by_id INTEGER,
    PRIMARY KEY (executor_id, buyer_id),
    FOREIGN KEY (executor_id) REFERENCES users(id) ON DELETE CASCADE,
    FOREIGN KEY (buyer_id) REFERENCES users(id) ON DELETE CASCADE,
    FOREIGN KEY (created_by_id) REFERENCES users(id),
    CONSTRAINT uq_executor_buyer UNIQUE (executor_id, buyer_id)
);

-- Создаем индексы для быстрого поиска
CREATE INDEX IF NOT EXISTS idx_executor_buyer_executor ON executor_buyer_assignments(executor_id);
CREATE INDEX IF NOT EXISTS idx_executor_buyer_buyer ON executor_buyer_assignments(buyer_id);

