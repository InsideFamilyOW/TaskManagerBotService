"""Обработчики файлов для байера"""
from aiogram import Router, F, Bot
from aiogram.types import Message, CallbackQuery
from aiogram.fsm.context import FSMContext
from datetime import datetime

from db.engine import AsyncSessionLocal
from db.queries import UserQueries, TaskQueries, MessageQueries, FileQueries
from db.models import UserRole, TaskStatus, FileType
from bot.keyboards.common_kb import CommonKeyboards
from bot.keyboards.buyer_kb import BuyerKeyboards
from states.buyer_states import BuyerStates
from bot.utils.file_handler import FileHandler
from bot.utils.photo_handler import PhotoHandler
from log import logger

router = Router()


# ============ ПРОСМОТР И СКАЧИВАНИЕ ФАЙЛОВ (приоритетные обработчики) ============

@router.callback_query(F.data.startswith("buyer_view_files_"))
async def callback_view_task_files(callback: CallbackQuery, state: FSMContext):
    """Просмотр файлов задачи"""
    task_id = int(callback.data.replace("buyer_view_files_", ""))
    logger.info(f"Обработчик buyer_view_files вызван для task_id={task_id}")
    
    async with AsyncSessionLocal() as session:
        task = await TaskQueries.get_task_by_id(session, task_id)
        
        if not task:
            await callback.answer("❌ Задача не найдена", show_alert=True)
            return
        
        # Получаем файлы задачи
        files = await FileQueries.get_task_files(session, task_id)
        
        if not files:
            await callback.answer("📭 Нет файлов", show_alert=True)
            return
        
        # Группируем файлы по типам
        initial_files = [f for f in files if f.file_type == FileType.INITIAL]
        result_files = [f for f in files if f.file_type == FileType.RESULT]
        message_files = [f for f in files if f.file_type == FileType.MESSAGE]
        
        text = f"""
📎 <b>ФАЙЛЫ ЗАДАЧИ {task.task_number}</b>
━━━━━━━━━━━━━━━━━━━━━━━━━━

"""
        
        if initial_files:
            text += f"📤 <b>Исходные файлы ({len(initial_files)}):</b>\n"
            for f in initial_files:
                size_mb = f.file_size / (1024 * 1024) if f.file_size else 0
                uploader_name = f"{f.uploader.first_name} {f.uploader.last_name or ''}".strip() if f.uploader else "Неизвестно"
                text += f"• {f.file_name} ({size_mb:.2f} МБ)\n  👤 {uploader_name}\n"
            text += "\n"
        
        if result_files:
            text += f"📥 <b>Файлы результата ({len(result_files)}):</b>\n"
            for f in result_files:
                size_mb = f.file_size / (1024 * 1024) if f.file_size else 0
                uploader_name = f"{f.uploader.first_name} {f.uploader.last_name or ''}".strip() if f.uploader else "Неизвестно"
                text += f"• {f.file_name} ({size_mb:.2f} МБ)\n  👤 {uploader_name}\n"
            text += "\n"
        
        if message_files:
            text += f"💬 <b>Файлы из сообщений ({len(message_files)}):</b>\n"
            for f in message_files:
                size_mb = f.file_size / (1024 * 1024) if f.file_size else 0
                uploader_name = f"{f.uploader.first_name} {f.uploader.last_name or ''}".strip() if f.uploader else "Неизвестно"
                text += f"• {f.file_name} ({size_mb:.2f} МБ)\n  👤 {uploader_name}\n\n"
        
        text += "\n━━━━━━━━━━━━━━━━━━━━━━━━━━"
        
        await callback.message.edit_text(
            text,
            reply_markup=BuyerKeyboards.task_files_actions(task_id, files),
            parse_mode="HTML"
        )
    
    await callback.answer()


