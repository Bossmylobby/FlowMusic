from flask import (
    Flask, render_template, request, redirect, url_for,
    flash, send_from_directory, jsonify, abort
)
from flask_sqlalchemy import SQLAlchemy
from flask_login import (
    LoginManager, UserMixin, login_user, logout_user,
    login_required, current_user
)
from flask_wtf.csrf import CSRFProtect, CSRFError
from werkzeug.security import generate_password_hash, check_password_hash
from werkzeug.utils import secure_filename
from dotenv import load_dotenv
import os
import re
import uuid
from datetime import datetime, timedelta, timezone
from collections import defaultdict
from functools import wraps
import requests

# ──────────────────────────────────────────────────────────────
#  ЗАГРУЗКА ПЕРЕМЕННЫХ ОКРУЖЕНИЯ ИЗ .env
# ──────────────────────────────────────────────────────────────

load_dotenv()  # Читает .env файл если он есть

# ──────────────────────────────────────────────────────────────
#  КОНФИГУРАЦИЯ ПРИЛОЖЕНИЯ
# ──────────────────────────────────────────────────────────────

app = Flask(__name__)

# БЕЗОПАСНОСТЬ: SECRET_KEY берётся из переменной окружения.
# Если не задан — генерируется случайный (сессии сбрасываются при перезапуске).
# В продакшне ОБЯЗАТЕЛЬНО установи SECRET_KEY в .env
_secret = os.environ.get('SECRET_KEY')
if not _secret or _secret == 'замени-на-случайную-строку-минимум-32-символа':
    import secrets
    _secret = secrets.token_hex(32)
    print("[!] SECRET_KEY ne zadan v .env — ispolzuetsya vremennyy klyuch. "
          "Sessii budut sbrosheny pri perezapuske!")

app.config['SECRET_KEY'] = _secret
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///music.db'
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
app.config['UPLOAD_FOLDER'] = 'static/music'
app.config['ALLOWED_EXTENSIONS'] = {'mp3', 'wav', 'ogg'}
app.config['MAX_CONTENT_LENGTH'] = 50 * 1024 * 1024  # 50 МБ максимум на файл
app.config['WTF_CSRF_TIME_LIMIT'] = 3600  # CSRF-токен действует 1 час

# БЕЗОПАСНОСТЬ: токен Discogs из переменной окружения
DISCOGS_TOKEN = os.environ.get('DISCOGS_TOKEN', '')
DISCOGS = 'https://api.discogs.com'
DISCOGS_TIMEOUT = 8

db = SQLAlchemy(app)
csrf = CSRFProtect(app)  # CSRF-защита на все POST-формы
login_manager = LoginManager(app)
login_manager.login_view = 'login'
login_manager.login_message = 'Пожалуйста, войдите в систему.'
login_manager.login_message_category = 'info'

os.makedirs(app.config['UPLOAD_FOLDER'], exist_ok=True)


# ──────────────────────────────────────────────────────────────
#  ЗАЩИТА ОТ БРУТФОРСА
#  Простой in-memory счётчик попыток входа по IP.
#  После 5 неудачных попыток — блокировка на 15 минут.
# ──────────────────────────────────────────────────────────────

login_attempts: dict[str, list] = defaultdict(list)
MAX_ATTEMPTS = 5
BLOCK_MINUTES = 15


def get_client_ip() -> str:
    """Получить IP клиента (с учётом прокси)."""
    return request.headers.get('X-Forwarded-For', request.remote_addr or 'unknown').split(',')[0].strip()


def is_ip_blocked(ip: str) -> bool:
    """Проверить, заблокирован ли IP из-за множества неудачных попыток."""
    now = datetime.now(timezone.utc)
    cutoff = now - timedelta(minutes=BLOCK_MINUTES)
    # Оставляем только свежие попытки в окне блокировки
    login_attempts[ip] = [t for t in login_attempts[ip] if t > cutoff]
    return len(login_attempts[ip]) >= MAX_ATTEMPTS


def record_failed_attempt(ip: str) -> None:
    """Записать неудачную попытку входа."""
    login_attempts[ip].append(datetime.now(timezone.utc))


