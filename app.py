import os
import json
import sqlite3
from datetime import datetime
from functools import wraps
from flask import Flask, render_template, request, jsonify, session, redirect, url_for
from werkzeug.security import generate_password_hash, check_password_hash

app = Flask(__name__)
app.config['SECRET_KEY'] = os.environ.get('SECRET_KEY', 'engelyurt-school2-math-secret-key-2026')

# Если подключен постоянный диск на Render — пишем туда, иначе локально
DATABASE = '/var/data/math_battle.db' if os.path.exists('/var/data') else 'math_battle.db'

def get_db():
    conn = sqlite3.connect(DATABASE)
    conn.row_factory = sqlite3.Row
    return conn

def init_db():
    with get_db() as conn:
        cursor = conn.cursor()
        
        # Классы
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS classes (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT UNIQUE NOT NULL,
                students_count INTEGER DEFAULT 25,
                bonus_points INTEGER DEFAULT 0
            )
        ''')

        # Зарегистрированные ученики
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS registered_students (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                student_name TEXT UNIQUE NOT NULL,
                class_name TEXT NOT NULL,
                phone_number TEXT NOT NULL,
                student_login TEXT UNIQUE NOT NULL,
                student_password TEXT NOT NULL,
                device_info TEXT NOT NULL,
                device_token TEXT NOT NULL,
                registered_at TEXT NOT NULL
            )
        ''')

        # Администраторы (Суперадмин и созданные им учителя)
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS users (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                username TEXT UNIQUE NOT NULL,
                password_hash TEXT NOT NULL,
                full_name TEXT NOT NULL,
                role TEXT NOT NULL DEFAULT 'teacher'
            )
        ''')

        # Вопросы
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS questions (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                author_id INTEGER,
                author_name TEXT,
                question_text TEXT NOT NULL,
                opt_a TEXT NOT NULL,
                opt_b TEXT NOT NULL,
                opt_c TEXT NOT NULL,
                opt_d TEXT NOT NULL,
                correct_idx INTEGER NOT NULL,
                points INTEGER DEFAULT 10,
                time_limit INTEGER DEFAULT 30,
                is_active INTEGER DEFAULT 1,
                FOREIGN KEY (author_id) REFERENCES users (id)
            )
        ''')

        # Ответы
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS submissions (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                student_name TEXT NOT NULL,
                class_name TEXT NOT NULL,
                question_id INTEGER NOT NULL,
                selected_idx INTEGER NOT NULL,
                is_correct INTEGER NOT NULL,
                points_earned INTEGER NOT NULL,
                time_taken INTEGER DEFAULT 0,
                submitted_at TEXT NOT NULL,
                FOREIGN KEY (question_id) REFERENCES questions (id)
            )
        ''')

        # Классы по умолчанию
        default_classes = [
            ("5-А", 24), ("5-Б", 23),
            ("6-А", 25), ("6-Б", 22),
            ("7-А", 26), ("7-Б", 25),
            ("8-А", 24), ("8-Б", 22),
            ("9-А", 22), ("9-Б", 25),
            ("10-А", 20), ("11-А", 18)
        ]
        for c_name, count in default_classes:
            cursor.execute("INSERT OR IGNORE INTO classes (name, students_count) VALUES (?, ?)", (c_name, count))

        # Создание или обновление пароля Суперадмина (superadmin / math2026)
        cursor.execute("SELECT id FROM users WHERE role = 'superadmin'")
        super_user = cursor.fetchone()
        hashed_pass = generate_password_hash("math2026")
        if not super_user:
            cursor.execute('''
                INSERT INTO users (username, password_hash, full_name, role)
                VALUES (?, ?, ?, ?)
            ''', ("superadmin", hashed_pass, "Главный Администратор", "superadmin"))
        else:
            cursor.execute("UPDATE users SET password_hash = ? WHERE username = 'superadmin'", (hashed_pass,))

        # Начальные вопросы
        cursor.execute("SELECT COUNT(*) FROM questions")
        if cursor.fetchone()[0] == 0:
            sample_questions = [
                (1, "Главный Администратор", "Чему равна сумма углов любого треугольника?", "90°", "180°", "360°", "270°", 1, 10, 25),
                (1, "Главный Администратор", "Какое число является наименьшим простым числом?", "0", "1", "2", "3", 2, 10, 20),
                (1, "Главный Администратор", "Вычислите: 2 + 2 × 2", "8", "6", "4", "10", 1, 10, 15),
                (1, "Главный Администратор", "Квадратный корень из 144 равен...", "11", "12", "14", "16", 1, 10, 20),
                (1, "Главный Администратор", "Сколько граней у стандартного куба?", "4", "6", "8", "12", 1, 10, 20)
            ]
            for q in sample_questions:
                cursor.execute('''
                    INSERT INTO questions (author_id, author_name, question_text, opt_a, opt_b, opt_c, opt_d, correct_idx, points, time_limit)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ''', q)

        conn.commit()

init_db()

# Декораторы прав
def login_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if 'user_id' not in session:
            return redirect(url_for('admin_login'))
        return f(*args, **kwargs)
    return decorated_function

def superadmin_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if session.get('role') != 'superadmin':
            return jsonify({"error": "Требуются права Главного Администратора"}), 403
        return f(*args, **kwargs)
    return decorated_function

# --- РОУТЫ ---
@app.route('/')
def index():
    return render_template('index.html')

@app.route('/api/classes')
def get_classes():
    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT id, name, students_count FROM classes ORDER BY name ASC")
        rows = [dict(r) for r in cursor.fetchall()]
    return jsonify(rows)

@app.route('/api/leaderboard')
def get_leaderboard():
    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT name, students_count, bonus_points FROM classes")
        classes = cursor.fetchall()
        
        cursor.execute('''
            SELECT class_name, SUM(points_earned) as total_pts, COUNT(DISTINCT student_name) as participants
            FROM submissions
            GROUP BY class_name
        ''')
        stats = {r['class_name']: r for r in cursor.fetchall()}
        
        result = []
        for c in classes:
            c_name = c['name']
            s_count = max(1, c['students_count'])
            st = stats.get(c_name, {'total_pts': 0, 'participants': 0})
            total = (st['total_pts'] or 0) + c['bonus_points']
            participants = st['participants'] or 0
            avg_score = round(total / s_count, 1)
            
            result.append({
                "class_name": c_name,
                "students_count": s_count,
                "total_points": total,
                "bonus_points": c['bonus_points'],
                "participants": participants,
                "avg_score": avg_score
            })
            
        result.sort(key=lambda x: x['avg_score'], reverse=True)
    return jsonify(result)

# ВХОД УЧЕНИКА В СВОЙ АККАУНТ (по логину и паролю)
@app.route('/api/student/login', methods=['POST'])
def student_login():
    data = request.json or {}
    s_login = data.get('login', '').strip().lower()
    s_password = data.get('password', '').strip()

    if not s_login or not s_password:
        return jsonify({"error": "Введите логин и пароль"}), 400

    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM registered_students WHERE LOWER(student_login) = LOWER(?)", (s_login,))
        user = cursor.fetchone()

        if not user:
            return jsonify({"error": "Ученик с таким логином не найден. Зарегистрируйтесь!"}), 404

        if user['student_password'].strip() != s_password:
            return jsonify({"error": "Неверный пароль!"}), 403

        return jsonify({
            "success": True,
            "student_name": user['student_name'],
            "class_name": user['class_name'],
            "phone_number": user['phone_number'],
            "student_login": user['student_login']
        })

# РЕГИСТРАЦИЯ НОВОГО УЧЕНИКА
@app.route('/api/student/register', methods=['POST'])
def student_register():
    data = request.json or {}
    s_name = " ".join(data.get('student_name', '').strip().split())
    c_name = data.get('class_name', '').strip()
    phone = data.get('phone_number', '').strip()
    s_login = data.get('student_login', '').strip().lower()
    s_password = data.get('student_password', '').strip()
    device_token = data.get('device_token', '').strip()
    device_info = data.get('device_info', '').strip() or request.headers.get('User-Agent', 'Смартфон')[:120]

    if not s_name or not c_name or not phone or not s_login or not s_password:
        return jsonify({"error": "Заполните все поля регистрации!"}), 400

    if len(s_name.split()) < 2:
        return jsonify({"error": "Введите и Фамилию, и Имя!"}), 400

    with get_db() as conn:
        cursor = conn.cursor()

        # Проверка логина
        cursor.execute("SELECT id FROM registered_students WHERE LOWER(student_login) = LOWER(?)", (s_login,))
        if cursor.fetchone():
            return jsonify({"error": "Этот логин уже занят другим учеником. Придумайте другой!"}), 400

        # Проверка ФИО
        cursor.execute("SELECT id FROM registered_students WHERE LOWER(student_name) = LOWER(?)", (s_name,))
        if cursor.fetchone():
            return jsonify({"error": "Ученик «" + s_name + "» уже зарегистрирован. Перейдите во вкладку «Войти»!"}), 400

        # Проверка номера телефона
        cursor.execute("SELECT id FROM registered_students WHERE phone_number = ?", (phone,))
        if cursor.fetchone():
            return jsonify({"error": "Этот номер телефона уже зарегистрирован в системе!"}), 400

        # Проверка одного устройства
        if device_token:
            cursor.execute("SELECT student_name FROM registered_students WHERE device_token = ?", (device_token,))
            owner = cursor.fetchone()
            if owner:
                return jsonify({"error": "С этого телефона уже играет «" + owner['student_name'] + "». Второй аккаунт запрещен!"}), 403

        now_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        cursor.execute('''
            INSERT INTO registered_students (student_name, class_name, phone_number, student_login, student_password, device_info, device_token, registered_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        ''', (s_name, c_name, phone, s_login, s_password, device_info, device_token, now_str))
        conn.commit()

        return jsonify({
            "success": True,
            "student_name": s_name,
            "class_name": c_name,
            "phone_number": phone,
            "student_login": s_login
        })

@app.route('/api/quiz/questions')
def get_quiz_questions():
    student_name = " ".join(request.args.get('student_name', '').strip().split())
    class_name = request.args.get('class_name', '').strip()
    
    if not student_name or not class_name:
        return jsonify({"error": "Укажите имя и класс"}), 400

    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute('''
            SELECT q.id, q.question_text, q.opt_a, q.opt_b, q.opt_c, q.opt_d, q.points, q.time_limit, q.author_name
            FROM questions q
            WHERE q.is_active = 1
              AND q.id NOT IN (
                  SELECT question_id FROM submissions
                  WHERE LOWER(student_name) = LOWER(?) AND class_name = ?
              )
            ORDER BY RANDOM()
        ''', (student_name, class_name))
        rows = [dict(r) for r in cursor.fetchall()]
    return jsonify(rows)

@app.route('/api/quiz/submit', methods=['POST'])
def submit_answer():
    data = request.json or {}
    student_name = " ".join(data.get('student_name', '').strip().split())
    class_name = data.get('class_name', '').strip()
    question_id = data.get('question_id')
    selected_idx = data.get('selected_idx')
    time_taken = data.get('time_taken', 0)

    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT id FROM submissions WHERE LOWER(student_name) = LOWER(?) AND class_name = ? AND question_id = ?",
                       (student_name, class_name, question_id))
        if cursor.fetchone():
            return jsonify({"error": "Вы уже отвечали на этот вопрос"}), 400

        cursor.execute("SELECT correct_idx, points FROM questions WHERE id = ?", (question_id,))
        q = cursor.fetchone()
        if not q:
            return jsonify({"error": "Вопрос не найден"}), 404

        is_correct = 1 if int(selected_idx) == int(q['correct_idx']) else 0
        points_earned = q['points'] if is_correct else 0
        now_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

        cursor.execute('''
            INSERT INTO submissions (student_name, class_name, question_id, selected_idx, is_correct, points_earned, time_taken, submitted_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        ''', (student_name, class_name, question_id, selected_idx, is_correct, points_earned, time_taken, now_str))
        conn.commit()

    return jsonify({
        "is_correct": bool(is_correct),
        "correct_idx": q['correct_idx'],
        "points_earned": points_earned
    })

# --- АДМИНКА СУПЕРАДМИНА ---
@app.route('/api/admin/login', methods=['POST'])
def admin_login():
    data = request.json or {}
    username = data.get('username', '').strip()
    password = data.get('password', '').strip()

    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM users WHERE username = ?", (username,))
        user = cursor.fetchone()

        if user and check_password_hash(user['password_hash'], password):
            session['user_id'] = user['id']
            session['username'] = user['username']
            session['full_name'] = user['full_name']
            session['role'] = user['role']
            return jsonify({
                "success": True,
                "user": {
                    "username": user['username'],
                    "full_name": user['full_name'],
                    "role": user['role']
                }
            })

    return jsonify({"error": "Неверный логин или пароль"}), 401

@app.route('/api/admin/logout', methods=['POST'])
def admin_logout():
    session.clear()
    return jsonify({"success": True})

@app.route('/api/admin/me')
def admin_me():
    if 'user_id' not in session:
        return jsonify({"authenticated": False})
    return jsonify({
        "authenticated": True,
        "user": {
            "username": session['username'],
            "full_name": session['full_name'],
            "role": session['role']
        }
    })

@app.route('/api/admin/classes', methods=['POST', 'PUT', 'DELETE'])
@login_required
@superadmin_required
def admin_manage_classes():
    with get_db() as conn:
        cursor = conn.cursor()
        if request.method == 'POST':
            d = request.json or {}
            c_name = d.get('name', '').strip()
            count = int(d.get('students_count', 25))
            try:
                cursor.execute("INSERT INTO classes (name, students_count) VALUES (?, ?)", (c_name, count))
                conn.commit()
                return jsonify({"success": True, "message": "Класс добавлен"})
            except sqlite3.IntegrityError:
                return jsonify({"error": "Такой класс уже есть"}), 400

        elif request.method == 'PUT':
            d = request.json or {}
            c_id = d.get('id')
            c_name = d.get('name', '').strip()
            count = int(d.get('students_count', 25))
            try:
                cursor.execute("SELECT name FROM classes WHERE id = ?", (c_id,))
                old_row = cursor.fetchone()
                if old_row:
                    old_name = old_row['name']
                    cursor.execute("UPDATE registered_students SET class_name = ? WHERE class_name = ?", (c_name, old_name))
                    cursor.execute("UPDATE submissions SET class_name = ? WHERE class_name = ?", (c_name, old_name))
                cursor.execute("UPDATE classes SET name = ?, students_count = ? WHERE id = ?", (c_name, count, c_id))
                conn.commit()
                return jsonify({"success": True, "message": "Класс обновлен"})
            except sqlite3.IntegrityError:
                return jsonify({"error": "Класс с таким именем уже существует"}), 400

        elif request.method == 'DELETE':
            c_id = request.args.get('id')
            cursor.execute("DELETE FROM classes WHERE id = ?", (c_id,))
            conn.commit()
            return jsonify({"success": True, "message": "Класс удален"})

@app.route('/api/admin/registered-students')
@login_required
@superadmin_required
def admin_registered_students():
    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute('''
            SELECT id, student_name, class_name, phone_number, student_login, student_password, device_info, registered_at 
            FROM registered_students 
            ORDER BY id DESC
        ''')
        return jsonify([dict(r) for r in cursor.fetchall()])

@app.route('/api/admin/questions', methods=['GET', 'POST', 'DELETE'])
@login_required
def admin_questions():
    with get_db() as conn:
        cursor = conn.cursor()
        if request.method == 'GET':
            cursor.execute("SELECT * FROM questions ORDER BY id DESC")
            return jsonify([dict(r) for r in cursor.fetchall()])
        elif request.method == 'POST':
            d = request.json or {}
            cursor.execute('''
                INSERT INTO questions (author_id, author_name, question_text, opt_a, opt_b, opt_c, opt_d, correct_idx, points, time_limit)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ''', (session['user_id'], session['full_name'], d.get('question_text'), d.get('opt_a'), d.get('opt_b'), d.get('opt_c'), d.get('opt_d'), int(d.get('correct_idx', 0)), int(d.get('points', 10)), int(d.get('time_limit', 30))))
            conn.commit()
            return jsonify({"success": True})
        elif request.method == 'DELETE':
            cursor.execute("DELETE FROM questions WHERE id = ?", (request.args.get('id'),))
            conn.commit()
            return jsonify({"success": True})

@app.route('/api/admin/submissions')
@login_required
def admin_submissions():
    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute('''
            SELECT s.*, q.question_text
            FROM submissions s
            JOIN questions q ON s.question_id = q.id
            ORDER BY s.id DESC LIMIT 300
        ''')
        return jsonify([dict(r) for r in cursor.fetchall()])

@app.route('/api/admin/users', methods=['GET', 'POST', 'DELETE'])
@login_required
@superadmin_required
def admin_users():
    with get_db() as conn:
        cursor = conn.cursor()
        if request.method == 'GET':
            cursor.execute("SELECT id, username, full_name, role FROM users ORDER BY id ASC")
            return jsonify([dict(r) for r in cursor.fetchall()])
        elif request.method == 'POST':
            d = request.json or {}
            hashed = generate_password_hash(d.get('password'))
            cursor.execute("INSERT INTO users (username, password_hash, full_name, role) VALUES (?, ?, ?, ?)",
                           (d.get('username'), hashed, d.get('full_name'), 'teacher'))
            conn.commit()
            return jsonify({"success": True})
        elif request.method == 'DELETE':
            cursor.execute("DELETE FROM users WHERE id = ? AND role != 'superadmin'", (request.args.get('id'),))
            conn.commit()
            return jsonify({"success": True})

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5000))
    app.run(host='0.0.0.0', port=port, debug=False)