@router.callback_query(F.data.startswith("buyer_download_file_"))
async def callback_download_file(callback: CallbackQuery, bot: Bot, state: FSMContext):
    """Скачивание файла"""
    file_id = int(callback.data.replace("buyer_download_file_", ""))
    logger.info(f"Обработчик buyer_download_file вызван для file_id={file_id}")
    
    async with AsyncSessionLocal() as session:
        file_record = await FileQueries.get_file_by_id(session, file_id)
        
        if not file_record:
            await callback.answer("❌ Файл не найден", show_alert=True)
            return
        
        try:
            telegram_file_id = FileQueries.get_telegram_file_id(file_record)
            
            if telegram_file_id:
                if file_record.mime_type and file_record.mime_type.startswith('image/'):
                    await bot.send_photo(callback.from_user.id, telegram_file_id, caption=file_record.file_name)
                elif file_record.mime_type and file_record.mime_type.startswith('video/'):
                    await bot.send_video(callback.from_user.id, telegram_file_id, caption=file_record.file_name)
                else:
                    await bot.send_document(callback.from_user.id, telegram_file_id, caption=file_record.file_name)
                await callback.answer("✅ Файл отправлен")
            elif file_record.file_data:
                from aiogram.types import BufferedInputFile
                file_bytes = FileHandler.decode_file_base64(file_record.file_data)
                if file_bytes:
                    input_file = BufferedInputFile(file_bytes, filename=file_record.file_name)
                    if file_record.mime_type and file_record.mime_type.startswith('image/'):
                        await bot.send_photo(callback.from_user.id, input_file, caption=file_record.file_name)
                    elif file_record.mime_type and file_record.mime_type.startswith('video/'):
                        await bot.send_video(callback.from_user.id, input_file, caption=file_record.file_name)
                    else:
                        await bot.send_document(callback.from_user.id, input_file, caption=file_record.file_name)
                    await callback.answer("✅ Файл отправлен")
                else:
                    await callback.answer("❌ Ошибка декодирования файла", show_alert=True)
            elif file_record.photo_base64:
                from aiogram.types import BufferedInputFile
                photo_bytes = PhotoHandler.decode_photo_base64(file_record.photo_base64)
                if photo_bytes:
                    input_file = BufferedInputFile(photo_bytes, filename=file_record.file_name)
                    await bot.send_photo(callback.from_user.id, input_file, caption=file_record.file_name)
                    await callback.answer("✅ Фото отправлено")
                else:
                    await callback.answer("❌ Ошибка декодирования фото", show_alert=True)
            elif file_record.file_path:
                if file_record.file_path.startswith("telegram_file_id:"):
                    telegram_file_id = file_record.file_path.replace("telegram_file_id:", "")
                    if file_record.mime_type and file_record.mime_type.startswith('image/'):
                        await bot.send_photo(callback.from_user.id, telegram_file_id, caption=file_record.file_name)
                    elif file_record.mime_type and file_record.mime_type.startswith('video/'):
                        await bot.send_video(callback.from_user.id, telegram_file_id, caption=file_record.file_name)
                    else:
                        await bot.send_document(callback.from_user.id, telegram_file_id, caption=file_record.file_name)
                    await callback.answer("✅ Файл отправлен")
                else:
                    import os
                    if os.path.exists(file_record.file_path):
                        with open(file_record.file_path, 'rb') as f:
                            if file_record.mime_type and file_record.mime_type.startswith('image/'):
                                await bot.send_photo(callback.from_user.id, f)
                            elif file_record.mime_type and file_record.mime_type.startswith('video/'):
                                await bot.send_video(callback.from_user.id, f, caption=file_record.file_name)
                            else:
                                await bot.send_document(callback.from_user.id, f, caption=file_record.file_name)
                        await callback.answer("✅ Файл отправлен")
                    else:
                        await callback.answer("❌ Файл не найден на диске", show_alert=True)
            else:
                await callback.answer("❌ Файл недоступен", show_alert=True)
        except Exception as e:
            logger.error(f"Ошибка отправки файла: {e}")
            await callback.answer("❌ Ошибка отправки файла", show_alert=True)


# ============ ФАЙЛЫ ПРИ СОЗДАНИИ ЗАДАЧИ ============

@router.callback_query(F.data == "edit_field_files", BuyerStates.waiting_task_confirmation)
async def edit_field_files(callback: CallbackQuery, state: FSMContext):
    """Редактирование файлов задачи"""
    data = await state.get_data()
    files = data.get('initial_files', [])
    
    # Если есть файлы, показываем их список
    if files:
        files_text = "\n".join([
            f"{'📷' if f.get('is_photo') else '📎'} {f['file_name']} ({f['file_size'] / (1024 * 1024):.2f} МБ)"
            for f in files
        ])
        
        await callback.message.edit_text(
            f"""
📎 <b>ФАЙЛЫ ЗАДАЧИ</b>
━━━━━━━━━━━━━━━━━━━━━━━━━━

<b>Шаг 6/6: Прикрепите файлы</b>

📋 <b>Уже добавлено ({len(files)}/10 файлов):</b>

{files_text}

━━━━━━━━━━━━━━━━━━━━━━━━━━

Нажмите на файл чтобы просмотреть его или добавьте новые файлы.
""",
            reply_markup=CommonKeyboards.file_list_with_actions(files, "initial"),
            parse_mode="HTML"
        )
    else:
        await callback.message.edit_text(
            """
📎 <b>ФАЙЛЫ ЗАДАЧИ</b>
━━━━━━━━━━━━━━━━━━━━━━━━━━

<b>Шаг 6/6: Прикрепите файлы</b>

Отправьте файлы задачи (до 10 файлов).
Когда закончите, нажмите "Завершить загрузку".
""",
            reply_markup=CommonKeyboards.file_actions(),
            parse_mode="HTML"
        )
    
    await state.set_state(BuyerStates.waiting_task_files)
    await callback.answer()


@router.callback_query(F.data.startswith("view_file_initial:"), BuyerStates.waiting_task_files)
async def view_initial_file(callback: CallbackQuery, state: FSMContext, bot: Bot):
    """Просмотр файла при создании задачи"""
    file_idx = int(callback.data.split(":")[1])
    data = await state.get_data()
    files = data.get('initial_files', [])
    
    if file_idx >= len(files):
        await callback.answer("❌ Файл не найден", show_alert=True)
        return
    
    file_info = files[file_idx]
    
    try:
        # Отправляем файл по file_id
        if file_info.get('is_photo'):
            await bot.send_photo(
                callback.from_user.id,
                file_info['file_id'],
                caption=f"{file_info['file_name']}\n📊 Размер: {file_info['file_size'] / (1024 * 1024):.2f} МБ"
            )
        else:
            await bot.send_document(
                callback.from_user.id,
                file_info['file_id'],
                caption=f"{file_info['file_name']}\n📊 Размер: {file_info['file_size'] / (1024 * 1024):.2f} МБ"
            )
        await callback.answer("✅ Файл отправлен")
    except Exception as e:
        logger.error(f"Ошибка отправки файла: {e}")
        await callback.answer("❌ Ошибка отправки файла", show_alert=True)


