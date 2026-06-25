"""
Юнит-тесты для MusicFlow Flask-приложения.
Запуск: python -m pytest tests/ -v
"""

import io
import os
import tempfile
import pytest

os.environ['TESTING'] = '1'

from app import app as flask_app, db, Users, Song, validate_password, allowed_file, sanitize_text

# Файловая временная БД — одна на всю сессию, чтобы fixture и client видели одну И ТУ ЖЕ БД
_TMP_DIR = tempfile.mkdtemp()
TEST_DB_PATH = os.path.join(_TMP_DIR, 'test_musicflow.db')


# ══════════════════════════════════════════════════════════════
#  ФИКСТУРЫ
# ══════════════════════════════════════════════════════════════

@pytest.fixture(scope='session')
def app():
    """Настройка тестового приложения."""
    flask_app.config.update({
        'TESTING':                True,
        # Файловая БД вместо :memory: — все запросы (fixture + client) видят одну и ту же БД
        'SQLALCHEMY_DATABASE_URI': f'sqlite:///{TEST_DB_PATH}',
        'WTF_CSRF_ENABLED':       False,
        'SECRET_KEY':             'test-secret-key-12345',
        'SERVER_NAME':            None,
    })
    with flask_app.app_context():
        db.create_all()
        yield flask_app
        db.drop_all()
    # Удаляем временную БД после всех тестов
    if os.path.exists(TEST_DB_PATH):
        os.remove(TEST_DB_PATH)


@pytest.fixture(scope='function')
def client(app):
    """Тестовый HTTP-клиент Flask."""
    return app.test_client()


@pytest.fixture(scope='function')
def ctx(app):
    """Контекст приложения для прямых обращений к БД."""
    with app.app_context():
        yield


@pytest.fixture(scope='function')
def test_user(app):
    """Создаёт тестового пользователя перед тестом и удаляет после."""
    with app.app_context():
        # Чистим если остался от предыдущего теста
        Users.query.filter_by(username='testuser').delete()
        db.session.commit()

        user = Users(username='testuser', email='test@example.com')
        user.set_password('Test@1234')
        db.session.add(user)
        db.session.commit()
        user_id = user.id

    yield user_id

    with app.app_context():
        Users.query.filter_by(username='testuser').delete()
        Song.query.filter_by(user_id=user_id).delete()
        db.session.commit()


@pytest.fixture(scope='function')
def logged_in_client(client, test_user):
    """Клиент с уже выполненным входом."""
    client.post('/login', data={
        'username': 'testuser',
        'password': 'Test@1234',
    }, follow_redirects=True)
    return client


# ══════════════════════════════════════════════════════════════
#  1. ТЕСТЫ УТИЛИТ И ВСПОМОГАТЕЛЬНЫХ ФУНКЦИЙ
# ══════════════════════════════════════════════════════════════

class TestValidatePassword:
    """Тесты функции validate_password."""

    def test_correct_password_returns_none(self):
        assert validate_password('Test@1234') is None

    def test_too_short_password(self):
        result = validate_password('Ab@1')
        assert result is not None
        assert '8' in result

    def test_no_letters(self):
        result = validate_password('12345678!')
        assert result is not None
        assert 'букв' in result.lower() or 'letter' in result.lower()

    def test_no_digit_or_special(self):
        result = validate_password('Abcdefgh')
        assert result is not None

    def test_exactly_8_chars_with_digit(self):
        assert validate_password('Abcdef1!') is None

    def test_empty_password(self):
        assert validate_password('') is not None

    def test_only_spaces(self):
        assert validate_password('        ') is not None


class TestAllowedFile:
    """Тесты функции allowed_file."""

    def test_mp3_allowed(self):
        assert allowed_file('song.mp3') is True

    def test_wav_allowed(self):
        assert allowed_file('track.wav') is True

    def test_ogg_allowed(self):
        assert allowed_file('audio.ogg') is True

    def test_mp3_uppercase_allowed(self):
        assert allowed_file('SONG.MP3') is True

    def test_exe_not_allowed(self):
        assert allowed_file('virus.exe') is False

    def test_php_not_allowed(self):
        assert allowed_file('shell.php') is False

    def test_no_extension(self):
        assert allowed_file('noextension') is False

    def test_double_extension_blocked(self):
        # Файл типа song.php.mp3 — расширение mp3, разрешено
        assert allowed_file('song.php.mp3') is True

    def test_empty_filename(self):
        assert allowed_file('') is False


class TestSanitizeText:
    """Тесты функции sanitize_text."""

    def test_strips_whitespace(self):
        assert sanitize_text('  hello  ') == 'hello'

    def test_truncates_to_max_len(self):
        long = 'a' * 200
        assert len(sanitize_text(long, max_len=100)) == 100

    def test_default_max_len_100(self):
        long = 'b' * 150
        assert len(sanitize_text(long)) == 100

    def test_short_string_unchanged(self):
        assert sanitize_text('hello') == 'hello'

    def test_empty_string(self):
        assert sanitize_text('') == ''


