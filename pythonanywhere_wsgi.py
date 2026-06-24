# =========================================================
# WSGI-файл для PythonAnywhere
# Скопируй это содержимое в WSGI Configuration File
# (ссылка в панели Web → WSGI configuration file)
# =========================================================

import sys
import os

# ── Укажи своё имя пользователя PythonAnywhere ──
# ИЗМЕНИ 'твой_ник' на реальный ник!
USERNAME = 'твой_ник'
PROJECT_DIR = f'/home/{USERNAME}/musicflow'

# Добавляем проект в sys.path
if PROJECT_DIR not in sys.path:
    sys.path.insert(0, PROJECT_DIR)

# Загружаем переменные окружения из .env
from dotenv import load_dotenv
load_dotenv(os.path.join(PROJECT_DIR, '.env'))

# Запускаем Flask приложение
from app import app as application  # noqa