@router.callback_query(F.data == "add_more_files_initial", BuyerStates.waiting_task_files)
async def add_more_initial_files(callback: CallbackQuery, state: FSMContext):
    """Добавить еще файлы при создании задачи"""
    data = await state.get_data()
    files = data.get('initial_files', [])
    
    await callback.message.edit_text(
        f"""
📎 <b>ДОБАВИТЬ ФАЙЛЫ</b>
━━━━━━━━━━━━━━━━━━━━━━━━━━

Отправьте файлы задачи (до 10 файлов).

📋 <b>Уже добавлено: {len(files)}/10</b>

━━━━━━━━━━━━━━━━━━━━━━━━━━

Когда закончите, нажмите "Завершить загрузку".
""",
        reply_markup=CommonKeyboards.file_actions(),
        parse_mode="HTML"
    )
    await callback.answer()


@router.message(BuyerStates.waiting_task_files, F.document | F.photo | F.video)
async def process_initial_file(message: Message, state: FSMContext, bot: Bot):
    """Обработка файла при создании задачи"""
    data = await state.get_data()
    files = data.get('initial_files', [])
    
    if len(files) >= 10:
        await message.answer("❌ Максимум 10 файлов!")
        return
    
    # Сохраняем информацию о файле
    if message.photo:
        # Фотография - будет храниться в base64
        photo = message.photo[-1]
        file_info = {
            'file_id': photo.file_id,
            'file_name': f"photo_{datetime.now().strftime('%Y%m%d_%H%M%S')}.jpg",
            'mime_type': "image/jpeg",
            'file_size': photo.file_size,
            'is_photo': True,
            'is_video': False
        }
    elif message.video:
        # Видео
        video = message.video
        file_info = {
            'file_id': video.file_id,
            'file_name': video.file_name or f"video_{datetime.now().strftime('%Y%m%d_%H%M%S')}.mp4",
            'mime_type': video.mime_type or "video/mp4",
            'file_size': video.file_size,
            'is_photo': False,
            'is_video': True
        }
    elif message.document:
        # Проверяем, является ли документ фотографией или видео
        is_photo = PhotoHandler.is_photo_mime_type(message.document.mime_type)
        is_video = message.document.mime_type and message.document.mime_type.startswith('video/')
        file_info = {
            'file_id': message.document.file_id,
            'file_name': message.document.file_name,
            'mime_type': message.document.mime_type,
            'file_size': message.document.file_size,
            'is_photo': is_photo,
            'is_video': is_video
        }
    else:
        return
    
    files.append(file_info)
    await state.update_data(initial_files=files)
    
    if file_info.get('is_photo'):
        file_type = "📷 Фото"
    elif file_info.get('is_video'):
        file_type = "🎥 Видео"
    else:
        file_type = "📎 Файл"
    
    # Формируем список файлов
    files_text = "\n".join([
        f"{'📷' if f.get('is_photo') else '🎥' if f.get('is_video') else '📎'} {f['file_name']} ({f['file_size'] / (1024 * 1024):.2f} МБ)"
        for f in files
    ])
    
    await message.answer(
        f"""
✅ {file_type} добавлен!

━━━━━━━━━━━━━━━━━━━━━━━━━━

📋 <b>Добавлено ({len(files)}/10 файлов):</b>

{files_text}

━━━━━━━━━━━━━━━━━━━━━━━━━━

Нажмите на файл чтобы просмотреть его или добавьте новые файлы.
""",
        reply_markup=CommonKeyboards.file_list_with_actions(files, "initial"),
        parse_mode="HTML"
    )


@router.callback_query(F.data == "files_done", BuyerStates.waiting_task_files)
async def files_upload_done(callback: CallbackQuery, state: FSMContext):
    """Завершение загрузки файлов при создании задачи"""
    data = await state.get_data()
    files = data.get('initial_files', [])
    
    # Возвращаемся к превью задачи через динамический импорт для избежания циклической зависимости
    try:
        from bot.handlers.buyer import show_task_preview
        await show_task_preview(callback.message, state, is_edit=True)
    except ImportError:
        # Fallback: просто переходим к подтверждению
        await callback.message.edit_text(
            f"✅ Файлы загружены ({len(files)} файлов)\n\n"
            f"Переходим к подтверждению создания задачи...",
            parse_mode="HTML"
        )
        await state.set_state(BuyerStates.waiting_task_confirmation)
    
    await callback.answer(f"Загружено файлов: {len(files)}")


# ============ ФАЙЛЫ В СООБЩЕНИЯХ ============

