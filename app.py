"""
MusicFlow — Flask-приложение для загрузки и прослушивания музыки.
Локальная библиотека + WTForms + Flask-Login.
"""
from flask import (
    Flask, render_template, request, redirect, url_for,
    flash, send_from_directory, jsonify, abort
)
from flask_login import (
    LoginManager, login_user, logout_user,
    login_required, current_user
)
from flask_wtf.csrf import CSRFProtect, CSRFError
from werkzeug.utils import secure_filename
from dotenv import load_dotenv
from collections import defaultdict
from datetime import datetime, timedelta, timezone
import os
import uuid

from models import db, Users, Song
from forms import LoginForm, RegistrationForm, UploadForm

# ──────────────────────────────────────────────────────────────
#  БАЗОВЫЙ ПУТЬ (локально + Render / PythonAnywhere)
# ──────────────────────────────────────────────────────────────

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
load_dotenv(os.path.join(BASE_DIR, '.env'))

# ──────────────────────────────────────────────────────────────
#  КОНФИГУРАЦИЯ
# ──────────────────────────────────────────────────────────────

app = Flask(__name__)

_secret = os.environ.get('SECRET_KEY')
if not _secret or _secret == 'замени-на-случайную-строку-минимум-32-символа':
    import secrets
    _secret = secrets.token_hex(32)
    print(
        '[!] SECRET_KEY не задан в .env — используется временный ключ. '
        'Сессии сбросятся при перезапуске!'
    )

app.config['SECRET_KEY'] = _secret
# Абсолютный путь к БД
os.makedirs(os.path.join(BASE_DIR, 'instance'), exist_ok=True)
app.config['SQLALCHEMY_DATABASE_URI'] = (
    'sqlite:///' + os.path.join(BASE_DIR, 'instance', 'music.db')
)
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
app.config['UPLOAD_FOLDER'] = os.path.join(BASE_DIR, 'static', 'music')
app.config['ALLOWED_EXTENSIONS'] = {'mp3', 'wav', 'ogg'}
app.config['MAX_CONTENT_LENGTH'] = 50 * 1024 * 1024  # 50 МБ
app.config['WTF_CSRF_TIME_LIMIT'] = 3600

db.init_app(app)
csrf = CSRFProtect(app)

login_manager = LoginManager(app)
login_manager.login_view = 'login'
login_manager.login_message = 'Пожалуйста, войдите в систему.'
login_manager.login_message_category = 'info'

os.makedirs(app.config['UPLOAD_FOLDER'], exist_ok=True)


@login_manager.user_loader
def load_user(user_id):
    return db.session.get(Users, int(user_id))


# ──────────────────────────────────────────────────────────────
#  RATE-LIMIT (in-memory)
#  Для продакшена лучше Redis / таблица в БД.
# ──────────────────────────────────────────────────────────────

login_attempts: dict[str, list] = defaultdict(list)
MAX_ATTEMPTS = 5
BLOCK_MINUTES = 15


def get_client_ip() -> str:
    return (
        request.headers.get('X-Forwarded-For', request.remote_addr or 'unknown')
        .split(',')[0]
        .strip()
    )


def is_ip_blocked(ip: str) -> bool:
    now = datetime.now(timezone.utc)
    cutoff = now - timedelta(minutes=BLOCK_MINUTES)
    login_attempts[ip] = [t for t in login_attempts[ip] if t > cutoff]
    return len(login_attempts[ip]) >= MAX_ATTEMPTS


def record_failed_attempt(ip: str) -> None:
    login_attempts[ip].append(datetime.now(timezone.utc))


def clear_attempts(ip: str) -> None:
    login_attempts.pop(ip, None)


# ──────────────────────────────────────────────────────────────
#  SECURITY HEADERS
# ──────────────────────────────────────────────────────────────

@app.after_request
def set_security_headers(response):
    response.headers['X-Frame-Options'] = 'SAMEORIGIN'
    response.headers['X-Content-Type-Options'] = 'nosniff'
    response.headers['Referrer-Policy'] = 'strict-origin-when-cross-origin'
    response.headers['X-XSS-Protection'] = '1; mode=block'
    response.headers['Permissions-Policy'] = 'geolocation=(), microphone=(), camera=()'
    return response


@app.errorhandler(CSRFError)
def handle_csrf_error(e):
    flash('Форма устарела. Пожалуйста, попробуйте снова.', 'error')
    return redirect(request.referrer or url_for('home'))


# ──────────────────────────────────────────────────────────────
#  ВСПОМОГАТЕЛЬНЫЕ
# ──────────────────────────────────────────────────────────────

