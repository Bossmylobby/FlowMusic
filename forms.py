from flask_wtf import FlaskForm
from flask_wtf.file import FileField, FileAllowed, FileRequired
from wtforms import (
    StringField, PasswordField, BooleanField, SubmitField, SelectField
)
from wtforms.validators import (
    DataRequired, Email, EqualTo, Length, ValidationError, Optional, Regexp
)
from models import Users


class LoginForm(FlaskForm):
    username = StringField(
        'Имя пользователя',
        validators=[DataRequired(), Length(min=3, max=80)]
    )
    password = PasswordField('Пароль', validators=[DataRequired()])
    remember = BooleanField('Запомнить меня')
    submit = SubmitField('Войти')


class RegistrationForm(FlaskForm):
    username = StringField(
        'Имя пользователя',
        validators=[
            DataRequired(),
            Length(min=3, max=20, message='От 3 до 20 символов'),
            Regexp(
                r'^[A-Za-z0-9_]+$',
                message='Только латинские буквы, цифры и _'
            ),
        ]
    )
    email = StringField(
        'Email',
        validators=[DataRequired(), Email(message='Введите корректный email')]
    )
    password = PasswordField(
        'Пароль',
        validators=[
            DataRequired(),
            Length(min=8, message='Минимум 8 символов'),
        ]
    )
    confirm_password = PasswordField(
        'Подтвердите пароль',
        validators=[
            DataRequired(),
            EqualTo('password', message='Пароли не совпадают'),
        ]
    )
    submit = SubmitField('Создать аккаунт')

    def validate_username(self, field):
        if Users.query.filter_by(username=field.data).first():
            raise ValidationError('Это имя пользователя уже занято')

    def validate_email(self, field):
        if Users.query.filter_by(email=field.data).first():
            raise ValidationError('Этот email уже используется')

    def validate_password(self, field):
        import re
        pwd = field.data
        if not re.search(r'[A-Za-z]', pwd):
            raise ValidationError('Пароль должен содержать хотя бы одну букву')
        if not re.search(r'[\d\W_]', pwd):
            raise ValidationError('Пароль должен содержать цифру или спецсимвол')


class UploadForm(FlaskForm):
    title = StringField(
        'Название трека',
        validators=[DataRequired(), Length(max=100)]
    )
    artist = StringField(
        'Исполнитель',
        validators=[DataRequired(), Length(max=100)]
    )
    genre = SelectField(
        'Жанр',
        choices=[
            ('', '— выбрать —'),
            ('Pop', 'Pop'),
            ('Rock', 'Rock'),
            ('Electronic', 'Electronic'),
            ('Synthwave', 'Synthwave'),
            ('Hip-Hop', 'Hip-Hop'),
            ('Jazz', 'Jazz'),
            ('Classical', 'Classical'),
            ('R&B', 'R&B'),
            ('Country', 'Country'),
        ],
        validators=[DataRequired(message='Выберите жанр')]
    )
    duration = StringField(
        'Длительность',
        validators=[
            DataRequired(),
            Length(max=10),
            Regexp(r'^\d{1,2}:\d{2}$', message='Формат: мм:сс (например 3:45)'),
        ]
    )
    file = FileField(
        'Аудиофайл',
        validators=[
            FileRequired(message='Выберите файл'),
            FileAllowed(['mp3', 'wav', 'ogg'], 'Только mp3, wav, ogg'),
        ]
    )
    submit = SubmitField('Загрузить трек')

    def validate_duration(self, field):
        parts = field.data.split(':')
        if len(parts) == 2:
            try:
                secs = int(parts[1])
                if secs > 59:
                    raise ValidationError('Секунды должны быть от 00 до 59')
            except ValueError:
                raise ValidationError('Некорректный формат длительности')
