"""Утилиты для работы с сообщениями Telegram"""
from typing import Tuple, Optional

TELEGRAM_MAX_MESSAGE_LENGTH = 4096


def truncate_message(text: str, max_length: int = TELEGRAM_MAX_MESSAGE_LENGTH) -> Tuple[str, bool]:
    """
    Обрезает сообщение до максимальной длины, если оно превышает лимит.
    
    Args:
        text: Текст сообщения
        max_length: Максимальная длина сообщения (по умолчанию 4096)
    
    Returns:
        Tuple[str, bool]: (обрезанный текст, был ли текст обрезан)
    """
    if len(text) <= max_length:
        return text, False
    
    truncated_text = text[:max_length - 20]
    truncated_text += "\n\n... (сообщение обрезано)"
    
    return truncated_text, True


def truncate_description_in_preview(
    description: str,
    base_text_template: str,
    max_length: int = TELEGRAM_MAX_MESSAGE_LENGTH
) -> Tuple[str, bool]:
    """
    Обрезает описание в превью задачи, если общая длина сообщения превышает лимит.
    
    Args:
        description: Описание задачи
        base_text_template: Шаблон текста без описания (с плейсхолдером {description})
        max_length: Максимальная длина сообщения
    
    Returns:
        Tuple[str, bool]: (финальный текст с обрезанным описанием, было ли обрезано)
    """
    full_text = base_text_template.format(description=description)
    
    if len(full_text) <= max_length:
        return full_text, False
    
    template_without_desc = base_text_template.format(description="")
    max_desc_length = max_length - len(template_without_desc) - 30
    
    if max_desc_length <= 0:
        return truncate_message(full_text, max_length)
    
    truncated_description = description[:max_desc_length]
    truncated_description += "\n\n... (описание обрезано)"
    
    final_text = base_text_template.format(description=truncated_description)
    
    return final_text, True


def truncate_text_if_needed(text: str, max_length: int = TELEGRAM_MAX_MESSAGE_LENGTH) -> str:
    """
    Обрезает текст, если он превышает максимальную длину.
    Используется для готовых сообщений, где нужно просто обрезать весь текст.
    
    Args:
        text: Текст сообщения
        max_length: Максимальная длина сообщения
    
    Returns:
        str: Обрезанный текст (если нужно) или исходный текст
    """
    if len(text) <= max_length:
        return text
    
    truncated_text = text[:max_length - 20]
    truncated_text += "\n\n... (сообщение обрезано)"
    
    return truncated_text


def check_message_length(
    description: str,
    base_text_template: str,
    max_length: int = TELEGRAM_MAX_MESSAGE_LENGTH
) -> Tuple[bool, int]:
    """
    Проверяет, будет ли сообщение слишком длинным с данным описанием.
    
    Args:
        description: Описание задачи
        base_text_template: Шаблон текста без описания (с плейсхолдером {description})
        max_length: Максимальная длина сообщения
    
    Returns:
        Tuple[bool, int]: (превышает ли лимит, текущая длина сообщения)
    """
    full_text = base_text_template.format(description=description)
    exceeds_limit = len(full_text) > max_length
    return exceeds_limit, len(full_text)


def get_max_description_length(
    base_text_template: str,
    max_length: int = TELEGRAM_MAX_MESSAGE_LENGTH
) -> int:
    """
    Вычисляет максимальную допустимую длину описания для данного шаблона.
    
    Args:
        base_text_template: Шаблон текста без описания (с плейсхолдером {description})
        max_length: Максимальная длина сообщения
    
    Returns:
        int: Максимальная длина описания
    """
    template_without_desc = base_text_template.format(description="")
    max_desc_length = max_length - len(template_without_desc) - 50
    return max(0, max_desc_length)
