"""Обработка фотографий с конвертацией в base64"""
import base64
import io
from typing import Optional, Tuple
from aiogram import Bot
from aiogram.types import PhotoSize
from PIL import Image
from log import logger


class PhotoHandler:
    """Обработчик фотографий с конвертацией в base64"""
    
    MAX_PHOTO_SIZE = 10 * 1024 * 1024  # 10 MB максимум для фото
    MAX_WIDTH = 1920  # Максимальная ширина для оптимизации
    MAX_HEIGHT = 1920  # Максимальная высота для оптимизации
    JPEG_QUALITY = 85  # Качество JPEG при сжатии
    
    @staticmethod
    async def download_and_encode_photo(bot: Bot, photo: PhotoSize) -> Optional[Tuple[str, int, str]]:
        """
        Скачать фото из Telegram и конвертировать в base64
        Возвращает: (base64_string, file_size, mime_type)
        """
        try:
            # Получаем файл из Telegram
            file = await bot.get_file(photo.file_id)
            file_bytes = await bot.download_file(file.file_path)
            
            # Читаем байты
            if hasattr(file_bytes, 'read'):
                photo_bytes = file_bytes.read()
            else:
                photo_bytes = file_bytes
            
            # Оптимизируем изображение если нужно
            optimized_bytes = PhotoHandler._optimize_image(photo_bytes)
            
            # Конвертируем в base64
            base64_string = base64.b64encode(optimized_bytes).decode('utf-8')
            file_size = len(optimized_bytes)
            
            logger.info(f"Фото конвертировано в base64: размер {file_size} байт")
            return base64_string, file_size, "image/jpeg"
            
        except Exception as e:
            logger.error(f"Ошибка при конвертации фото в base64: {e}")
            return None
    
    @staticmethod
    async def download_and_encode_photo_from_file(bot: Bot, file_id: str) -> Optional[Tuple[str, int, str]]:
        """
        Скачать файл-фото из Telegram и конвертировать в base64
        Возвращает: (base64_string, file_size, mime_type)
        """
        try:
            # Получаем файл из Telegram
            file = await bot.get_file(file_id)
            file_bytes = await bot.download_file(file.file_path)
            
            # Читаем байты
            if hasattr(file_bytes, 'read'):
                photo_bytes = file_bytes.read()
            else:
                photo_bytes = file_bytes
            
            # Определяем тип файла
            mime_type = "image/jpeg"
            if file.file_path:
                if file.file_path.endswith('.png'):
                    mime_type = "image/png"
                elif file.file_path.endswith('.gif'):
                    mime_type = "image/gif"
                elif file.file_path.endswith('.webp'):
                    mime_type = "image/webp"
            
            # Оптимизируем изображение
            optimized_bytes = PhotoHandler._optimize_image(photo_bytes)
            
            # Конвертируем в base64
            base64_string = base64.b64encode(optimized_bytes).decode('utf-8')
            file_size = len(optimized_bytes)
            
            logger.info(f"Файл-фото конвертирован в base64: размер {file_size} байт, тип {mime_type}")
            return base64_string, file_size, mime_type
            
        except Exception as e:
            logger.error(f"Ошибка при конвертации файла-фото в base64: {e}")
            return None
    
    @staticmethod
    def _optimize_image(photo_bytes: bytes) -> bytes:
        """
        Оптимизировать изображение (изменить размер если нужно, сжать)
        """
        try:
            # Открываем изображение
            image = Image.open(io.BytesIO(photo_bytes))
            
            # Конвертируем в RGB если нужно (для JPEG)
            if image.mode in ('RGBA', 'LA', 'P'):
                # Создаем белый фон для прозрачных изображений
                background = Image.new('RGB', image.size, (255, 255, 255))
                if image.mode == 'P':
                    image = image.convert('RGBA')
                background.paste(image, mask=image.split()[-1] if image.mode == 'RGBA' else None)
                image = background
            elif image.mode != 'RGB':
                image = image.convert('RGB')
            
            # Изменяем размер если изображение слишком большое
            if image.width > PhotoHandler.MAX_WIDTH or image.height > PhotoHandler.MAX_HEIGHT:
                image.thumbnail((PhotoHandler.MAX_WIDTH, PhotoHandler.MAX_HEIGHT), Image.Resampling.LANCZOS)
                logger.info(f"Изображение изменено до размера: {image.width}x{image.height}")
            
            # Сохраняем в буфер с оптимизацией
            output = io.BytesIO()
            image.save(output, format='JPEG', quality=PhotoHandler.JPEG_QUALITY, optimize=True)
            optimized_bytes = output.getvalue()
            
            # Проверяем, что оптимизация действительно уменьшила размер
            if len(optimized_bytes) < len(photo_bytes):
                logger.info(f"Изображение оптимизировано: {len(photo_bytes)} -> {len(optimized_bytes)} байт")
                return optimized_bytes
            else:
                return photo_bytes
                
        except Exception as e:
            logger.error(f"Ошибка при оптимизации изображения: {e}")
            # В случае ошибки возвращаем оригинальные байты
            return photo_bytes
    
    @staticmethod
    def decode_photo_base64(base64_string: str) -> Optional[bytes]:
        """
        Декодировать base64 строку в байты изображения
        """
        try:
            photo_bytes = base64.b64decode(base64_string)
            return photo_bytes
        except Exception as e:
            logger.error(f"Ошибка при декодировании base64: {e}")
            return None
    
    @staticmethod
    def is_photo_mime_type(mime_type: str) -> bool:
        """
        Проверить, является ли mime_type типом изображения
        """
        if not mime_type:
            return False
        return mime_type.startswith('image/')
    
    @staticmethod
    def get_photo_size_str(size_bytes: int) -> str:
        """Получить размер фото в читаемом формате"""
        for unit in ['B', 'KB', 'MB']:
            if size_bytes < 1024.0:
                return f"{size_bytes:.1f} {unit}"
            size_bytes /= 1024.0
        return f"{size_bytes:.1f} GB"

