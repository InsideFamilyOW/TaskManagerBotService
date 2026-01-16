"""Обработка файлов"""
import os
import aiofiles
import base64
from datetime import datetime
from aiogram import Bot
from aiogram.types import Message, Document, PhotoSize
from typing import Tuple, Optional
from log import logger


class FileHandler:
    """Обработчик файлов"""
    
    UPLOAD_DIR = "uploads"
    MAX_FILE_SIZE = 50 * 1024 * 1024  # 50 MB
    
    @staticmethod
    async def download_file(bot: Bot, file_id: str, task_number: str) -> Optional[Tuple[str, str, int]]:
        """
        Скачать файл из Telegram
        Возвращает: (путь к файлу, имя файла, размер файла)
        """
        try:
            file = await bot.get_file(file_id)
            file_path = file.file_path
            
            # Определяем расширение файла
            ext = os.path.splitext(file_path)[1] if file_path else ""
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            
            # Создаем директорию для задачи
            task_dir = os.path.join(FileHandler.UPLOAD_DIR, task_number)
            os.makedirs(task_dir, exist_ok=True)
            
            # Генерируем имя файла
            file_name = f"file_{timestamp}{ext}"
            local_path = os.path.join(task_dir, file_name)
            
            # Скачиваем файл
            await bot.download_file(file_path, local_path)
            
            # Получаем размер файла
            file_size = os.path.getsize(local_path)
            
            logger.info(f"Файл скачан: {file_name} ({file_size} bytes) для задачи {task_number}")
            return local_path, file_name, file_size
            
        except Exception as e:
            logger.error(f"Ошибка при скачивании файла: {e}")
            return None
    
    @staticmethod
    async def download_photo(bot: Bot, photo: PhotoSize, task_number: str) -> Optional[Tuple[str, str, int]]:
        """
        Скачать фото из Telegram
        Возвращает: (путь к файлу, имя файла, размер файла)
        """
        try:
            file = await bot.get_file(photo.file_id)
            file_path = file.file_path
            
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            
            # Создаем директорию для задачи
            task_dir = os.path.join(FileHandler.UPLOAD_DIR, task_number)
            os.makedirs(task_dir, exist_ok=True)
            
            # Генерируем имя файла
            file_name = f"photo_{timestamp}.jpg"
            local_path = os.path.join(task_dir, file_name)
            
            # Скачиваем файл
            await bot.download_file(file_path, local_path)
            
            # Получаем размер файла
            file_size = os.path.getsize(local_path)
            
            logger.info(f"Фото скачано: {file_name} ({file_size} bytes) для задачи {task_number}")
            return local_path, file_name, file_size
            
        except Exception as e:
            logger.error(f"Ошибка при скачивании фото: {e}")
            return None
    
    @staticmethod
    async def save_file_from_message(bot: Bot, message: Message, task_number: str) -> Optional[Tuple[str, str, int, str]]:
        """
        Сохранить файл из сообщения
        Возвращает: (путь к файлу, имя файла, размер файла, mime_type)
        """
        try:
            if message.document:
                doc = message.document
                result = await FileHandler.download_file(bot, doc.file_id, task_number)
                if result:
                    return (*result, doc.mime_type)
            
            elif message.photo:
                photo = message.photo[-1]  # Берем самое большое фото
                result = await FileHandler.download_photo(bot, photo, task_number)
                if result:
                    return (*result, "image/jpeg")
            
            return None
            
        except Exception as e:
            logger.error(f"Ошибка при сохранении файла из сообщения: {e}")
            return None
    
    @staticmethod
    def get_file_size_str(size_bytes: int) -> str:
        """Получить размер файла в читаемом формате"""
        for unit in ['B', 'KB', 'MB', 'GB']:
            if size_bytes < 1024.0:
                return f"{size_bytes:.1f} {unit}"
            size_bytes /= 1024.0
        return f"{size_bytes:.1f} TB"
    
    @staticmethod
    def is_file_size_valid(size_bytes: int) -> bool:
        """Проверить размер файла"""
        return size_bytes <= FileHandler.MAX_FILE_SIZE
    
    @staticmethod
    async def download_and_encode_file(bot: Bot, file_id: str) -> Optional[Tuple[str, int, str]]:
        """
        Скачать файл из Telegram и конвертировать в base64
        Возвращает: (base64_string, file_size, mime_type)
        """
        try:
            # Получаем файл из Telegram
            file = await bot.get_file(file_id)
            file_bytes = await bot.download_file(file.file_path)
            
            # Читаем байты
            if hasattr(file_bytes, 'read'):
                file_data = file_bytes.read()
            else:
                file_data = file_bytes
            
            # Конвертируем в base64
            base64_string = base64.b64encode(file_data).decode('utf-8')
            file_size = len(file_data)
            
            # Определяем mime_type по расширению
            mime_type = "application/octet-stream"
            if file.file_path:
                ext = os.path.splitext(file.file_path)[1].lower()
                mime_types = {
                    '.pdf': 'application/pdf',
                    '.doc': 'application/msword',
                    '.docx': 'application/vnd.openxmlformats-officedocument.wordprocessingml.document',
                    '.xls': 'application/vnd.ms-excel',
                    '.xlsx': 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
                    '.ppt': 'application/vnd.ms-powerpoint',
                    '.pptx': 'application/vnd.openxmlformats-officedocument.presentationml.presentation',
                    '.txt': 'text/plain',
                    '.zip': 'application/zip',
                    '.rar': 'application/x-rar-compressed',
                    '.7z': 'application/x-7z-compressed',
                    '.png': 'image/png',
                    '.jpg': 'image/jpeg',
                    '.jpeg': 'image/jpeg',
                    '.gif': 'image/gif',
                    '.webp': 'image/webp',
                    '.mp4': 'video/mp4',
                    '.avi': 'video/x-msvideo',
                    '.mov': 'video/quicktime',
                    '.wmv': 'video/x-ms-wmv',
                    '.flv': 'video/x-flv',
                    '.webm': 'video/webm',
                    '.mkv': 'video/x-matroska',
                    '.mp3': 'audio/mpeg',
                }
                mime_type = mime_types.get(ext, mime_type)
            
            logger.info(f"Файл конвертирован в base64: размер {file_size} байт, mime: {mime_type}")
            return base64_string, file_size, mime_type
            
        except Exception as e:
            logger.error(f"Ошибка при конвертации файла в base64: {e}")
            return None
    
    @staticmethod
    def decode_file_base64(base64_string: str) -> Optional[bytes]:
        """
        Декодировать base64 строку в байты файла
        """
        try:
            file_bytes = base64.b64decode(base64_string)
            return file_bytes
        except Exception as e:
            logger.error(f"Ошибка при декодировании base64: {e}")
            return None