@router.callback_query(F.data.startswith("buyer_attach_file_"))
async def callback_attach_file_to_message(callback: CallbackQuery, state: FSMContext):
    """Прикрепление файла к сообщению"""
    task_id = int(callback.data.replace("buyer_attach_file_", ""))
    logger.info(f"Обработчик buyer_attach_file вызван для task_id={task_id}")
    
    async with AsyncSessionLocal() as session:
        task = await TaskQueries.get_task_by_id(session, task_id)
        
        if not task:
            await callback.answer("❌ Задача не найдена", show_alert=True)
            return
    
    data = await state.get_data()
    # Если уже есть сообщение в процессе отправки, добавляем файл к нему
    if data.get('message_task_id') == task_id:
        await callback.message.edit_text(
            """
📎 <b>ПРИКРЕПИТЬ ФАЙЛ</b>
━━━━━━━━━━━━━━━━━━━━━━━━━━

Отправьте файл, который будет прикреплен к сообщению.
Можно отправить несколько файлов.
""",
            parse_mode="HTML"
        )
        await state.set_state(BuyerStates.waiting_message_file)
    else:
        # Начинаем новое сообщение с файлом
        await state.update_data(
            message_task_id=task_id,
            message_files=[]
        )
        await callback.message.edit_text(
            """
📎 <b>СООБЩЕНИЕ С ФАЙЛОМ</b>
━━━━━━━━━━━━━━━━━━━━━━━━━━

Отправьте файлы, которые будут прикреплены к сообщению.
Можно отправить несколько файлов (до 10).
После загрузки файлов напишите текст сообщения.
""",
            parse_mode="HTML"
        )
        await state.set_state(BuyerStates.waiting_message_file)
    
    await callback.answer()


@router.message(BuyerStates.waiting_message_file, F.document | F.photo)
async def process_message_file(message: Message, state: FSMContext, bot: Bot):
    """Обработка файла для сообщения"""
    data = await state.get_data()
    files = data.get('message_files', [])
    
    if len(files) >= 10:
        await message.answer("❌ Максимум 10 файлов!")
        return
    
    # Сохраняем информацию о файле
    if message.photo:
        # Фотография - будет храниться в base64
        photo = message.photo[-1]
        file_info = {
            'file_id': photo.file_id,
            'file_name': f"photo_{datetime.now().strftime('%Y%m%d_%H%M%S')}.jpg",
            'mime_type': "image/jpeg",
            'file_size': photo.file_size,
            'is_photo': True,
            'is_video': False
        }
    elif message.video:
        # Видео
        video = message.video
        file_info = {
            'file_id': video.file_id,
            'file_name': video.file_name or f"video_{datetime.now().strftime('%Y%m%d_%H%M%S')}.mp4",
            'mime_type': video.mime_type or "video/mp4",
            'file_size': video.file_size,
            'is_photo': False,
            'is_video': True
        }
    elif message.document:
        # Проверяем, является ли документ фотографией или видео
        is_photo = PhotoHandler.is_photo_mime_type(message.document.mime_type)
        is_video = message.document.mime_type and message.document.mime_type.startswith('video/')
        file_info = {
            'file_id': message.document.file_id,
            'file_name': message.document.file_name,
            'mime_type': message.document.mime_type,
            'file_size': message.document.file_size,
            'is_photo': is_photo,
            'is_video': is_video
        }
    else:
        return
    
    files.append(file_info)
    await state.update_data(message_files=files)
    
    if file_info.get('is_photo'):
        file_type = "📷 Фото"
    elif file_info.get('is_video'):
        file_type = "🎥 Видео"
    else:
        file_type = "📎 Файл"
    
    await message.answer(
        f"✅ {file_type} добавлен ({len(files)}/10)\n\n"
        f"Отправьте еще файлы или напишите текст сообщения."
    )