def clear_attempts(ip: str) -> None:
    """Сбросить счётчик после успешного входа."""
    login_attempts.pop(ip, None)


# ──────────────────────────────────────────────────────────────
#  SECURITY HEADERS
#  Добавляются ко всем ответам сервера.
# ──────────────────────────────────────────────────────────────

@app.after_request
def set_security_headers(response):
    # Запрет встраивания в iframe (защита от clickjacking)
    response.headers['X-Frame-Options'] = 'SAMEORIGIN'
    # Запрет MIME-sniffing (браузер не «угадывает» тип файла)
    response.headers['X-Content-Type-Options'] = 'nosniff'
    # Реферер отправляется только на тот же домен
    response.headers['Referrer-Policy'] = 'strict-origin-when-cross-origin'
    # Запрет XSS через старый IE-механизм
    response.headers['X-XSS-Protection'] = '1; mode=block'
    # Разрешить доступ к микрофону/камере только с явного разрешения
    response.headers['Permissions-Policy'] = 'geolocation=(), microphone=(), camera=()'
    return response


# ──────────────────────────────────────────────────────────────
#  ОБРАБОТКА CSRF-ОШИБОК
# ──────────────────────────────────────────────────────────────

@app.errorhandler(CSRFError)
def handle_csrf_error(e):
    flash('Форма устарела или запрос недействителен. Пожалуйста, попробуйте снова.', 'error')
    return redirect(request.referrer or url_for('home'))


# ──────────────────────────────────────────────────────────────
#  МОДЕЛИ БАЗЫ ДАННЫХ
# ──────────────────────────────────────────────────────────────

class Users(UserMixin, db.Model):
    __tablename__ = 'users'

    id            = db.Column(db.Integer, primary_key=True)
    username      = db.Column(db.String(80), unique=True, nullable=False)
    email         = db.Column(db.String(120), unique=True, nullable=False)
    # БЕЗОПАСНОСТЬ: длина 256 — bcrypt/scrypt хэши длиннее 120 символов
    password_hash = db.Column(db.String(256))
    created_at    = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc))

    def set_password(self, password: str) -> None:
        self.password_hash = generate_password_hash(password)

    def check_password(self, password: str) -> bool:
        if not self.password_hash:
            return False
        return check_password_hash(self.password_hash, password)


class Song(db.Model):
    id          = db.Column(db.Integer, primary_key=True)
    title       = db.Column(db.String(100), nullable=False)
    artist      = db.Column(db.String(100), nullable=False)
    genre       = db.Column(db.String(50), nullable=False)
    duration    = db.Column(db.String(10))
    filename    = db.Column(db.String(200))
    plays       = db.Column(db.Integer, default=0)
    upload_date = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc))
    user_id     = db.Column(db.Integer, db.ForeignKey('users.id'))


@login_manager.user_loader
def load_user(user_id):
    return db.session.get(Users, int(user_id))


# ──────────────────────────────────────────────────────────────
#  ВСПОМОГАТЕЛЬНЫЕ ФУНКЦИИ ВАЛИДАЦИИ
# ──────────────────────────────────────────────────────────────

def allowed_file(filename: str) -> bool:
    """Проверяет расширение файла по белому списку."""
    return '.' in filename and \
           filename.rsplit('.', 1)[1].lower() in app.config['ALLOWED_EXTENSIONS']


def validate_password(password: str) -> str | None:
    """
    Проверяет надёжность пароля.
    Возвращает строку с ошибкой или None если пароль корректен.
    """
    if len(password) < 8:
        return 'Пароль должен содержать минимум 8 символов'
    if not re.search(r'[A-Za-z]', password):
        return 'Пароль должен содержать хотя бы одну букву'
    if not re.search(r'[\d\W_]', password):
        return 'Пароль должен содержать хотя бы одну цифру или спецсимвол'
    return None


def sanitize_text(value: str, max_len: int = 100) -> str:
    """Обрезает и очищает текстовое поле от лишних пробелов."""
    return value.strip()[:max_len]


