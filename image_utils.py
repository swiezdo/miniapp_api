# image_utils.py
# Утилиты для обработки изображений

import os
import shutil
import tempfile
from contextlib import contextmanager
from PIL import Image, ImageOps
from fastapi import UploadFile
from typing import Optional


def process_image_for_upload(image: Image.Image, output_path: str, quality: int = 85) -> None:
    """
    Универсальная обработка изображений для загрузки.
    
    Выполняет:
    - Исправление ориентации согласно EXIF-метаданным
    - Конвертацию RGBA/LA/P -> RGB
    - Сохранение как JPEG
    
    Args:
        image: PIL Image объект
        output_path: Путь для сохранения обработанного изображения
        quality: Качество JPEG (по умолчанию 85)
    """
    # Исправляем ориентацию согласно EXIF-метаданным
    image = ImageOps.exif_transpose(image)
    
    # Конвертируем в RGB если нужно (PNG с альфа-каналом)
    if image.mode in ('RGBA', 'LA', 'P'):
        background = Image.new('RGB', image.size, (255, 255, 255))
        if image.mode == 'P':
            image = image.convert('RGBA')
        background.paste(image, mask=image.split()[-1] if image.mode == 'RGBA' else None)
        image = background
    
    # Сохраняем как JPEG
    image.save(output_path, 'JPEG', quality=quality, optimize=True)


def process_avatar_image(image: Image.Image, output_path: str, size: int = 300) -> None:
    """
    Обработка аватарки с квадратной обрезкой.
    
    Выполняет:
    - Исправление ориентации согласно EXIF-метаданным
    - Квадратную обрезку по центру
    - Ресайз до указанного размера
    - Конвертацию в RGB если нужно
    - Сохранение как JPEG
    
    Args:
        image: PIL Image объект
        output_path: Путь для сохранения обработанной аватарки
        size: Размер квадрата в пикселях (по умолчанию 300)
    """
    # Исправляем ориентацию согласно EXIF-метаданным
    image = ImageOps.exif_transpose(image)
    
    # Квадратная обрезка по центру
    width, height = image.size
    min_dimension = min(width, height)
    left = (width - min_dimension) // 2
    top = (height - min_dimension) // 2
    right = left + min_dimension
    bottom = top + min_dimension
    image = image.crop((left, top, right, bottom))
    
    # Ресайз до указанного размера
    image = image.resize((size, size), Image.Resampling.LANCZOS)
    
    # Конвертируем в RGB если нужно
    if image.mode in ('RGBA', 'LA', 'P'):
        background = Image.new('RGB', image.size, (255, 255, 255))
        if image.mode == 'P':
            image = image.convert('RGBA')
        background.paste(image, mask=image.split()[-1] if image.mode == 'RGBA' else None)
        image = background
    
    # Сохраняем как JPEG
    image.save(output_path, 'JPEG', quality=85, optimize=True)


def validate_image_file(file: UploadFile) -> bool:
    """
    Валидирует тип файла изображения.
    
    Args:
        file: UploadFile объект
    
    Returns:
        True если файл является изображением, False иначе
    """
    if not file.content_type:
        return False
    return file.content_type.startswith('image/')


@contextmanager
def temp_image_directory(prefix: str = 'temp_images_'):
    """
    Context manager для временной директории с изображениями.
    
    Автоматически создает временную директорию и удаляет её после использования.
    
    Args:
        prefix: Префикс для имени временной директории
    
    Yields:
        Путь к временной директории
    """
    temp_dir = None
    try:
        temp_dir = tempfile.mkdtemp(prefix=prefix)
        yield temp_dir
    finally:
        if temp_dir and os.path.exists(temp_dir):
            try:
                shutil.rmtree(temp_dir)
            except Exception as e:
                print(f"Ошибка удаления временной директории: {e}")