@router.message(BuyerStates.waiting_message_file)
async def process_message_with_files(message: Message, state: FSMContext, bot: Bot):
    """Обработка текста сообщения с файлами"""
    # Если это еще файл, обрабатываем его
    if message.document or message.photo or message.video:
        await process_message_file(message, state)
        return
    
    # Если это текст или пустое сообщение
    content = message.text.strip() if message.text else "Без текста"
    data = await state.get_data()
    task_id = data['message_task_id']
    files = data.get('message_files', [])
    target_executor_id = data.get('message_executor_id')
    
    # Если нет файлов и нет текста, просим что-то отправить
    if not files and content == "Без текста":
        await message.answer(
            "❌ Пожалуйста, отправьте файлы или напишите текст сообщения.\n\n"
            "Или нажмите 'Отменить', чтобы вернуться назад."
        )
        return
    
    async with AsyncSessionLocal() as session:
        buyer = await UserQueries.get_user_by_telegram_id(session, message.from_user.id)
        task = await TaskQueries.get_task_by_id(session, task_id)
        
        if not task:
            await message.answer("❌ Задача не найдена")
            await state.clear()
            return
        
        target_executor = None
        if target_executor_id:
            target_executor = await UserQueries.get_user_by_id(session, target_executor_id)
        else:
            target_executor = task.executor
        
        if not target_executor:
            await message.answer("❌ Нет доступного исполнителя для отправки сообщения")
            await state.clear()
            return
        
        # Сохраняем сообщение
        await MessageQueries.create_message(
            session=session,
            task_id=task_id,
            sender_id=buyer.id,
            content=content
        )
        
        # Сохраняем файлы в БД
        for file_info in files:
            is_photo = file_info.get('is_photo', False)
            
            if is_photo:
                # Сохраняем фото в base64
                if 'file_id' in file_info:
                    # Определяем тип фото
                    if file_info.get('mime_type') and file_info['mime_type'] != 'image/jpeg':
                        # Это файл-фото
                        photo_data = await PhotoHandler.download_and_encode_photo_from_file(bot, file_info['file_id'])
                    else:
                        # Это обычная фотография
                        photo_size = type('obj', (object,), {'file_id': file_info['file_id'], 'file_size': file_info['file_size']})
                        photo_data = await PhotoHandler.download_and_encode_photo(bot, photo_size)
                    
                    if photo_data:
                        base64_string, file_size, mime_type = photo_data
                        await FileQueries.create_file(
                            session=session,
                            task_id=task_id,
                            file_type=FileType.MESSAGE,
                            file_name=file_info['file_name'],
                            file_data=base64_string,
                            file_size=file_size,
                            uploaded_by_id=buyer.id,
                            mime_type=mime_type
                        )
                        # Отправляем файл в канал
                        from bot.utils.log_channel import LogChannel
                        await LogChannel.log_file_uploaded(
                            bot=bot,
                            task=task,
                            file_id=file_info['file_id'],
                            file_name=file_info['file_name'],
                            file_type="MESSAGE",
                            uploaded_by=buyer,
                            mime_type=mime_type
                        )
            else:
                # Сохраняем обычный файл в БД (base64) - включая видео
                # Для больших файлов (>20MB) сохраняем только file_id
                MAX_SIZE_FOR_BASE64 = 20 * 1024 * 1024  # 20 MB
                file_size_from_info = file_info.get('file_size', 0)
                
                try:
                    # Если файл больше 20MB или является видео, сохраняем только file_id
                    if file_size_from_info > MAX_SIZE_FOR_BASE64 or file_info.get('is_video', False):
                        final_mime_type = file_info.get('mime_type') or "application/octet-stream"
                        await FileQueries.create_file(
                            session=session,
                            task_id=task_id,
                            file_type=FileType.MESSAGE,
                            file_name=file_info['file_name'],
                            file_data=None,
                            file_size=file_size_from_info,
                            uploaded_by_id=buyer.id,
                            mime_type=final_mime_type,
                            telegram_file_id=file_info['file_id']
                        )
                        # Отправляем файл в канал
                        from bot.utils.log_channel import LogChannel
                        await LogChannel.log_file_uploaded(
                            bot=bot,
                            task=task,
                            file_id=file_info['file_id'],
                            file_name=file_info['file_name'],
                            file_type="MESSAGE",
                            uploaded_by=buyer,
                            mime_type=final_mime_type
                        )
                    else:
                        # Пытаемся скачать и сохранить в base64
                        file_data_tuple = await FileHandler.download_and_encode_file(bot, file_info['file_id'])
                        if file_data_tuple:
                            base64_string, file_size, mime_type = file_data_tuple
                            final_mime_type = file_info.get('mime_type') or mime_type
                            await FileQueries.create_file(
                                session=session,
                                task_id=task_id,
                                file_type=FileType.MESSAGE,
                                file_name=file_info['file_name'],
                                file_data=base64_string,
                                file_size=file_size,
                                uploaded_by_id=buyer.id,
                                mime_type=final_mime_type
                            )
                            # Отправляем файл в канал
                            from bot.utils.log_channel import LogChannel
                            await LogChannel.log_file_uploaded(
                                bot=bot,
                                task=task,
                                file_id=file_info['file_id'],
                                file_name=file_info['file_name'],
                                file_type="MESSAGE",
                                uploaded_by=buyer,
                                mime_type=final_mime_type
                            )
                        else:
                            # Если не удалось скачать, сохраняем только file_id
                            logger.warning(f"Не удалось скачать файл {file_info.get('file_name')}, сохраняем только file_id")
                            final_mime_type = file_info.get('mime_type') or "application/octet-stream"
                            await FileQueries.create_file(
                                session=session,
                                task_id=task_id,
                                file_type=FileType.MESSAGE,
                                file_name=file_info['file_name'],
                                file_data=None,
                                file_size=file_size_from_info,
                                uploaded_by_id=buyer.id,
                                mime_type=final_mime_type,
                                telegram_file_id=file_info['file_id']
                            )
                except Exception as e:
                    logger.error(f"Ошибка при сохранении файла {file_info.get('file_name')}: {e}, сохраняем только file_id")
                    try:
                        final_mime_type = file_info.get('mime_type') or "application/octet-stream"
                        await FileQueries.create_file(
                            session=session,
                            task_id=task_id,
                            file_type=FileType.MESSAGE,
                            file_name=file_info['file_name'],
                            file_data=None,
                            file_size=file_size_from_info,
                            uploaded_by_id=buyer.id,
                            mime_type=final_mime_type,
                            telegram_file_id=file_info['file_id']
                        )
                    except Exception as e2:
                        logger.error(f"Критическая ошибка при сохранении file_id: {e2}")
                    else:
                        logger.error(f"Не удалось скачать файл {file_info.get('file_name')} (file_id: {file_info.get('file_id')})")
                except Exception as e:
                    logger.error(f"Ошибка при сохранении файла {file_info.get('file_name')}: {e}")
        
        # Отправляем исполнителю с файлами в одном сообщении
        try:
            from aiogram.utils.keyboard import InlineKeyboardBuilder
            from aiogram.types import InputMediaPhoto, InputMediaDocument, InputMediaVideo
            
            builder = InlineKeyboardBuilder()
            builder.button(text="💬 Ответить", callback_data=f"executor_message_{task.id}")
            
            if task.status == TaskStatus.PENDING:
                builder.button(text="▶️ ПРИНЯТЬ ЗАДАЧУ", callback_data=f"executor_take_{task.id}")
                builder.button(text="❌ ОТКАЗАТЬСЯ", callback_data=f"executor_reject_{task.id}")
            
            builder.adjust(1)
            
            files_text = "\n".join([f"• {f['file_name']}" for f in files]) if files else ""
            
            text_message = f"""
💬 <b>СООБЩЕНИЕ ОТ БАЙЕРА</b>
━━━━━━━━━━━━━━━━━━━━━━━━━━

📋 <b>Задача:</b> {task.task_number}
👤 <b>От:</b> {buyer.first_name} {buyer.last_name or ''}

━━━━━━━━━━━━━━━━━━━━━━━━━━

{content}

{f'━━━━━━━━━━━━━━━━━━━━━━━━━━\n\n📎 <b>Прикрепленные файлы:</b>\n{files_text}' if files_text else ''}
"""
            
            # Если есть файлы, отправляем их как media group с первым файлом содержащим caption
            if files:
                media_group = []
                for idx, file_info in enumerate(files):
                    is_photo = file_info.get('is_photo', False)
                    is_video = file_info.get('is_video', False)
                    caption = text_message if idx == 0 else None
                    
                    if is_photo:
                        media_group.append(InputMediaPhoto(
                            media=file_info['file_id'],
                            caption=caption,
                            parse_mode="HTML" if caption else None
                        ))
                    elif is_video:
                        media_group.append(InputMediaVideo(
                            media=file_info['file_id'],
                            caption=caption,
                            parse_mode="HTML" if caption else None
                        ))
                    else:
                        media_group.append(InputMediaDocument(
                            media=file_info['file_id'],
                            caption=caption,
                            parse_mode="HTML" if caption else None
                        ))
                
                # Отправляем media group
                await bot.send_media_group(target_executor.telegram_id, media=media_group)
                
                # Отправляем клавиатуру отдельным сообщением (media group не поддерживает клавиатуры)
                if task.status == TaskStatus.PENDING:
                    await bot.send_message(
                        target_executor.telegram_id,
                        "Выберите действие:",
                        reply_markup=builder.as_markup()
                    )
            else:
                # Если нет файлов, отправляем обычное сообщение с клавиатурой
                await bot.send_message(
                    target_executor.telegram_id,
                    text_message,
                    parse_mode="HTML",
                    reply_markup=builder.as_markup()
                )
                    
        except Exception as e:
            logger.error(f"Ошибка отправки сообщения исполнителю: {e}")
        
        await message.answer(
            f"✅ <b>Сообщение отправлено исполнителю</b>\n\n"
            f"{f'Прикреплено файлов: {len(files)}' if files else ''}",
            parse_mode="HTML"
        )
        
        await state.clear()
        logger.info(f"Байер {buyer.telegram_id} отправил сообщение с файлами по задаче {task.task_number}")