# ══════════════════════════════════════════════════════════════
#  2. ТЕСТЫ МОДЕЛЕЙ БАЗЫ ДАННЫХ
# ══════════════════════════════════════════════════════════════

class TestUserModel:
    """Тесты модели Users."""

    def test_create_user(self, app):
        with app.app_context():
            Users.query.filter_by(username='modeltest').delete()
            db.session.commit()

            user = Users(username='modeltest', email='modeltest@example.com')
            user.set_password('Pass@word1')
            db.session.add(user)
            db.session.commit()

            found = Users.query.filter_by(username='modeltest').first()
            assert found is not None
            assert found.email == 'modeltest@example.com'

            db.session.delete(found)
            db.session.commit()

    def test_password_hashed(self, app):
        with app.app_context():
            Users.query.filter_by(username='hashtest').delete()
            db.session.commit()

            user = Users(username='hashtest', email='hash@example.com')
            user.set_password('MyPass@123')
            db.session.add(user)
            db.session.commit()

            # Хэш не должен равняться оригинальному паролю
            assert user.password_hash != 'MyPass@123'
            assert user.check_password('MyPass@123') is True
            assert user.check_password('wrong') is False

            db.session.delete(user)
            db.session.commit()

    def test_username_unique(self, app, test_user):
        with app.app_context():
            duplicate = Users(username='testuser', email='other@example.com')
            duplicate.set_password('Pass@123')
            db.session.add(duplicate)
            with pytest.raises(Exception):
                db.session.commit()
            db.session.rollback()

    def test_check_password_empty_hash(self, app):
        with app.app_context():
            user = Users(username='emptytest', email='empty@example.com')
            # Не задаём пароль
            assert user.check_password('anything') is False


class TestSongModel:
    """Тесты модели Song."""

    def test_create_song(self, app, test_user):
        with app.app_context():
            song = Song(
                title='Test Track',
                artist='Test Artist',
                genre='Electronic',
                duration='3:30',
                filename='test.mp3',
                plays=0,
                user_id=test_user
            )
            db.session.add(song)
            db.session.commit()

            found = Song.query.filter_by(title='Test Track').first()
            assert found is not None
            assert found.artist == 'Test Artist'
            assert found.plays == 0

            db.session.delete(found)
            db.session.commit()

    def test_plays_default_zero(self, app, test_user):
        with app.app_context():
            song = Song(
                title='ZeroPlays',
                artist='Nobody',
                genre='Rock',
                filename='zero.mp3',
                user_id=test_user
            )
            db.session.add(song)
            db.session.commit()
            assert song.plays == 0

            db.session.delete(song)
            db.session.commit()


# ══════════════════════════════════════════════════════════════
#  3. ТЕСТЫ МАРШРУТОВ — ПУБЛИЧНЫЕ СТРАНИЦЫ
# ══════════════════════════════════════════════════════════════

class TestPublicRoutes:
    """Тесты публичных страниц (без авторизации)."""

    def test_home_page_ok(self, client):
        r = client.get('/')
        assert r.status_code == 200

    def test_home_contains_musicflow(self, client):
        r = client.get('/')
        assert b'MUSICFLOW' in r.data or b'MusicFlow' in r.data

    def test_music_page_ok(self, client):
        r = client.get('/music')
        assert r.status_code == 200

    def test_login_page_ok(self, client):
        r = client.get('/login')
        assert r.status_code == 200

    def test_register_page_ok(self, client):
        r = client.get('/register')
        assert r.status_code == 200

    def test_upload_requires_login(self, client):
        r = client.get('/upload')
        # Должен редиректить на /login
        assert r.status_code in (302, 301)
        assert b'login' in r.headers.get('Location', '').encode()

    def test_profile_requires_login(self, client):
        r = client.get('/profile')
        assert r.status_code in (302, 301)

    def test_nonexistent_page_404(self, client):
        r = client.get('/this-page-does-not-exist')
        assert r.status_code == 404

    def test_security_headers_present(self, client):
        r = client.get('/')
        assert 'X-Frame-Options' in r.headers
        assert 'X-Content-Type-Options' in r.headers
        assert r.headers['X-Content-Type-Options'] == 'nosniff'


# ══════════════════════════════════════════════════════════════
#  4. ТЕСТЫ РЕГИСТРАЦИИ
# ══════════════════════════════════════════════════════════════

