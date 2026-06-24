# 🎵 MusicFlow

Минималистичная аудиоплатформа на Flask — загружай, слушай и делись музыкой.

![Python](https://img.shields.io/badge/Python-3.11-blue)
![Flask](https://img.shields.io/badge/Flask-3.1-green)
![License](https://img.shields.io/badge/License-MIT-yellow)

---

## Возможности

- 🎵 **Загрузка треков** — MP3, WAV, OGG до 50 МБ
- ▶️ **Встроенный плеер** — слушай прямо в браузере
- 🌐 **Discovery** — поиск по базе Discogs (миллионы треков)
- 👤 **Аккаунты** — регистрация, вход, профиль
- 🔐 **Безопасность** — CSRF-защита, brute-force блокировка, bcrypt пароли
- 📊 **Статистика** — прослушивания, топ треков
- 📱 **Адаптивный дизайн** — работает на мобиле

---

## Быстрый старт (локально)

### Требования
- Python 3.11+
- pip

### Установка

```bash
# Клонируй репозиторий
git clone https://github.com/YOUR_USERNAME/musicflow.git
cd musicflow

# Создай виртуальное окружение
python -m venv venv

# Активируй (Windows)
venv\Scripts\activate

# Активируй (Mac/Linux)
source venv/bin/activate

# Установи зависимости
pip install -r requirements.txt
```

### Настройка окружения

Скопируй `.env` и заполни:

```bash
# Сгенерируй SECRET_KEY
python -c "import secrets; print(secrets.token_hex(32))"
```

Файл `.env`:
```env
SECRET_KEY=твой-случайный-ключ-минимум-32-символа
FLASK_DEBUG=0
DISCOGS_TOKEN=твой-токен-discogs
```

Получить токен Discogs: [discogs.com/settings/developers](https://www.discogs.com/settings/developers)

### Запуск

```bash
python app.py
```

Открой: **http://localhost:5000**

#### Тестовый аккаунт
| Логин | Пароль |
|-------|--------|
| demo  | Demo@1234 |

---

## Деплой на Render.com (бесплатно)

### 1. Залей код на GitHub

```bash
git init
git add .
git commit -m "Initial commit"
git remote add origin https://github.com/YOUR_USERNAME/musicflow.git
git push -u origin main
```

### 2. Создай сервис на Render

1. Зайди на [render.com](https://render.com) → **New → Web Service**
2. Подключи GitHub репозиторий
3. Настройки автоматически возьмутся из `render.yaml`
4. Нажми **Deploy**

### 3. Переменные окружения на Render

В разделе **Environment** добавь:
| Переменная | Значение |
|-----------|---------|
| `SECRET_KEY` | (сгенерируй случайный) |
| `DISCOGS_TOKEN` | твой токен |
| `FLASK_DEBUG` | `0` |

> ⚠️ **Важно:** На бесплатном Render файлы треков сохраняются на persistent disk (1 GB включено).

---

## Структура проекта

```
musicflow/
├── app.py                  # Основное приложение Flask
├── requirements.txt        # Зависимости Python
├── Procfile               # Конфиг для Render/Heroku
├── render.yaml            # Конфиг деплоя Render
├── .env                   # Переменные окружения (НЕ в git!)
├── .env.example           # Пример .env
├── .gitignore             # Игнор-файлы
├── instance/
│   └── music.db           # SQLite база данных
├── static/
│   └── music/             # Загруженные аудиофайлы
└── templates/
    ├── base.html          # Базовый шаблон (navbar, flash)
    ├── index.html         # Главная страница
    ├── music.html         # Страница треков + плеер
    ├── upload.html        # Загрузка трека
    ├── login.html         # Вход
    ├── register.html      # Регистрация
    └── profile.html       # Профиль пользователя
```

---

## API Endpoints

Все API-маршруты возвращают JSON.

### Треки

| Метод | URL | Описание |
|-------|-----|---------|
| GET | `/api/songs` | Список треков (с фильтрами) |
| GET | `/api/songs/<id>` | Один трек |
| GET | `/api/songs/top?limit=10` | Топ по прослушиваниям |
| GET | `/api/songs/new?limit=10` | Последние загруженные |
| GET | `/api/genres` | Список жанров с количеством |
| GET | `/api/stats` | Общая статистика |

#### Параметры `/api/songs`

| Параметр | Тип | Описание |
|---------|-----|---------|
| `search` | string | Поиск по названию/исполнителю |
| `genre` | string | Фильтр по жанру |
| `sort` | string | `date`, `plays`, `title`, `artist` |
| `order` | string | `asc`, `desc` |
| `limit` | int | Количество результатов |
| `offset` | int | Смещение (пагинация) |

#### Пример ответа `/api/songs`

```json
{
  "success": true,
  "total": 42,
  "count": 10,
  "songs": [
    {
      "id": 1,
      "title": "Summer Vibes",
      "artist": "DJ Sunshine",
      "genre": "Electronic",
      "duration": "3:45",
      "plays": 1245,
      "stream_url": "/play/1",
      "upload_date": "2026-06-21T05:00:00"
    }
  ]
}
```

### Discovery (Discogs)

| Метод | URL | Описание |
|-------|-----|---------|
| GET | `/api/deezer/charts?genre=0&limit=30` | Чарты по жанру |
| GET | `/api/deezer/search?q=query&limit=20` | Поиск |
| GET | `/api/deezer/genres` | Список жанров |

### Стриминг

| Метод | URL | Описание |
|-------|-----|---------|
| GET | `/play/<id>` | Стрим аудиофайла (увеличивает счётчик) |

---

## Безопасность

| Механизм | Описание |
|---------|---------|
| CSRF-защита | Flask-WTF на всех формах |
| Brute-force | 5 попыток → блок 15 минут по IP |
| Пароли | Werkzeug scrypt (bcrypt-совместимый) |
| Загрузки | Whitelist форматов + UUID имена + 50 МБ лимит |
| Заголовки | X-Frame-Options, X-Content-Type-Options, Referrer-Policy |
| Редиректы | Проверка `?next=` на локальность |

---

## Требования к паролю

- Минимум 8 символов
- Хотя бы одна буква
- Хотя бы одна цифра или спецсимвол

---

## Технологии

| Компонент | Технология |
|---------|-----------|
| Backend | Python 3.11, Flask 3.1 |
| База данных | SQLite + SQLAlchemy 2.0 |
| Аутентификация | Flask-Login |
| Безопасность форм | Flask-WTF (CSRF) |
| Фронтенд | Vanilla HTML/CSS/JS |
| Шрифты | Inter (Google Fonts) |
| Иконки | Font Awesome 6 |
| API данные | Discogs API |
| WSGI (продакшн) | Gunicorn |

---

## Лицензия

MIT License — используй свободно.

---

## Автор

Создано с Flask + ❤️