# ============ ЗАГРУЗКА ФАЙЛОВ К ЗАДАЧЕ БАЙЕРОМ ============

@router.callback_query(F.data.startswith("buyer_add_file_"))
async def callback_buyer_add_file_to_task(callback: CallbackQuery, state: FSMContext, bot: Bot):
    """Добавление файла к задаче байером"""
    task_id = int(callback.data.replace("buyer_add_file_", ""))
    logger.info(f"Обработчик buyer_add_file вызван для task_id={task_id}")
    
    async with AsyncSessionLocal() as session:
        task = await TaskQueries.get_task_by_id(session, task_id)
        
        if not task:
            await callback.answer("❌ Задача не найдена", show_alert=True)
            return
        
        # Проверяем, что задача не отменена
        if task.status == TaskStatus.CANCELLED:
            await callback.answer("❌ Эта задача была отменена", show_alert=True)
            return
        
        # Получаем уже существующие файлы задачи
        existing_files = await FileQueries.get_task_files(session, task_id)
        
        await callback.message.edit_text(
            f"""
📎 <b>ДОБАВИТЬ ФАЙЛЫ</b>
━━━━━━━━━━━━━━━━━━━━━━━━━━

Отправьте файлы, которые хотите прикрепить к задаче.
Можно отправить несколько файлов (до 10).

📋 <b>Уже в задаче: {len(existing_files)}/10 файлов</b>

━━━━━━━━━━━━━━━━━━━━━━━━━━

Когда закончите, нажмите "Завершить загрузку".
""",
            reply_markup=CommonKeyboards.file_actions(),
            parse_mode="HTML"
        )
        
        await state.update_data(file_task_id=task_id, task_files=[])
        await state.set_state(BuyerStates.waiting_file_to_task)
    
    await callback.answer()


