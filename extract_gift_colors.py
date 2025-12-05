#!/usr/bin/env python3
"""
Скрипт для извлечения доминантных цветов из иконки подарка.
Использование: python extract_gift_colors.py <путь_к_изображению>

Выводит цвета в формате для gifts.json
"""

import sys
from pathlib import Path
from collections import Counter
from PIL import Image


def extract_dominant_colors(image_path: str, num_colors: int = 2) -> list:
    """
    Извлекает доминантные цвета из изображения.
    
    Args:
        image_path: Путь к изображению
        num_colors: Количество цветов для извлечения
    
    Returns:
        Список HEX цветов
    """
    img = Image.open(image_path)
    
    # Конвертируем в RGBA если нужно
    if img.mode != 'RGBA':
        img = img.convert('RGBA')
    
    # Уменьшаем размер для скорости
    img = img.resize((100, 100), Image.Resampling.LANCZOS)
    
    # Собираем все непрозрачные пиксели
    pixels = []
    for x in range(img.width):
        for y in range(img.height):
            r, g, b, a = img.getpixel((x, y))
            # Игнорируем прозрачные и почти белые/чёрные пиксели
            if a > 128:
                brightness = (r + g + b) / 3
                if 30 < brightness < 240:
                    # Квантизация для группировки похожих цветов
                    r = (r // 32) * 32
                    g = (g // 32) * 32
                    b = (b // 32) * 32
                    pixels.append((r, g, b))
    
    if not pixels:
        return ['#ff6b6b', '#ffbe76']  # Дефолтные цвета
    
    # Находим самые частые цвета
    color_counts = Counter(pixels)
    most_common = color_counts.most_common(num_colors * 3)
    
    # Выбираем разные цвета (не слишком похожие)
    result = []
    for color, _ in most_common:
        if len(result) >= num_colors:
            break
        
        # Проверяем что цвет достаточно отличается от уже выбранных
        is_different = True
        for existing in result:
            diff = sum(abs(a - b) for a, b in zip(color, existing))
            if diff < 60:  # Минимальная разница
                is_different = False
                break
        
        if is_different:
            result.append(color)
    
    # Если не нашли достаточно разных цветов
    while len(result) < num_colors:
        result.append(result[-1] if result else (255, 107, 107))
    
    # Конвертируем в HEX
    hex_colors = []
    for r, g, b in result:
        # Делаем цвета ярче
        r = min(255, r + 30)
        g = min(255, g + 30)
        b = min(255, b + 30)
        hex_colors.append(f'#{r:02x}{g:02x}{b:02x}')
    
    return hex_colors


def main():
    if len(sys.argv) < 2:
        print("Использование: python extract_gift_colors.py <путь_к_изображению>")
        print("Или: python extract_gift_colors.py --all <папка_с_иконками>")
        sys.exit(1)
    
    if sys.argv[1] == '--all':
        # Обработка всех файлов в папке
        folder = Path(sys.argv[2]) if len(sys.argv) > 2 else Path('/root/tsushimaru_app/docs/assets/icons/gifts')
        
        print("Цвета для gifts.json:\n")
        for img_path in sorted(folder.glob('*.webp')):
            key = img_path.stem
            colors = extract_dominant_colors(str(img_path))
            print(f'  "{key}": ["{colors[0]}", "{colors[1]}"],')
    else:
        # Обработка одного файла
        image_path = sys.argv[1]
        
        if not Path(image_path).exists():
            print(f"Файл не найден: {image_path}")
            sys.exit(1)
        
        colors = extract_dominant_colors(image_path)
        key = Path(image_path).stem
        
        print(f"\nЦвета для {key}:")
        print(f"  Основной: {colors[0]}")
        print(f"  Вторичный: {colors[1]}")
        print(f"\nДля gifts.json:")
        print(f'  "colors": ["{colors[0]}", "{colors[1]}"]')


if __name__ == "__main__":
    main()


