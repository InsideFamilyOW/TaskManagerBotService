"""Клавиатуры для просмотра профиля исполнителя байером."""

from aiogram.types import InlineKeyboardMarkup
from aiogram.utils.keyboard import InlineKeyboardBuilder

from db.models import TaskStatus


class BuyerProfileKeyboards:
    """Профиль исполнителя для байера."""

    @staticmethod
    def executor_profile(executor_id: int) -> InlineKeyboardMarkup:
        """Клавиатура под профилем исполнителя."""
        builder = InlineKeyboardBuilder()

        # Задачи по статусам
        builder.button(
            text="🟡 Задачи в работе",
            callback_data=f"buyer_exec_tasks_{executor_id}_{TaskStatus.IN_PROGRESS.value}",
        )
        builder.button(
            text="⏳ Ожидающие задачи",
            callback_data=f"buyer_exec_tasks_{executor_id}_{TaskStatus.PENDING.value}",
        )
        builder.button(
            text="🎉 Одобренные задачи",
            callback_data=f"buyer_exec_tasks_{executor_id}_{TaskStatus.APPROVED.value}",
        )

        builder.adjust(1)
        return builder.as_markup()


