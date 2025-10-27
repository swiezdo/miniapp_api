#!/bin/bash
# Скрипт для запуска Tsushima Mini App API

cd /root/miniapp_api

# Активируем виртуальное окружение
source venv/bin/activate

# Запускаем сервер
echo "🚀 Запуск Tsushima Mini App API..."
echo "📁 Рабочая директория: $(pwd)"
echo "🐍 Python: $(which python)"
echo "📦 Виртуальное окружение: $(which pip)"

python app.py