def safe_redirect_url() -> str:
    """Защита от open redirect."""
    next_url = request.args.get('next') or request.form.get('next', '')
    if next_url and next_url.startswith('/') and not next_url.startswith('//'):
        return next_url
    return url_for('home')


def sanitize_text(value: str, max_len: int = 100) -> str:
    return (value or '').strip()[:max_len]


# ──────────────────────────────────────────────────────────────
#  СТРАНИЦЫ
# ──────────────────────────────────────────────────────────────

@app.route('/')
def home():
    popular_songs = Song.query.order_by(Song.plays.desc()).limit(6).all()
    recent_songs = Song.query.order_by(Song.upload_date.desc()).limit(6).all()
    return render_template(
        'index.html',
        popular_songs=popular_songs,
        recent_songs=recent_songs,
        total_songs=Song.query.count(),
        total_users=Users.query.count(),
    )


@app.route('/music')
def show_music():
    songs = Song.query.all()
    return render_template('music.html', songs=songs)


@app.route('/upload', methods=['GET', 'POST'])
@login_required
def upload():
    form = UploadForm()
    if form.validate_on_submit():
        file = form.file.data
        original_ext = secure_filename(file.filename).rsplit('.', 1)[-1].lower()
        filename = f'{uuid.uuid4().hex}.{original_ext}'
        file.save(os.path.join(app.config['UPLOAD_FOLDER'], filename))

        song = Song(
            title=sanitize_text(form.title.data),
            artist=sanitize_text(form.artist.data),
            genre=form.genre.data,
            duration=form.duration.data.strip(),
            filename=filename,
            user_id=current_user.id,
        )
        db.session.add(song)
        db.session.commit()
        flash('Трек успешно загружен!', 'success')
        return redirect(url_for('show_music'))

    return render_template('upload.html', form=form)


@app.route('/register', methods=['GET', 'POST'])
def register():
    if current_user.is_authenticated:
        return redirect(url_for('home'))

    form = RegistrationForm()
    if form.validate_on_submit():
        user = Users(
            username=form.username.data.strip(),
            email=form.email.data.strip().lower(),
        )
        user.set_password(form.password.data)
        db.session.add(user)
        db.session.commit()
        login_user(user)
        flash('Регистрация успешна! Добро пожаловать!', 'success')
        return redirect(url_for('home'))

    return render_template('register.html', form=form)


@app.route('/login', methods=['GET', 'POST'])
def login():
    if current_user.is_authenticated:
        return redirect(url_for('home'))

    form = LoginForm()
    if form.validate_on_submit():
        ip = get_client_ip()

        if is_ip_blocked(ip):
            flash(
                f'Слишком много неудачных попыток. '
                f'Попробуйте через {BLOCK_MINUTES} минут.',
                'error',
            )
            return render_template('login.html', form=form)

        user = Users.query.filter_by(username=form.username.data.strip()).first()
        if user and user.check_password(form.password.data):
            clear_attempts(ip)
            login_user(user, remember=form.remember.data)
            flash('Вход выполнен успешно!', 'success')
            return redirect(safe_redirect_url())

        record_failed_attempt(ip)
        left = MAX_ATTEMPTS - len(login_attempts[ip])
        if left <= 2:
            flash(
                f'Неверное имя пользователя или пароль. '
                f'Осталось попыток: {max(0, left)}',
                'error',
            )
        else:
            flash('Неверное имя пользователя или пароль', 'error')

    return render_template('login.html', form=form)


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

    filepath = os.path.join(app.config['UPLOAD_FOLDER'], song.filename or '')
    if not song.filename or not os.path.isfile(filepath):
        abort(404)

    return send_from_directory(app.config['UPLOAD_FOLDER'], song.filename)

@app.route('/api/songs/<int:song_id>/play', methods=['POST'])
@csrf.exempt
def api_count_play(song_id):
    song = db.session.get(Song, song_id)
    if not song:
        return jsonify({'success': False, 'error': 'Трек не найден'}), 404
    path = os.path.join(app.config['UPLOAD_FOLDER'], song.filename or '')
    if not song.filename or not os.path.isfile(path):
        return jsonify({'success': False, 'error': 'Файл отсутствует'}), 404
    song.plays = (song.plays or 0) + 1
    db.session.commit()
    return jsonify({'success': True, 'plays': song.plays})

@app.route('/profile')
@login_required
def profile():
    # Через relationship
    user_songs = current_user.songs.order_by(Song.upload_date.desc()).all()
    return render_template('profile.html', user_songs=user_songs)


# ──────────────────────────────────────────────────────────────
#  ИНИЦИАЛИЗАЦИЯ БД
# ──────────────────────────────────────────────────────────────

