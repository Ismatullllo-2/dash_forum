from flask import Flask, render_template, url_for, redirect, request, flash
from flask_sqlalchemy import SQLAlchemy
from flask_login import LoginManager, current_user, login_user, logout_user, login_required, UserMixin
from datetime import datetime
import os
from werkzeug.security import generate_password_hash, check_password_hash


app = Flask(__name__)
app.config['SECRET_KEY'] = os.environ.get('SECRET_KEY', 'fallback-development-key-change-in-production')
basedir = os.path.abspath(os.path.dirname(__file__))
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///' + os.path.join(basedir, 'forum.db')
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False

db = SQLAlchemy(app)
login_manager = LoginManager(app)
login_manager.login_view = 'login'
login_manager.login_message = 'Пожалуйста, войдите для доступа к этой странице.'
login_manager.login_message_category = 'info'


class User(UserMixin, db.Model):
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(80), unique=True, nullable=False)
    email = db.Column(db.String(120), unique=True, nullable=False)
    password_hash = db.Column(db.String(120), nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    topics = db.relationship('Topic', backref='author', lazy=True)
    replies = db.relationship('Reply', backref='author', lazy=True)
    
    def set_password(self, password):
        self.password_hash = generate_password_hash(password)
    
    def check_password(self, password):
        return check_password_hash(self.password_hash, password)

class Topic(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    title = db.Column(db.String(200), nullable=False)
    content = db.Column(db.Text, nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    views = db.Column(db.Integer, default=0)
    replies = db.relationship('Reply', backref='topic', lazy=True, cascade='all, delete-orphan')
    
    @property
    def reply_count(self):
        return len(self.replies)
    
    @property
    def last_reply(self):
        return Reply.query.filter_by(topic_id=self.id).order_by(Reply.created_at.desc()).first()

class Reply(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    content = db.Column(db.Text, nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    topic_id = db.Column(db.Integer, db.ForeignKey('topic.id'), nullable=False)

@login_manager.user_loader
def load_user(user_id):
    return User.query.get(int(user_id))


with app.app_context():
    db.create_all()


@app.route('/')
def index():
    latest_topics = Topic.query.order_by(Topic.created_at.desc()).limit(5).all()
    return render_template('index.html', topics=latest_topics)

@app.route('/forum')
def topics():
    page = request.args.get('page', 1, type=int)
    per_page = 20
    
    all_topics = Topic.query.order_by(Topic.created_at.desc()).paginate(
        page=page, per_page=per_page, error_out=False)
    
    next_url = url_for('topics', page=all_topics.next_num) if all_topics.has_next else None
    prev_url = url_for('topics', page=all_topics.prev_num) if all_topics.has_prev else None
    
    return render_template('topics.html', 
                          topics=all_topics.items, 
                          next_url=next_url, 
                          prev_url=prev_url)

@app.route('/topic/<int:topic_id>')
def topic(topic_id):
    topic = Topic.query.get_or_404(topic_id)
    topic.views += 1
    db.session.commit()
    return render_template('topic.html', topic=topic)

@app.route('/new_topic', methods=['GET', 'POST'])
@login_required
def new_topic():
    if request.method == 'POST':
        title = request.form.get('title')
        content = request.form.get('content')
        
        if title and content:
            new_topic = Topic(title=title, content=content, user_id=current_user.id)
            db.session.add(new_topic)
            db.session.commit()
            flash('Тема успешно создана!', 'success')
            return redirect(url_for('topic', topic_id=new_topic.id))
        else:
            flash('Заполните все поля', 'error')
    
    return render_template('new_topic.html')

@app.route('/reply/<int:topic_id>', methods=['POST'])
@login_required
def reply(topic_id):
    topic = Topic.query.get_or_404(topic_id)
    content = request.form.get('content')
    
    if content:
        new_reply = Reply(content=content, user_id=current_user.id, topic_id=topic_id)
        db.session.add(new_reply)
        db.session.commit()
        flash('Ответ добавлен!', 'success')
    else:
        flash('Сообщение не может быть пустым', 'error')
    
    return redirect(url_for('topic', topic_id=topic_id))


@app.route('/login', methods=['GET', 'POST'])
def login():
    if current_user.is_authenticated:
        return redirect(url_for('index'))
    
    if request.method == 'POST':
        username = request.form.get('username')
        password = request.form.get('password')
        remember = bool(request.form.get('remember'))
        
        user = User.query.filter_by(username=username).first()
        
        if user and user.check_password(password):
            login_user(user, remember=remember)
            next_page = request.args.get('next')
            flash('Вы успешно вошли в систему!', 'success')
            return redirect(next_page or url_for('index'))
        else:
            flash('Неверное имя пользователя или пароль', 'error')
    
    return render_template('login.html')

@app.route('/register', methods=['GET', 'POST'])
def register():
    if current_user.is_authenticated:
        return redirect(url_for('index'))
    
    if request.method == 'POST':
        username = request.form.get('username')
        email = request.form.get('email')
        password = request.form.get('password')
        confirm_password = request.form.get('confirm_password')
        
        errors = []
        
        if not username or not email or not password:
            errors.append('Все поля обязательны для заполнения')
        
        if password != confirm_password:
            errors.append('Пароли не совпадают')
        
        if len(password) < 6:
            errors.append('Пароль должен содержать не менее 6 символов')
        
        if User.query.filter_by(username=username).first():
            errors.append('Имя пользователя уже занято')
        
        if User.query.filter_by(email=email).first():
            errors.append('Email уже зарегистрирован')
        
        if errors:
            for error in errors:
                flash(error, 'error')
        else:
            new_user = User(username=username, email=email)
            new_user.set_password(password)
            
            db.session.add(new_user)
            db.session.commit()
            
            flash('Регистрация прошла успешно! Теперь вы можете войти.', 'success')
            return redirect(url_for('login'))
    
    return render_template('register.html')

@app.route('/logout')
@login_required
def logout():
    logout_user()
    flash('Вы вышли из системы', 'info')
    return redirect(url_for('index'))

#рендер через 10 минут сервер глушит если никого нету это что бы не глушил
def start_keep_alive():
    import threading
    import time
    import requests
    from datetime import datetime
    
    def ping_server():
        while True:
            try:
                base_url = os.environ.get('RENDER_EXTERNAL_URL', 'http://localhost:5000')
                requests.get(f"{base_url}/", timeout=5)
                print(f"{datetime.now()} - Keep-alive ping sent to {base_url}")
            except Exception as e:
                print(f"{datetime.now()} - Ping error: {e}")
            time.sleep(300)  
    
    thread = threading.Thread(target=ping_server, daemon=True)
    thread.start()

# Запускаем keep-alive при старте
start_keep_alive()

if __name__ == '__main__':

    with app.app_context():
        db.drop_all()
        db.create_all()
        
        test_user = User(username='test', email='test@example.com')
        test_user.set_password('test')
        db.session.add(test_user)
        
        topic1 = Topic(title='Добро пожаловать на форум!', 
                      content='Это тестовая тема для демонстрации работы форума.', 
                      user_id=1)
        topic2 = Topic(title='Правила форума', 
                      content='Здесь будут правила нашего форума.', 
                      user_id=1)
        db.session.add_all([topic1, topic2])
        
        reply1 = Reply(content='Отличный форум!', user_id=1, topic_id=1)
        reply2 = Reply(content='Согласен с правилами', user_id=1, topic_id=2)
        db.session.add_all([reply1, reply2])
        
        db.session.commit()
        print("Test data created successfully!")
    
    port = int(os.environ.get('PORT', 5000))
    app.run(host='0.0.0.0', port=port, debug=False)