def safe_redirect_url() -> str:
    """
    БЕЗОПАСНОСТЬ: проверяет параметр ?next= чтобы не допустить
    open redirect (перенаправление на внешний сайт).
    """
    next_url = request.args.get('next') or request.form.get('next', '')
    # Разрешаем только относительные пути (начинаются с /, без //)
    if next_url and next_url.startswith('/') and not next_url.startswith('//'):
        return next_url
    return url_for('home')


# ──────────────────────────────────────────────────────────────
#  ОСНОВНЫЕ МАРШРУТЫ
# ──────────────────────────────────────────────────────────────

@app.route('/')
def home():
    popular_songs = Song.query.order_by(Song.plays.desc()).limit(6).all()
    recent_songs  = Song.query.order_by(Song.upload_date.desc()).limit(6).all()
    return render_template('index.html',
                           popular_songs=popular_songs,
                           recent_songs=recent_songs,
                           total_songs=Song.query.count(),
                           total_users=Users.query.count())


@app.route('/music')
def show_music():
    songs = Song.query.all()
    return render_template('music.html', songs=songs)


@app.route('/upload', methods=['GET', 'POST'])
@login_required
def upload():
    if request.method == 'POST':
        # Валидация полей формы
        title    = sanitize_text(request.form.get('title', ''))
        artist   = sanitize_text(request.form.get('artist', ''))
        genre    = sanitize_text(request.form.get('genre', ''))
        duration = sanitize_text(request.form.get('duration', ''), max_len=10)

        if not title or not artist or not genre:
            flash('Название, исполнитель и жанр обязательны', 'error')
            return redirect(request.url)

        if 'file' not in request.files:
            flash('Файл не выбран', 'error')
            return redirect(request.url)

        file = request.files['file']
        if file.filename == '':
            flash('Файл не выбран', 'error')
            return redirect(request.url)

        if not (file and allowed_file(file.filename)):
            flash('Недопустимый формат файла. Разрешены: mp3, wav, ogg', 'error')
            return redirect(request.url)

        # БЕЗОПАСНОСТЬ: уникальное имя через UUID — предотвращает перезапись
        original_ext = secure_filename(file.filename).rsplit('.', 1)[-1].lower()
        filename = f"{uuid.uuid4().hex}.{original_ext}"
        file.save(os.path.join(app.config['UPLOAD_FOLDER'], filename))

        new_song = Song(
            title=title,
            artist=artist,
            genre=genre,
            duration=duration,
            filename=filename,
            user_id=current_user.id
        )
        db.session.add(new_song)
        db.session.commit()
        flash('Трек успешно загружен!', 'success')
        return redirect(url_for('show_music'))

    return render_template('upload.html')


@app.route('/register', methods=['GET', 'POST'])
def register():
    if current_user.is_authenticated:
        return redirect(url_for('home'))

    if request.method == 'POST':
        username         = sanitize_text(request.form.get('username', ''))
        email            = sanitize_text(request.form.get('email', ''))
        password         = request.form.get('password', '')
        confirm_password = request.form.get('confirm_password', '')

        # Валидация имени пользователя
        if len(username) < 3 or len(username) > 20:
            flash('Имя пользователя: от 3 до 20 символов', 'error')
            return redirect(url_for('register'))

        if not re.match(r'^[A-Za-z0-9_]+$', username):
            flash('Имя пользователя может содержать только латинские буквы, цифры и _', 'error')
            return redirect(url_for('register'))

        # Валидация email
        if not re.match(r'^[^@\s]+@[^@\s]+\.[^@\s]+$', email):
            flash('Введите корректный email', 'error')
            return redirect(url_for('register'))

        # Валидация пароля
        pwd_error = validate_password(password)
        if pwd_error:
            flash(pwd_error, 'error')
            return redirect(url_for('register'))

        if password != confirm_password:
            flash('Пароли не совпадают', 'error')
            return redirect(url_for('register'))

        # Проверка уникальности
        if Users.query.filter_by(username=username).first():
            flash('Имя пользователя уже занято', 'error')
            return redirect(url_for('register'))

        if Users.query.filter_by(email=email).first():
            flash('Email уже используется', 'error')
            return redirect(url_for('register'))

        user = Users(username=username, email=email)
        user.set_password(password)
        db.session.add(user)
        db.session.commit()

        login_user(user)
        flash('Регистрация успешна! Добро пожаловать!', 'success')
        return redirect(url_for('home'))

    return render_template('register.html')