@router.message(BuyerStates.waiting_file_to_task, F.document | F.photo | F.video)
async def process_buyer_file_to_task(message: Message, state: FSMContext, bot: Bot):
    """Обработка файла от байера к задаче"""
    data = await state.get_data()
    task_id = data.get('file_task_id')
    files = data.get('task_files', [])
    
    async with AsyncSessionLocal() as session:
        existing_files = await FileQueries.get_task_files(session, task_id)
        total_files = len(existing_files) + len(files)
        
        if total_files >= 10:
            await message.answer(f"❌ Максимум 10 файлов! У вас уже {len(existing_files)} файлов в задаче.")
            return
    
    # Сохраняем информацию о файле
    if message.photo:
        # Фотография
        photo = message.photo[-1]
        file_info = {
            'file_id': photo.file_id,
            'file_name': f"photo_{datetime.now().strftime('%Y%m%d_%H%M%S')}.jpg",
            'mime_type': "image/jpeg",
            'file_size': photo.file_size,
            'is_photo': True,
            'is_video': False
        }
    elif message.video:
        # Видео
        video = message.video
        file_info = {
            'file_id': video.file_id,
            'file_name': video.file_name or f"video_{datetime.now().strftime('%Y%m%d_%H%M%S')}.mp4",
            'mime_type': video.mime_type or "video/mp4",
            'file_size': video.file_size,
            'is_photo': False,
            'is_video': True
        }
    elif message.document:
        # Проверяем, является ли документ фотографией или видео
        is_photo = PhotoHandler.is_photo_mime_type(message.document.mime_type)
        is_video = message.document.mime_type and message.document.mime_type.startswith('video/')
        file_info = {
            'file_id': message.document.file_id,
            'file_name': message.document.file_name,
            'mime_type': message.document.mime_type,
            'file_size': message.document.file_size,
            'is_photo': is_photo,
            'is_video': is_video
        }
    else:
        return
    
    files.append(file_info)
    await state.update_data(task_files=files)
    
    if file_info.get('is_photo'):
        file_type = "📷 Фото"
    elif file_info.get('is_video'):
        file_type = "🎥 Видео"
    else:
        file_type = "📎 Файл"
    
    total_in_session = len(files)
    total_overall = len(existing_files) + len(files)
    
    await message.answer(
        f"✅ {file_type} добавлен!\n\n"
        f"📊 В этой сессии: {total_in_session}\n"
        f"📋 Всего в задаче: {total_overall}/10\n\n"
        f"Отправьте еще файлы или нажмите 'Завершить загрузку'.",
        reply_markup=CommonKeyboards.file_actions()
    )


