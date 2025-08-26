from flask import Flask, render_template, request, redirect, url_for, flash, session
from datetime import datetime
import os
import uuid

app = Flask(__name__)
app.secret_key = 'y1234' 


users = []
topics = []
posts = []


def find_user(username):
    return next((u for u in users if u['username'] == username), None)

def find_topic(topic_id):
    return next((t for t in topics if t['id'] == topic_id), None)

def get_topic_posts(topic_id):
    return [p for p in posts if p['topic_id'] == topic_id]

@app.route('/')
def index():
    return render_template('index.html', topics=topics)

@app.route('/topic/<topic_id>')
def topic(topic_id):
    topic = find_topic(topic_id)
    if not topic:
        flash('Тема не найдена')
        return redirect(url_for('index'))
    
    topic_posts = get_topic_posts(topic_id)
    return render_template('topic.html', topic=topic, posts=topic_posts)

@app.route('/create_topic', methods=['GET', 'POST'])
def create_topic():
    if 'username' not in session:
        flash('Войдите, чтобы создать тему')
        return redirect(url_for('login'))
    
    if request.method == 'POST':
        title = request.form['title']
        content = request.form['content']
        
        new_topic = {
            'id': str(uuid.uuid4()),
            'title': title,
            'content': content,
            'author': session['username'],
            'created_at': datetime.now().strftime('%d.%m.%Y %H:%M')
        }
        
        topics.append(new_topic)
        flash('Тема создана успешно!')
        return redirect(url_for('index'))
    
    return render_template('create_topic.html')

@app.route('/add_post/<topic_id>', methods=['POST'])
def add_post(topic_id):
    if 'username' not in session:
        flash('Войдите, чтобы оставить сообщение')
        return redirect(url_for('login'))
    
    content = request.form['content']
    
    new_post = {
        'id': str(uuid.uuid4()),
        'content': content,
        'author': session['username'],
        'topic_id': topic_id,
        'created_at': datetime.now().strftime('%d.%m.%Y %H:%M')
    }
    
    posts.append(new_post)
    flash('Сообщение добавлено!')
    return redirect(url_for('topic', topic_id=topic_id))

@app.route('/register', methods=['GET', 'POST'])
def register():
    if request.method == 'POST':
        username = request.form['username']
        password = request.form['password']  # нужно хэшировать!
        
        if find_user(username):
            flash('Имя пользователя уже занято')
            return redirect(url_for('register'))
        
        users.append({
            'username': username,
            'password': password,  # not безопасно sql ataki
            'created_at': datetime.now()
        })
        
        flash('Регистрация успешна! Теперь войдите в систему.')
        return redirect(url_for('login'))
    
    return render_template('register.html')

@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        username = request.form['username']
        password = request.form['password']
        
        user = find_user(username)
        
        if user and user['password'] == password:  # sql atacki
            session['username'] = username
            return redirect(url_for('index'))
        else:
            flash('Неверное имя пользователя или пароль')
    
    return render_template('login.html')

@app.route('/logout')
def logout():
    session.pop('username', None)
    return redirect(url_for('index'))

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5000))
    app.run(host='0.0.0.0', port=port, debug=False)


