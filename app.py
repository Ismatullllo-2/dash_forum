from flask import Flask, render_template, url_for, redirect, request, flash, send_from_directory
from flask_sqlalchemy import SQLAlchemy
from flask_login import LoginManager, current_user, login_user, logout_user, login_required, UserMixin
from datetime import datetime
import os
from werkzeug.security import generate_password_hash, check_password_hash
from werkzeug.utils import secure_filename

app = Flask(__name__)
app.config['SECRET_KEY'] = os.environ.get('SECRET_KEY', 'dev-secret-key-change-in-production')

basedir = os.path.abspath(os.path.dirname(__file__))
app.config['SQLALCHEMY_DATABASE_URI'] = os.environ.get('DATABASE_URL', 'sqlite:///' + os.path.join(basedir, 'forum.db'))
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False

app.config['UPLOAD_FOLDER'] = os.path.join(basedir, 'uploads')
app.config['MAX_CONTENT_LENGTH'] = 16 * 1024 * 1024  #max 16 mb
ALLOWED_EXTENSIONS = {'txt', 'pdf', 'png', 'jpg', 'jpeg', 'gif', 'zip', 'doc', 'docx'}

os.makedirs(app.config['UPLOAD_FOLDER'], exist_ok=True)

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
    is_admin = db.Column(db.Boolean, default=False)
    is_active = db.Column(db.Boolean, default=True)  # Мягкое удаление
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
    is_deleted = db.Column(db.Boolean, default=False)  # Мягкое удаление
    replies = db.relationship('Reply', backref='topic', lazy=True, cascade='all, delete-orphan')
    attachments = db.relationship('Attachment', backref='topic', lazy=True, cascade='all, delete-orphan')
    
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
    attachments = db.relationship('Attachment', backref='reply', lazy=True, cascade='all, delete-orphan')

class Attachment(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    filename = db.Column(db.String(255), nullable=False)
    original_filename = db.Column(db.String(255), nullable=False)
    uploaded_at = db.Column(db.DateTime, default=datetime.utcnow)
    topic_id = db.Column(db.Integer, db.ForeignKey('topic.id'), nullable=True)
    reply_id = db.Column(db.Integer, db.ForeignKey('reply.id'), nullable=True)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)

def allowed_file(filename):
    return '.' in filename and \
           filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS

def is_admin():
    return current_user.is_authenticated and current_user.is_admin


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

    all_topics = Topic.query.filter_by(is_deleted=False)\
        .join(User).filter(User.is_active == True)\
        .order_by(Topic.created_at.desc()).paginate(
        page=page, per_page=per_page, error_out=False)
    
    return render_template('topics.html', topics=all_topics.items)

@app.route('/new_topic', methods=['GET', 'POST'])
@login_required
def new_topic():
    if request.method == 'POST':
        title = request.form.get('title')
        content = request.form.get('content')
        
        if title and content:
            new_topic = Topic(title=title, content=content, user_id=current_user.id)
            db.session.add(new_topic)
            db.session.flush() 
            
            if 'files' in request.files:
                files = request.files.getlist('files')
                for file in files:
                    if file and file.filename and allowed_file(file.filename):
                        filename = secure_filename(file.filename)
                        unique_filename = f"{datetime.now().timestamp()}_{filename}"
                        file_path = os.path.join(app.config['UPLOAD_FOLDER'], unique_filename)
                        file.save(file_path)
                        
                        attachment = Attachment(
                            filename=unique_filename,
                            original_filename=filename,
                            topic_id=new_topic.id,
                            user_id=current_user.id
                        )
                        db.session.add(attachment)
            
            db.session.commit()
            flash('Тема успешно создана!', 'success')
            return redirect(url_for('topic', topic_id=new_topic.id))
        else:
            flash('Заполните все поля', 'error')
    
    return render_template('new_topic.html')

@app.route('/profile/delete', methods=['GET', 'POST'])
@login_required
def delete_own_account():
    if request.method == 'POST':
        password = request.form.get('password')
        
        if current_user.check_password(password):
            # Мягкое удаление аккаунта
            current_user.is_active = False
            db.session.commit()
            
            logout_user()
            flash('Ваш аккаунт успешно удален', 'success')
            return redirect(url_for('index'))
        else:
            flash('Неверный пароль', 'error')
    
    return render_template('delete_account.html')

