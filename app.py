from flask import Flask, render_template, request, redirect, url_for, flash, send_from_directory
from flask_sqlalchemy import SQLAlchemy
from flask_login import LoginManager, UserMixin, login_user, logout_user, login_required, current_user
from werkzeug.security import generate_password_hash, check_password_hash
from werkzeug.utils import secure_filename
import os
from datetime import datetime

app = Flask(__name__)
app.config['SECRET_KEY'] = 'music-platform-secret-key-2024'
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///music.db'
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
app.config['UPLOAD_FOLDER'] = 'static/music'
app.config['ALLOWED_EXTENSIONS'] = {'mp3', 'wav', 'ogg'}

db = SQLAlchemy(app)
login_manager = LoginManager(app)
login_manager.login_view = 'login'
login_manager.login_message = 'Пожалуйста, войдите в систему.'

os.makedirs(app.config['UPLOAD_FOLDER'], exist_ok=True)

class Users(UserMixin, db.Model):
    __tablename__ = 'users'  
    
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(80), unique=True, nullable=False)
    email = db.Column(db.String(120), unique=True, nullable=False)
    password_hash = db.Column(db.String(120))
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    
    def set_password(self, password):
        self.password_hash = generate_password_hash(password)
    
    def check_password(self, password):
        return check_password_hash(self.password_hash, password)

class Song(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    title = db.Column(db.String(100), nullable=False)
    artist = db.Column(db.String(100), nullable=False)
    genre = db.Column(db.String(50), nullable=False)
    duration = db.Column(db.String(10))
    filename = db.Column(db.String(200))
    plays = db.Column(db.Integer, default=0)
    upload_date = db.Column(db.DateTime, default=datetime.utcnow)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'))   

@login_manager.user_loader
def load_user(user_id):
    return Users.query.get(int(user_id))

def allowed_file(filename):
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in app.config['ALLOWED_EXTENSIONS']

@app.route('/')
def home():
    popular_songs = Song.query.order_by(Song.plays.desc()).limit(6).all()
    recent_songs = Song.query.order_by(Song.upload_date.desc()).limit(6).all()
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
        if 'file' not in request.files:
            flash('Файл не выбран', 'error')
            return redirect(request.url)
        
        file = request.files['file']
        if file.filename == '':
            flash('Файл не выбран', 'error')
            return redirect(request.url)
        
        if file and allowed_file(file.filename):
            filename = secure_filename(file.filename)
            file.save(os.path.join(app.config['UPLOAD_FOLDER'], filename))
            
            new_song = Song(
                title=request.form['title'],
                artist=request.form['artist'],
                genre=request.form['genre'],
                duration=request.form['duration'],
                filename=filename,
                user_id=current_user.id
            )
            
            db.session.add(new_song)
            db.session.commit()
            flash('Трек успешно загружен!', 'success')
            return redirect(url_for('show_music'))
        else:
            flash('Недопустимый формат файла', 'error')
    
    return render_template('upload.html')

@app.route('/register', methods=['GET', 'POST'])
def register():
    if request.method == 'POST':
        username = request.form['username']
        email = request.form['email']
        password = request.form['password']
        confirm_password = request.form['confirm_password']
        
        if password != confirm_password:
            flash('Пароли не совпадают', 'error')
            return redirect(url_for('register'))
        
        if len(password) < 6:
            flash('Пароль должен содержать минимум 6 символов', 'error')
            return redirect(url_for('register'))
        
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
        flash('Регистрация успешна!', 'success')
        return redirect(url_for('home'))
    
    return render_template('register.html')

@app.route('/login', methods=['GET', 'POST'])
def login():
    if current_user.is_authenticated:
        return redirect(url_for('home'))
    
    if request.method == 'POST':
        username = request.form['username']
        password = request.form['password']
        remember = bool(request.form.get('remember'))
        
        user = Users.query.filter_by(username=username).first()
        if user and user.check_password(password):
            login_user(user, remember=remember)
            flash('Вход выполнен успешно!', 'success')
            return redirect(url_for('home'))
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
    song = Song.query.get_or_404(song_id)
    song.plays += 1
    db.session.commit()
    return send_from_directory(app.config['UPLOAD_FOLDER'], song.filename)

@app.route('/profile')
@login_required
def profile():
    user_songs = Song.query.filter_by(user_id=current_user.id).all()
    return render_template('profile.html', user_songs=user_songs)

with app.app_context():
    db.create_all()
    if Song.query.count() == 0:
        test_songs = [
            Song(title='Summer Vibes', artist='DJ Sunshine', genre='Electronic', duration='3:45', filename='sample1.mp3', plays=1245, user_id=1),
            Song(title='Night Drive', artist='Midnight Crew', genre='Synthwave', duration='4:20', filename='sample2.mp3', plays=892, user_id=1),
        ]
        db.session.bulk_save_objects(test_songs)
        
        if Users.query.count() == 0:
            user = Users(username='demo', email='demo@musicflow.com')
            user.set_password('demo123')
            db.session.add(user)
        
        db.session.commit()

if __name__ == '__main__':
    print("🎵 MusicFlow запущен! http://localhost:5000")
    app.run(debug=True)