@app.route('/login', methods=['GET', 'POST'])
def login():
    if current_user.is_authenticated:
        return redirect(url_for('home'))

    if request.method == 'POST':
        ip = get_client_ip()

        # БЕЗОПАСНОСТЬ: проверяем блокировку по IP до любой обработки
        if is_ip_blocked(ip):
            remaining = BLOCK_MINUTES
            flash(
                f'Слишком много неудачных попыток входа. '
                f'Попробуйте через {remaining} минут.',
                'error'
            )
            return render_template('login.html')

        username = request.form.get('username', '').strip()
        password = request.form.get('password', '')
        remember = bool(request.form.get('remember'))

        user = Users.query.filter_by(username=username).first()

        if user and user.check_password(password):
            clear_attempts(ip)  # Сбросить счётчик при успехе
            login_user(user, remember=remember)
            flash('Вход выполнен успешно!', 'success')
            return redirect(safe_redirect_url())
        else:
            record_failed_attempt(ip)
            attempts_left = MAX_ATTEMPTS - len(login_attempts[ip])
            if attempts_left <= 2:
                flash(
                    f'Неверное имя пользователя или пароль. '
                    f'Осталось попыток: {max(0, attempts_left)}',
                    'error'
                )
            else:
                flash('Неверное имя пользователя или пароль', 'error')

    return render_template('login.html')


@app.route('/logout')
@login_required
def logout():
    logout_user()
    flash('Вы вышли из системы', 'info')
    return redirect(url_for('home'))


@app.route('/play/<int:song_id>')
def play_song(song_id):
    song = db.session.get(Song, song_id)
    if song is None:
        abort(404)
    song.plays += 1
    db.session.commit()
    return send_from_directory(app.config['UPLOAD_FOLDER'], song.filename)


@app.route('/profile')
@login_required
def profile():
    user_songs = Song.query.filter_by(user_id=current_user.id).all()
    return render_template('profile.html', user_songs=user_songs)


# ──────────────────────────────────────────────────────────────
#  ИНИЦИАЛИЗАЦИЯ БАЗЫ ДАННЫХ
# ──────────────────────────────────────────────────────────────

with app.app_context():
    db.create_all()
    # Сначала пользователь, потом треки — чтобы user_id существовал
    if Users.query.count() == 0:
        demo_user = Users(username='demo', email='demo@musicflow.com')
        demo_user.set_password('Demo@1234')  # Более надёжный пароль
        db.session.add(demo_user)
        db.session.flush()  # Получить demo_user.id до commit

        if Song.query.count() == 0:
            test_songs = [
                Song(title='Summer Vibes', artist='DJ Sunshine', genre='Electronic',
                     duration='3:45', filename='sample1.mp3', plays=1245, user_id=demo_user.id),
                Song(title='Night Drive', artist='Midnight Crew', genre='Synthwave',
                     duration='4:20', filename='sample2.mp3', plays=892, user_id=demo_user.id),
            ]
            db.session.add_all(test_songs)

        db.session.commit()
    elif Song.query.count() == 0:
        first_user = Users.query.first()
        test_songs = [
            Song(title='Summer Vibes', artist='DJ Sunshine', genre='Electronic',
                 duration='3:45', filename='sample1.mp3', plays=1245, user_id=first_user.id),
            Song(title='Night Drive', artist='Midnight Crew', genre='Synthwave',
                 duration='4:20', filename='sample2.mp3', plays=892, user_id=first_user.id),
        ]
        db.session.add_all(test_songs)
        db.session.commit()


# ──────────────────────────────────────────────────────────────
#  API — ВСПОМОГАТЕЛЬНЫЕ ФУНКЦИИ
# ──────────────────────────────────────────────────────────────