@router.callback_query(F.data == "files_done", BuyerStates.waiting_file_to_task)
async def buyer_files_to_task_done(callback: CallbackQuery, state: FSMContext, bot: Bot):
    """Завершение загрузки файлов байером"""
    data = await state.get_data()
    task_id = data.get('file_task_id')
    files = data.get('task_files', [])
    
    if not files:
        await callback.answer("❌ Не выбрано ни одного файла", show_alert=True)
        return
    
    async with AsyncSessionLocal() as session:
        buyer = await UserQueries.get_user_by_telegram_id(session, callback.from_user.id)
        task = await TaskQueries.get_task_by_id(session, task_id)
        
        if not task:
            await callback.answer("❌ Задача не найдена или была удалена", show_alert=True)
            await state.clear()
            return
        
        # Проверяем, что задача не отменена
        if task.status == TaskStatus.CANCELLED:
            await callback.answer("❌ Эта задача была отменена", show_alert=True)
            await state.clear()
            return
        
        # Сохраняем файлы в БД
        saved_count = 0
        for file_info in files:
            is_photo = file_info.get('is_photo', False)
            
            if is_photo:
                # Сохраняем фото в base64
                if 'file_id' in file_info:
                    # Определяем тип фото
                    if file_info.get('mime_type') and file_info['mime_type'] != 'image/jpeg':
                        # Это файл-фото
                        photo_data = await PhotoHandler.download_and_encode_photo_from_file(bot, file_info['file_id'])
                    else:
                        # Это обычная фотография
                        photo_size = type('obj', (object,), {'file_id': file_info['file_id'], 'file_size': file_info.get('file_size', 0)})
                        photo_data = await PhotoHandler.download_and_encode_photo(bot, photo_size)
                    
                    if photo_data:
                        base64_string, file_size, mime_type = photo_data
                        await FileQueries.create_file(
                            session=session,
                            task_id=task_id,
                            file_type=FileType.MESSAGE,
                            file_name=file_info['file_name'],
                            file_data=base64_string,
                            file_size=file_size,
                            uploaded_by_id=buyer.id,
                            mime_type=mime_type
                        )
                        # Отправляем файл в канал
                        from bot.utils.log_channel import LogChannel
                        await LogChannel.log_file_uploaded(
                            bot=bot,
                            task=task,
                            file_id=file_info['file_id'],
                            file_name=file_info['file_name'],
                            file_type="MESSAGE",
                            uploaded_by=buyer,
                            mime_type=mime_type
                        )
                        saved_count += 1
            else:
                # Сохраняем обычный файл в БД (base64) - включая видео
                # Для больших файлов (>20MB) сохраняем только file_id
                MAX_SIZE_FOR_BASE64 = 20 * 1024 * 1024  # 20 MB
                file_size_from_info = file_info.get('file_size', 0)
                
                try:
                    # Если файл больше 20MB или является видео, сохраняем только file_id
                    if file_size_from_info > MAX_SIZE_FOR_BASE64 or file_info.get('is_video', False):
                        final_mime_type = file_info.get('mime_type') or "application/octet-stream"
                        await FileQueries.create_file(
                            session=session,
                            task_id=task_id,
                            file_type=FileType.MESSAGE,
                            file_name=file_info['file_name'],
                            file_data=None,
                            file_size=file_size_from_info,
                            uploaded_by_id=buyer.id,
                            mime_type=final_mime_type,
                            telegram_file_id=file_info['file_id']
                        )
                        # Отправляем файл в канал
                        from bot.utils.log_channel import LogChannel
                        await LogChannel.log_file_uploaded(
                            bot=bot,
                            task=task,
                            file_id=file_info['file_id'],
                            file_name=file_info['file_name'],
                            file_type="MESSAGE",
                            uploaded_by=buyer,
                            mime_type=final_mime_type
                        )
                        saved_count += 1
                        logger.info(f"Большой файл сохранен с file_id: {file_info.get('file_name')} ({file_size_from_info / (1024*1024):.2f} MB)")
                    else:
                        # Пытаемся скачать и сохранить в base64
                        file_data_tuple = await FileHandler.download_and_encode_file(bot, file_info['file_id'])
                        if file_data_tuple:
                            base64_string, file_size, mime_type = file_data_tuple
                            # Используем mime_type из file_info, если он есть (для видео это важно)
                            final_mime_type = file_info.get('mime_type') or mime_type
                            await FileQueries.create_file(
                                session=session,
                                task_id=task_id,
                                file_type=FileType.MESSAGE,
                                file_name=file_info['file_name'],
                                file_data=base64_string,
                                file_size=file_size,
                                uploaded_by_id=buyer.id,
                                mime_type=final_mime_type
                            )
                            # Отправляем файл в канал
                            from bot.utils.log_channel import LogChannel
                            await LogChannel.log_file_uploaded(
                                bot=bot,
                                task=task,
                                file_id=file_info['file_id'],
                                file_name=file_info['file_name'],
                                file_type="MESSAGE",
                                uploaded_by=buyer,
                                mime_type=final_mime_type
                            )
                            saved_count += 1
                        else:
                            # Если не удалось скачать, сохраняем только file_id
                            logger.warning(f"Не удалось скачать файл {file_info.get('file_name')}, сохраняем только file_id")
                            final_mime_type = file_info.get('mime_type') or "application/octet-stream"
                            await FileQueries.create_file(
                                session=session,
                                task_id=task_id,
                                file_type=FileType.MESSAGE,
                                file_name=file_info['file_name'],
                                file_data=None,
                                file_size=file_size_from_info,
                                uploaded_by_id=buyer.id,
                                mime_type=final_mime_type,
                                telegram_file_id=file_info['file_id']
                            )
                            saved_count += 1
                except Exception as e:
                    # В случае ошибки сохраняем только file_id
                    logger.error(f"Ошибка при сохранении файла {file_info.get('file_name')}: {e}, сохраняем только file_id")
                    try:
                        final_mime_type = file_info.get('mime_type') or "application/octet-stream"
                        await FileQueries.create_file(
                            session=session,
                            task_id=task_id,
                            file_type=FileType.MESSAGE,
                            file_name=file_info['file_name'],
                            file_data=None,
                            file_size=file_size_from_info,
                            uploaded_by_id=buyer.id,
                            mime_type=final_mime_type,
                            telegram_file_id=file_info['file_id']
                        )
                        saved_count += 1
                    except Exception as e2:
                        logger.error(f"Критическая ошибка при сохранении file_id: {e2}")
        
        # Отправляем файлы исполнителю
        if task.executor:
            try:
                from aiogram.types import InputMediaPhoto, InputMediaDocument, InputMediaVideo
                
                text_message = f"""
📎 <b>НОВЫЕ ФАЙЛЫ ПО ЗАДАЧЕ</b>
━━━━━━━━━━━━━━━━━━━━━━━━━━

📋 <b>Задача:</b> {task.task_number}
👤 <b>От байера:</b> {buyer.first_name} {buyer.last_name or ''}

━━━━━━━━━━━━━━━━━━━━━━━━━━

Байер загрузил {saved_count} файл(ов) к задаче.
"""
                
                # Отправляем файлы как media group
                if files:
                    media_group = []
                    for idx, file_info in enumerate(files):
                        is_photo = file_info.get('is_photo', False)
                        is_video = file_info.get('is_video', False)
                        caption = text_message if idx == 0 else None
                        
                        if is_photo:
                            media_group.append(InputMediaPhoto(
                                media=file_info['file_id'],
                                caption=caption,
                                parse_mode="HTML" if caption else None
                            ))
                        elif is_video:
                            media_group.append(InputMediaVideo(
                                media=file_info['file_id'],
                                caption=caption,
                                parse_mode="HTML" if caption else None
                            ))
                        else:
                            media_group.append(InputMediaDocument(
                                media=file_info['file_id'],
                                caption=caption,
                                parse_mode="HTML" if caption else None
                            ))
                    
                    await bot.send_media_group(task.executor.telegram_id, media=media_group)
                    logger.info(f"Отправлены файлы от байера исполнителю по задаче {task.task_number}")
            except Exception as e:
                logger.error(f"Ошибка отправки файлов исполнителю: {e}")
        
        await callback.message.edit_text(
            f"✅ <b>ФАЙЛЫ ЗАГРУЖЕНЫ</b>\n\n"
            f"Загружено файлов: {saved_count}\n"
            f"Файлы отправлены исполнителю.",
            parse_mode="HTML"
        )
        
        await state.clear()
        logger.info(f"Байер {buyer.telegram_id} загрузил {saved_count} файлов к задаче {task.task_number}")
    
    await callback.answer(f"✅ Загружено файлов: {saved_count}")