@app.route('/admin/delete_user/<int:user_id>', methods=['POST'])
@login_required
def admin_delete_user(user_id):
    if not is_admin():
        flash('Недостаточно прав', 'error')
        return redirect(url_for('index'))
    
    user = User.query.get_or_404(user_id)

    if user.id == current_user.id:
        flash('Нельзя удалить свой собственный аккаунт', 'error')
    elif user.is_admin:
        flash('Нельзя удалить другого администратора', 'error')
    else:
        user.is_active = False
        db.session.commit()
        flash(f'Аккаунт пользователя {user.username} удален', 'success')
    
    return redirect(url_for('admin_users'))

@app.route('/admin/restore_user/<int:user_id>', methods=['POST'])
@login_required
def admin_restore_user(user_id):
    if not is_admin():
        flash('Недостаточно прав', 'error')
        return redirect(url_for('index'))
    
    user = User.query.get_or_404(user_id)
    user.is_active = True
    db.session.commit()
    flash(f'Аккаунт пользователя {user.username} восстановлен', 'success')
    
    return redirect(url_for('admin_users'))

@app.route('/admin/users')
@login_required
def admin_users():
    if not is_admin():
        flash('Недостаточно прав', 'error')
        return redirect(url_for('index'))
    
    users = User.query.order_by(User.created_at.desc()).all()
    return render_template('admin_users.html', users=users)

@app.route('/reply/<int:topic_id>', methods=['POST'])
@login_required
def reply(topic_id):
    topic = Topic.query.get_or_404(topic_id)
    content = request.form.get('content')
    
    if content:
        new_reply = Reply(content=content, user_id=current_user.id, topic_id=topic_id)
        db.session.add(new_reply)
        db.session.flush()
        
        if 'files' in request.files:
            files = request.files.getlist('files')
            for file in files:
                if file and file.filename and allowed_file(file.filename):
                    filename = secure_filename(file.filename)
                    unique_filename = f"{datetime.now().timestamp()}_{filename}"
                    file_path = os.path.join(app.config['UPLOAD_FOLDER'], unique_filename)
                    file.save(file_path)
                    
                    attachment = Attachment(
                        filename=unique_filename,
                        original_filename=filename,
                        reply_id=new_reply.id,
                        user_id=current_user.id
                    )
                    db.session.add(attachment)
        
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

@app.route('/uploads/<filename>')
def uploaded_file(filename):
    return send_from_directory(app.config['UPLOAD_FOLDER'], filename)

@app.route('/admin/delete_topic/<int:topic_id>', methods=['POST'])
@login_required
def admin_delete_topic(topic_id):
    if not is_admin():
        flash('Недостаточно прав для выполнения этой операции', 'error')
        return redirect(url_for('index'))
    
    topic = Topic.query.get_or_404(topic_id)
    topic.is_deleted = True
    db.session.commit()
    
    flash('Тема успешно удалена', 'success')
    return redirect(url_for('topics'))

@app.route('/admin/restore_topic/<int:topic_id>', methods=['POST'])
@login_required
def admin_restore_topic(topic_id):
    if not is_admin():
        flash('Недостаточно прав для выполнения этой операции', 'error')
        return redirect(url_for('index'))
    
    topic = Topic.query.get_or_404(topic_id)
    topic.is_deleted = False
    db.session.commit()
    
    flash('Тема восстановлена', 'success')
    return redirect(url_for('topics'))

@app.route('/admin/topics')
@login_required
def admin_topics():
    if not is_admin():
        flash('Недостаточно прав для доступа к этой странице', 'error')
        return redirect(url_for('index'))
    
    deleted_topics = Topic.query.filter_by(is_deleted=True).all()
    return render_template('admin_topics.html', topics=deleted_topics)

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

start_keep_alive()

if __name__ == '__main__':

    with app.app_context():
        db.drop_all()
        db.create_all()

        test_admin = User(username=Curaga, email='admin@dash.com', is_admin=True)
        test_admin.set_password(PASSWORD_ADMIN)
        db.session.add(test_admin)

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