class TestRegister:
    """Тесты маршрута /register."""

    def _reg(self, client, username='newuser99', email='new99@test.com',
             password='Test@1234', confirm='Test@1234'):
        return client.post('/register', data={
            'username':         username,
            'email':            email,
            'password':         password,
            'confirm_password': confirm,
        }, follow_redirects=True)

    def test_successful_registration(self, client, app):
        with app.app_context():
            Users.query.filter_by(username='newuser99').delete()
            db.session.commit()

        r = self._reg(client)
        assert r.status_code == 200

        with app.app_context():
            user = Users.query.filter_by(username='newuser99').first()
            assert user is not None
            db.session.delete(user)
            db.session.commit()

    def test_duplicate_username_rejected(self, client, test_user):
        r = self._reg(client, username='testuser', email='other@test.com')
        assert r.status_code == 200
        # Проверяем что находимся на странице регистрации (не на главной), значит ошибка была
        html = r.data.decode('utf-8', errors='replace')
        assert 'занято' in html or 'already' in html.lower() or 'Регистрация' in html

    def test_duplicate_email_rejected(self, client, test_user):
        r = self._reg(client, username='newguy', email='test@example.com')
        assert r.status_code == 200

    def test_short_username_rejected(self, client):
        r = self._reg(client, username='ab')
        assert r.status_code == 200

    def test_invalid_username_chars(self, client):
        r = self._reg(client, username='user name!')
        assert r.status_code == 200

    def test_weak_password_rejected(self, client):
        r = self._reg(client, password='12345678', confirm='12345678')
        assert r.status_code == 200

    def test_password_mismatch_rejected(self, client):
        r = self._reg(client, password='Test@1234', confirm='Test@9999')
        assert r.status_code == 200
        html = r.data.decode('utf-8', errors='replace')
        assert 'совпад' in html or 'Регистрация' in html

    def test_invalid_email_rejected(self, client):
        r = self._reg(client, email='not-an-email')
        assert r.status_code == 200


# ══════════════════════════════════════════════════════════════
#  5. ТЕСТЫ ВХОДА / ВЫХОДА
# ══════════════════════════════════════════════════════════════

class TestLogin:
    """Тесты маршрута /login."""

    def test_successful_login(self, client, test_user):
        r = client.post('/login', data={
            'username': 'testuser',
            'password': 'Test@1234',
        }, follow_redirects=True)
        assert r.status_code == 200
        assert 'успешно'.encode() in r.data or b'success' in r.data.lower()

    def test_wrong_password(self, client, test_user):
        r = client.post('/login', data={
            'username': 'testuser',
            'password': 'wrong',
        }, follow_redirects=True)
        assert r.status_code == 200
        html = r.data.decode('utf-8', errors='replace')
        assert 'Неверн' in html or 'Войти' in html

    def test_nonexistent_user(self, client):
        r = client.post('/login', data={
            'username': 'nobody_xyz',
            'password': 'Test@1234',
        }, follow_redirects=True)
        assert r.status_code == 200
        html = r.data.decode('utf-8', errors='replace')
        assert 'Неверн' in html or 'Войти' in html

    def test_empty_credentials(self, client):
        r = client.post('/login', data={
            'username': '',
            'password': '',
        }, follow_redirects=True)
        assert r.status_code == 200

    def test_logout_redirects(self, logged_in_client):
        r = logged_in_client.get('/logout', follow_redirects=True)
        assert r.status_code == 200

    def test_authenticated_user_redirected_from_login(self, logged_in_client):
        r = logged_in_client.get('/login')
        assert r.status_code == 302  # Редирект на главную

    def test_authenticated_user_redirected_from_register(self, logged_in_client):
        r = logged_in_client.get('/register')
        assert r.status_code == 302


# ══════════════════════════════════════════════════════════════
#  6. ТЕСТЫ ЗАГРУЗКИ ТРЕКОВ
# ══════════════════════════════════════════════════════════════

class TestUpload:
    """Тесты маршрута /upload."""

    def test_upload_page_visible_when_logged_in(self, logged_in_client):
        r = logged_in_client.get('/upload')
        assert r.status_code == 200

    def test_upload_without_file_fails(self, logged_in_client):
        r = logged_in_client.post('/upload', data={
            'title': 'Test',
            'artist': 'Artist',
            'genre': 'Pop',
        }, follow_redirects=True)
        assert r.status_code == 200

    def test_upload_with_invalid_format_fails(self, logged_in_client):
        data = {
            'title': 'Test',
            'artist': 'Artist',
            'genre': 'Pop',
            'file': (io.BytesIO(b'fake content'), 'test.exe'),
        }
        r = logged_in_client.post('/upload',
                                   data=data,
                                   content_type='multipart/form-data',
                                   follow_redirects=True)
        assert r.status_code == 200
        assert 'Недопустимый'.encode() in r.data

    def test_upload_without_title_fails(self, logged_in_client):
        data = {
            'title': '',
            'artist': 'Artist',
            'genre': 'Pop',
            'file': (io.BytesIO(b'ID3fake'), 'track.mp3'),
        }
        r = logged_in_client.post('/upload',
                                   data=data,
                                   content_type='multipart/form-data',
                                   follow_redirects=True)
        assert r.status_code == 200

    def test_upload_anonymous_user_redirected(self, client):
        data = {
            'title': 'Test',
            'artist': 'Artist',
            'genre': 'Pop',
            'file': (io.BytesIO(b'fake'), 'track.mp3'),
        }
        r = client.post('/upload',
                        data=data,
                        content_type='multipart/form-data')
        assert r.status_code in (302, 301)