def song_to_dict(song):
    return {
        'id':          song.id,
        'title':       song.title,
        'artist':      song.artist,
        'genre':       song.genre,
        'duration':    song.duration,
        'filename':    song.filename,
        'plays':       song.plays,
        'upload_date': song.upload_date.isoformat() if song.upload_date else None,
        'user_id':     song.user_id,
        'stream_url':  f'/play/{song.id}',
    }


def api_error(message, status=400):
    return jsonify({'success': False, 'error': message}), status


# ──────────────────────────────────────────────────────────────
#  API — ТРЕКИ (CSRF exempt — это публичное API, не браузерные формы)
# ──────────────────────────────────────────────────────────────

@app.route('/api/songs', methods=['GET'])
@csrf.exempt
def api_get_songs():
    limit  = request.args.get('limit', type=int)
    offset = request.args.get('offset', default=0, type=int)
    sort   = request.args.get('sort', default='date')
    order  = request.args.get('order', default='desc')
    genre  = request.args.get('genre')
    search = request.args.get('search')

    query = Song.query

    if genre:
        query = query.filter(Song.genre.ilike(f'%{genre}%'))

    if search:
        query = query.filter(
            db.or_(
                Song.title.ilike(f'%{search}%'),
                Song.artist.ilike(f'%{search}%')
            )
        )

    sort_map = {
        'plays':  Song.plays,
        'date':   Song.upload_date,
        'title':  Song.title,
        'artist': Song.artist,
    }
    sort_col = sort_map.get(sort, Song.upload_date)
    query = query.order_by(sort_col.desc() if order == 'desc' else sort_col.asc())

    total = query.count()
    songs = query.offset(offset).limit(limit).all() if limit else query.offset(offset).all()

    return jsonify({
        'success': True,
        'total':   total,
        'count':   len(songs),
        'offset':  offset,
        'songs':   [song_to_dict(s) for s in songs],
    })


@app.route('/api/songs/<int:song_id>', methods=['GET'])
@csrf.exempt
def api_get_song(song_id):
    song = db.session.get(Song, song_id)
    if not song:
        return api_error('Трек не найден', 404)
    return jsonify({'success': True, 'song': song_to_dict(song)})


@app.route('/api/songs/top', methods=['GET'])
@csrf.exempt
def api_top_songs():
    limit = request.args.get('limit', default=10, type=int)
    songs = Song.query.order_by(Song.plays.desc()).limit(limit).all()
    return jsonify({
        'success': True,
        'count':   len(songs),
        'songs':   [song_to_dict(s) for s in songs],
    })


@app.route('/api/songs/new', methods=['GET'])
@csrf.exempt
def api_new_songs():
    limit = request.args.get('limit', default=10, type=int)
    songs = Song.query.order_by(Song.upload_date.desc()).limit(limit).all()
    return jsonify({
        'success': True,
        'count':   len(songs),
        'songs':   [song_to_dict(s) for s in songs],
    })


@app.route('/api/genres', methods=['GET'])
@csrf.exempt
def api_genres():
    results = db.session.query(
        Song.genre, db.func.count(Song.id).label('count')
    ).group_by(Song.genre).all()
    genres = [{'genre': r.genre, 'count': r.count} for r in results]
    return jsonify({'success': True, 'genres': genres})


@app.route('/api/stats', methods=['GET'])
@csrf.exempt
def api_stats():
    total_songs = Song.query.count()
    total_users = Users.query.count()
    total_plays = db.session.query(db.func.sum(Song.plays)).scalar() or 0
    top_song    = Song.query.order_by(Song.plays.desc()).first()
    top_genre   = db.session.query(
        Song.genre, db.func.count(Song.id).label('c')
    ).group_by(Song.genre).order_by(db.desc('c')).first()

    return jsonify({
        'success':     True,
        'total_songs': total_songs,
        'total_users': total_users,
        'total_plays': total_plays,
        'top_song':    song_to_dict(top_song) if top_song else None,
        'top_genre':   top_genre[0] if top_genre else None,
    })


# ──────────────────────────────────────────────────────────────
#  API — DISCOGS
# ──────────────────────────────────────────────────────────────