def init_db():
    with app.app_context():
        db.create_all()
        # Только демо-пользователь. Треки без реальных файлов не создаём —
        # иначе «Слушать» на главной/в библиотеке ведёт на 404.
        if Users.query.count() == 0:
            demo = Users(username='demo', email='demo@musicflow.com')
            demo.set_password('Demo@1234')
            db.session.add(demo)
            db.session.commit()
            print('[*] Создан демо-пользователь: demo / Demo@1234')



# ──────────────────────────────────────────────────────────────
#  API — helpers
# ──────────────────────────────────────────────────────────────

def song_to_dict(song: Song) -> dict:
    return {
        'id': song.id,
        'title': song.title,
        'artist': song.artist,
        'genre': song.genre,
        'duration': song.duration,
        'filename': song.filename,
        'plays': song.plays,
        'upload_date': song.upload_date.isoformat() if song.upload_date else None,
        'user_id': song.user_id,
        'stream_url': f'/play/{song.id}',
    }


def api_error(message: str, status: int = 400):
    return jsonify({'success': False, 'error': message}), status


# ──────────────────────────────────────────────────────────────
#  API — треки
# ──────────────────────────────────────────────────────────────




@app.route('/api/songs', methods=['GET'])
@csrf.exempt
def api_get_songs():
    limit = request.args.get('limit', type=int)
    offset = request.args.get('offset', default=0, type=int)
    sort = request.args.get('sort', default='date')
    order = request.args.get('order', default='desc')
    genre = request.args.get('genre')
    search = request.args.get('search')

    query = Song.query

    if genre:
        query = query.filter(Song.genre.ilike(f'%{genre}%'))
    if search:
        query = query.filter(
            db.or_(
                Song.title.ilike(f'%{search}%'),
                Song.artist.ilike(f'%{search}%'),
            )
        )

    sort_map = {
        'plays': Song.plays,
        'date': Song.upload_date,
        'title': Song.title,
        'artist': Song.artist,
    }
    sort_col = sort_map.get(sort, Song.upload_date)
    query = query.order_by(sort_col.desc() if order == 'desc' else sort_col.asc())

    total = query.count()
    songs = (
        query.offset(offset).limit(limit).all()
        if limit
        else query.offset(offset).all()
    )

    return jsonify({
        'success': True,
        'total': total,
        'count': len(songs),
        'offset': offset,
        'songs': [song_to_dict(s) for s in songs],
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
        'count': len(songs),
        'songs': [song_to_dict(s) for s in songs],
    })


@app.route('/api/songs/new', methods=['GET'])
@csrf.exempt
def api_new_songs():
    limit = request.args.get('limit', default=10, type=int)
    songs = Song.query.order_by(Song.upload_date.desc()).limit(limit).all()
    return jsonify({
        'success': True,
        'count': len(songs),
        'songs': [song_to_dict(s) for s in songs],
    })


@app.route('/api/genres', methods=['GET'])
@csrf.exempt
def api_genres():
    results = (
        db.session.query(Song.genre, db.func.count(Song.id).label('count'))
        .group_by(Song.genre)
        .all()
    )
    genres = [{'genre': r.genre, 'count': r.count} for r in results]
    return jsonify({'success': True, 'genres': genres})


@app.route('/api/stats', methods=['GET'])
@csrf.exempt
def api_stats():
    total_songs = Song.query.count()
    total_users = Users.query.count()
    total_plays = db.session.query(db.func.sum(Song.plays)).scalar() or 0
    top_song = Song.query.order_by(Song.plays.desc()).first()
    top_genre = (
        db.session.query(Song.genre, db.func.count(Song.id).label('c'))
        .group_by(Song.genre)
        .order_by(db.desc('c'))
        .first()
    )
    return jsonify({
        'success': True,
        'total_songs': total_songs,
        'total_users': total_users,
        'total_plays': total_plays,
        'top_song': song_to_dict(top_song) if top_song else None,
        'top_genre': top_genre[0] if top_genre else None,
    })


# ──────────────────────────────────────────────────────────────
#  ЗАПУСК
# ──────────────────────────────────────────────────────────────

if __name__ == '__main__':
    init_db()
    debug_mode = os.environ.get('FLASK_DEBUG', '0') == '1'
    print('[*] MusicFlow → http://localhost:5000')
    print('[*] API: /api/songs, /api/songs/top, /api/songs/new, /api/stats')
    if debug_mode:
        print('[!] Режим отладки ВКЛЮЧЁН')
    app.run(debug=debug_mode, host='0.0.0.0', port=5000)


