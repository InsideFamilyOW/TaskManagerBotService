-- Создание таблицы для хранения чатов, в которые добавлен бот
CREATE TABLE IF NOT EXISTS chats (
    id SERIAL PRIMARY KEY,
    chat_id BIGINT UNIQUE NOT NULL,
    chat_type VARCHAR(20) NOT NULL,
    chat_title VARCHAR(255),
    bot_status VARCHAR(20) NOT NULL,
    
    -- Права бота (если статус administrator)
    can_post_messages BOOLEAN DEFAULT FALSE,
    can_edit_messages BOOLEAN DEFAULT FALSE,
    can_delete_messages BOOLEAN DEFAULT FALSE,
    can_restrict_members BOOLEAN DEFAULT FALSE,
    can_promote_members BOOLEAN DEFAULT FALSE,
    can_change_info BOOLEAN DEFAULT FALSE,
    can_invite_users BOOLEAN DEFAULT FALSE,
    can_pin_messages BOOLEAN DEFAULT FALSE,
    can_manage_chat BOOLEAN DEFAULT FALSE,
    can_manage_video_chats BOOLEAN DEFAULT FALSE,
    
    -- Метаданные
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    updated_at TIMESTAMP WITH TIME ZONE
);

-- Индексы для оптимизации запросов
CREATE INDEX IF NOT EXISTS idx_chats_chat_id ON chats (chat_id);
CREATE INDEX IF NOT EXISTS idx_chats_status ON chats (bot_status, chat_id);
CREATE INDEX IF NOT EXISTS idx_chats_type ON chats (chat_type, bot_status);