def discogs_request(url, params=None):
    headers = {
        'User-Agent': 'MusicFlow/1.0 (https://github.com/Bossmylobby/FlowMusic)'
    }
    if DISCOGS_TOKEN:
        headers['Authorization'] = f'Discogs token={DISCOGS_TOKEN}'

    try:
        r = requests.get(url, headers=headers, params=params, timeout=DISCOGS_TIMEOUT)
        r.raise_for_status()
        return r.json()
    except requests.exceptions.RequestException as e:
        return {'error': str(e)}


def format_discogs_track(item):
    """Форматирует трек из Discogs в единый формат для фронтенда."""
    return {
        'id':          item.get('id'),
        'title':       item.get('title', 'Без названия'),
        'artist':      item.get('artist', 'Неизвестный исполнитель'),
        'album':       'Discogs релиз',
        'cover':       item.get('cover_image', '') or item.get('thumb', ''),
        'preview_url': None,
        'duration':    '0:30',
        'source':      'discogs',
    }


@app.route('/api/deezer/charts')
@csrf.exempt
def deezer_charts():
    """Возвращает чарты (поиск в Discogs по жанру)."""
    limit = request.args.get('limit', default=30, type=int)
    genre = request.args.get('genre', default='0')

    genre_map = {
        '0': 'rock', '1': 'pop', '2': 'rock', '3': 'hip hop',
        '4': 'electronic', '5': 'jazz', '6': 'classical',
        '132': 'electronic', '116': 'hip hop', '152': 'rock',
    }
    search_query = genre_map.get(str(genre), 'rock')

    data = discogs_request(f"{DISCOGS}/database/search", params={
        'q': search_query, 'type': 'release', 'per_page': limit, 'page': 1,
    })

    if 'error' in data:
        return jsonify({'success': False, 'error': data['error'], 'tracks': []})

    tracks = [format_discogs_track(item) for item in data.get('results', [])]
    return jsonify({'success': True, 'count': len(tracks), 'tracks': tracks})


@app.route('/api/deezer/genres')
@app.route('/api/deezer/generes')
@csrf.exempt
def deezer_genres():
    """Возвращает список жанров."""
    genres = [
        {'id': 0,   'name': 'Все чарты'},
        {'id': 1,   'name': 'Pop'},
        {'id': 2,   'name': 'Rock'},
        {'id': 3,   'name': 'Hip Hop'},
        {'id': 4,   'name': 'Electronic'},
        {'id': 5,   'name': 'Jazz'},
        {'id': 6,   'name': 'Classical'},
        {'id': 132, 'name': 'Electronic / Dance'},
        {'id': 116, 'name': 'Rap'},
        {'id': 152, 'name': 'Rock / Alternative'},
    ]
    return jsonify({'success': True, 'genres': genres})


@app.route('/api/deezer/search')
@csrf.exempt
def deezer_search():
    """Поиск через Discogs."""
    q     = request.args.get('q', '').strip()
    limit = request.args.get('limit', default=20, type=int)

    if not q:
        return api_error('Параметр ?q= обязателен', 400)

    data = discogs_request(f"{DISCOGS}/database/search", params={
        'q': q, 'type': 'release', 'per_page': limit, 'page': 1,
    })

    if 'error' in data:
        return api_error(f'Discogs ошибка: {data["error"]}', 502)

    tracks = [format_discogs_track(item) for item in data.get('results', [])]
    return jsonify({'success': True, 'count': len(tracks), 'tracks': tracks})


# ──────────────────────────────────────────────────────────────
#  ЗАПУСК
# ──────────────────────────────────────────────────────────────

if __name__ == '__main__':
    debug_mode = os.environ.get('FLASK_DEBUG', '0') == '1'
    print("[*] MusicFlow zapushchen! http://localhost:5000")
    print("[*] API: /api/songs, /api/stats, /api/genres")
    print("[*] Diskaveri: /api/deezer/charts, /api/deezer/search")
    if debug_mode:
        print("[!] Rezhim otladki VKLYUCHEN — tolko dlya razrabotki!")
    app.run(debug=debug_mode)