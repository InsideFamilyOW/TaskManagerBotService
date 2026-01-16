"""Запросы для работы с файлами"""
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from typing import List, Optional

from db.models import TaskFile, FileType
from log import logger


class FileQueries:
    """Запросы для работы с файлами"""
    
    @staticmethod
    async def create_file(
        session: AsyncSession,
        task_id: int,
        file_type: FileType,
        file_name: str,
        file_data: str = None,
        file_size: int = 0,
        uploaded_by_id: int = None,
        mime_type: str = None,
        telegram_file_id: str = None
    ) -> TaskFile:
        """
        Создать запись о файле в base64 или с telegram_file_id для больших файлов
        
        Если передан telegram_file_id, файл не скачивается, сохраняется только file_id.
        Если передан file_data, файл сохраняется в base64.
        """
        file = TaskFile(
            task_id=task_id,
            file_type=file_type,
            file_name=file_name,
            file_path=f"telegram_file_id:{telegram_file_id}" if telegram_file_id else None,
            file_size=file_size,
            uploaded_by_id=uploaded_by_id,
            mime_type=mime_type,
            file_data=file_data  # Файл хранится в base64, или None если используем file_id
        )
        session.add(file)
        await session.commit()
        await session.refresh(file)
        
        if telegram_file_id:
            logger.info(f"Добавлен файл в БД {file_name} к задаче {task_id} с file_id (размер: {file_size} байт)")
        else:
            logger.info(f"Добавлен файл в БД {file_name} к задаче {task_id}, размер: {file_size} байт")
        return file
    
    @staticmethod
    def get_telegram_file_id(file_record: TaskFile) -> Optional[str]:
        """Получить telegram_file_id из записи файла, если он сохранен"""
        if file_record.file_path and file_record.file_path.startswith("telegram_file_id:"):
            return file_record.file_path.replace("telegram_file_id:", "")
        return None
    
    @staticmethod
    async def create_photo_base64(
        session: AsyncSession,
        task_id: int,
        file_type: FileType,
        file_name: str,
        photo_base64: str,
        file_size: int,
        uploaded_by_id: int,
        mime_type: str = "image/jpeg"
    ) -> TaskFile:
        """Создать запись о фотографии в base64 (устаревший метод, использует file_data)"""
        file = TaskFile(
            task_id=task_id,
            file_type=file_type,
            file_name=file_name,
            file_path=None,
            file_size=file_size,
            uploaded_by_id=uploaded_by_id,
            mime_type=mime_type,
            file_data=photo_base64  # Используем новое поле
        )
        session.add(file)
        await session.commit()
        await session.refresh(file)
        
        logger.info(f"Добавлена фотография в БД {file_name} к задаче {task_id}, размер: {file_size} байт")
        return file
    
    @staticmethod
    async def get_task_files(
        session: AsyncSession,
        task_id: int,
        file_type: FileType = None
    ) -> List[TaskFile]:
        """Получить файлы задачи"""
        query = select(TaskFile).where(
            TaskFile.task_id == task_id,
            TaskFile.is_deleted == False
        )
        if file_type:
            query = query.where(TaskFile.file_type == file_type)
        
        result = await session.execute(query.order_by(TaskFile.created_at))
        return result.scalars().all()
    
    @staticmethod
    async def get_file_by_id(
        session: AsyncSession,
        file_id: int
    ) -> Optional[TaskFile]:
        """Получить файл по ID"""
        result = await session.execute(
            select(TaskFile).where(TaskFile.id == file_id)
        )
        return result.scalar_one_or_none()
    
    @staticmethod
    async def delete_file(
        session: AsyncSession,
        file_id: int
    ):
        """Удалить файл (soft delete)"""
        file = await FileQueries.get_file_by_id(session, file_id)
        if file:
            file.is_deleted = True
            await session.commit()
            logger.info(f"Файл {file.file_name} (ID: {file_id}) помечен как удаленный")
    
    @staticmethod
    async def get_initial_files(
        session: AsyncSession,
        task_id: int
    ) -> List[TaskFile]:
        """Получить начальные файлы задачи"""
        return await FileQueries.get_task_files(session, task_id, FileType.INITIAL)
    
    @staticmethod
    async def get_result_files(
        session: AsyncSession,
        task_id: int
    ) -> List[TaskFile]:
        """Получить файлы результата"""
        return await FileQueries.get_task_files(session, task_id, FileType.RESULT)
    
    @staticmethod
    async def get_total_files_size(
        session: AsyncSession,
        task_id: int
    ) -> int:
        """Получить общий размер файлов задачи"""
        from sqlalchemy import func
        
        result = await session.execute(
            select(func.sum(TaskFile.file_size)).where(
                TaskFile.task_id == task_id,
                TaskFile.is_deleted == False
            )
        )
        total_size = result.scalar()
        return total_size if total_size else 0