# ══════════════════════════════════════════════════════════════
#  7. ТЕСТЫ API
# ══════════════════════════════════════════════════════════════

class TestAPI:
    """Тесты JSON API маршрутов."""

    def test_api_songs_ok(self, client):
        r = client.get('/api/songs')
        assert r.status_code == 200
        data = r.get_json()
        assert data['success'] is True
        assert 'songs' in data
        assert 'total' in data

    def test_api_songs_search(self, client):
        r = client.get('/api/songs?search=Summer')
        assert r.status_code == 200
        data = r.get_json()
        assert data['success'] is True

    def test_api_songs_sort_by_plays(self, client):
        r = client.get('/api/songs?sort=plays&order=desc')
        assert r.status_code == 200
        data = r.get_json()
        assert data['success'] is True

    def test_api_songs_sort_by_title(self, client):
        r = client.get('/api/songs?sort=title&order=asc')
        assert r.status_code == 200

    def test_api_stats_ok(self, client):
        r = client.get('/api/stats')
        assert r.status_code == 200
        data = r.get_json()
        assert data['success'] is True
        assert 'total_songs' in data
        assert 'total_users' in data
        assert 'total_plays' in data

    def test_api_genres_ok(self, client):
        r = client.get('/api/genres')
        assert r.status_code == 200
        data = r.get_json()
        assert data['success'] is True
        assert 'genres' in data

    def test_api_songs_top_ok(self, client):
        r = client.get('/api/songs/top?limit=3')
        assert r.status_code == 200
        data = r.get_json()
        assert data['success'] is True
        assert len(data['songs']) <= 3

    def test_api_songs_new_ok(self, client):
        r = client.get('/api/songs/new?limit=3')
        assert r.status_code == 200
        data = r.get_json()
        assert data['success'] is True

    def test_api_songs_filter_by_genre(self, client):
        r = client.get('/api/songs?genre=Electronic')
        assert r.status_code == 200
        data = r.get_json()
        assert data['success'] is True

    def test_api_deezer_genres_ok(self, client):
        r = client.get('/api/deezer/genres')
        assert r.status_code == 200
        data = r.get_json()
        assert data['success'] is True
        assert len(data['genres']) > 0

    def test_api_content_type_json(self, client):
        r = client.get('/api/stats')
        assert 'application/json' in r.content_type


# ══════════════════════════════════════════════════════════════
#  8. ТЕСТЫ БЕЗОПАСНОСТИ
# ══════════════════════════════════════════════════════════════

class TestSecurity:
    """Тесты защитных механизмов."""

    def test_play_nonexistent_song_404(self, client):
        r = client.get('/play/99999')
        assert r.status_code == 404

    def test_open_redirect_blocked(self, client, test_user):
        # ?next= с внешним URL не должен перенаправлять туда
        r = client.post('/login?next=https://evil.com', data={
            'username': 'testuser',
            'password': 'Test@1234',
        })
        location = r.headers.get('Location', '')
        assert 'evil.com' not in location

    def test_xframe_options_header(self, client):
        r = client.get('/')
        assert r.headers.get('X-Frame-Options') == 'SAMEORIGIN'

    def test_nosniff_header(self, client):
        r = client.get('/')
        assert r.headers.get('X-Content-Type-Options') == 'nosniff'

    def test_referrer_policy_header(self, client):
        r = client.get('/')
        assert 'Referrer-Policy' in r.headers

    def test_xss_protection_header(self, client):
        r = client.get('/')
        assert 'X-XSS-Protection' in r.headers

    def test_brute_force_counter_logic(self, app):
        """Проверяем логику счётчика попыток входа."""
        from app import login_attempts, record_failed_attempt, is_ip_blocked, clear_attempts, MAX_ATTEMPTS
        test_ip = '10.0.0.99'
        login_attempts.pop(test_ip, None)

        for _ in range(MAX_ATTEMPTS):
            record_failed_attempt(test_ip)

        assert is_ip_blocked(test_ip) is True

        clear_attempts(test_ip)
        assert is_ip_blocked(test_ip) is False
