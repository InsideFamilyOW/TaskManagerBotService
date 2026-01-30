"""Регистрация всех обработчиков"""
from aiogram import Dispatcher
from . import common, admin, buyer, executor


def register_handlers(dp: Dispatcher):
    """Регистрация всех обработчиков"""
    dp.include_router(common.router)
    
    # 2. Обработчики для администраторов
    dp.include_router(admin.router)
    
    # 3. Обработчики для байеров
    dp.include_router(buyer.router)
    
    # 4. Обработчики для исполнителей
    dp.include_router(executor.router)
