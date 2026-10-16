# MusicFlow

Минималистичная аудиоплатформа на Flask — загружай, слушай и делись музыкой.

## Возможности

- Загрузка треков (MP3, WAV, OGG до 50 МБ)
- Встроенный плеер
- Discovery через Discogs API
- Регистрация / вход / профиль
- CSRF, rate-limit по IP, security headers
- REST API + статистика
- Адаптивный тёмный UI

## Быстрый старт

```bash
# 1. Распакуй архив и перейди в папку
cd musicflow

# 2. Виртуальное окружение
python -m venv venv

# Windows:
venv\Scripts\activate

# Mac/Linux:
source venv/bin/activate

# 3. Зависимости
pip install -r requirements.txt

# 4. Окружение
cp .env.example .env
# Открой .env и поставь SECRET_KEY:
#   python -c "import secrets; print(secrets.token_hex(32))"
# Опционально: DISCOGS_TOKEN с https://www.discogs.com/settings/developers

# 5. Запуск
python app.py
```

Открой: **http://127.0.0.1:5000**

### Демо-аккаунт

| Логин | Пароль    |
|-------|-----------|
| demo  | Demo@1234 |

## Структура

```
musicflow/
├── app.py              # Маршруты и API
├── models.py           # Users, Song + relationship
├── forms.py            # WTForms
├── requirements.txt
├── Procfile            # для Render / Heroku
├── .env.example
├── .gitignore
├── README.md
├── instance/           # SQLite (создаётся сама)
├── static/
│   ├── css/
│   └── music/          # загруженные файлы
└── templates/
    ├── base.html
    ├── index.html
    ├── music.html
    ├── login.html
    ├── register.html
    ├── profile.html
    └── upload.html
```

## API

| URL | Описание |
|-----|----------|
| GET /api/songs | Список (?search=&genre=&sort=&order=&limit=&offset=) |
| GET /api/songs/top | Топ по plays |
| GET /api/songs/new | Новые |
| GET /api/stats | Статистика |
| GET /api/genres | Жанры |
| GET /api/discogs/charts | Чарты Discogs |
| GET /api/discogs/search?q= | Поиск Discogs |
| GET /play/<id> | Стрим файла |

Старые пути /api/deezer/* тоже работают.
## Лицензия

MIT
