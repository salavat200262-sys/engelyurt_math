import os
import json
import sqlite3
from datetime import datetime
from functools import wraps
from flask import Flask, render_template, request, jsonify, session, redirect, url_for
from werkzeug.security import generate_password_hash, check_password_hash

app = Flask(__name__)
app.config['SECRET_KEY'] = os.environ.get('SECRET_KEY', 'engelyurt-school2-math-secret-key-2026')
DATABASE = 'math_battle.db'

def get_db():
    conn = sqlite3.connect(DATABASE)
    conn.row_factory = sqlite3.Row
    return conn

def init_db():
    with get_db() as conn:
        cursor = conn.cursor()
        
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS classes (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT UNIQUE NOT NULL,
                students_count INTEGER DEFAULT 25,
                bonus_points INTEGER DEFAULT 0
            )
        ''')

        cursor.execute('''
            CREATE TABLE IF NOT EXISTS registered_students (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                student_name TEXT UNIQUE NOT NULL,
                class_name TEXT NOT NULL,
                device_token TEXT,
                registered_at TEXT NOT NULL
            )
        ''')

        cursor.execute('''
            CREATE TABLE IF NOT EXISTS users (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                username TEXT UNIQUE NOT NULL,
                password_hash TEXT NOT NULL,
                full_name TEXT NOT NULL,
                role TEXT NOT NULL DEFAULT 'teacher'
            )
        ''')

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

        cursor.execute("SELECT id FROM users WHERE role = 'superadmin'")
        if not cursor.fetchone():
            default_super_pass = generate_password_hash("math2026")
            cursor.execute('''
                INSERT INTO users (username, password_hash, full_name, role)
                VALUES (?, ?, ?, ?)
            ''', ("superadmin", default_super_pass, "Главный Администратор", "superadmin"))

        cursor.execute("SELECT id FROM users WHERE username = 'teacher1'")
        if not cursor.fetchone():
            default_teacher_pass = generate_password_hash("teacher123")
            cursor.execute('''
                INSERT INTO users (username, password_hash, full_name, role)
                VALUES (?, ?, ?, ?)
            ''', ("teacher1", default_teacher_pass, "Учитель Математики", "teacher"))

        cursor.execute("SELECT COUNT(*) FROM questions")
        if cursor.fetchone()[0] == 0:
            sample_questions = [
                (1, "Главный Администратор", "Чему равна сумма углов любого выпуклого треугольника?", "90°", "180°", "360°", "270°", 1, 10, 25),
                (1, "Главный Администратор", "Какое число является наименьшим простым числом?", "0", "1", "2", "3", 2, 10, 20),
                (2, "Учитель Математики", "Вычислите значение выражения: 2 + 2 × 2", "8", "6", "4", "10", 1, 10, 15),
                (2, "Учитель Математики", "Квадратный корень из 144 равен...", "11", "12", "14", "16", 1, 10, 20),
                (2, "Учитель Математики", "Сколько граней у стандартного куба?", "4", "6", "8", "12", 1, 10, 20)
            ]
            for q in sample_questions:
                cursor.execute('''
                    INSERT INTO questions (author_id, author_name, question_text, opt_a, opt_b, opt_c, opt_d, correct_idx, points, time_limit)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ''', q)

        conn.commit()

init_db()

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

@app.route('/')
def index():
    return render_template('index.html')

@app.route('/api/classes')
# --- Полное управление классами: Добавление, Редактирование, Удаление ---
@app.route('/api/admin/classes', methods=['POST', 'PUT', 'DELETE'])
@login_required
@superadmin_required
def admin_manage_classes():
    with get_db() as conn:
        cursor = conn.cursor()
        
        # 1. Добавление нового класса
        if request.method == 'POST':
            d = request.json or {}
            c_name = d.get('name', '').strip()
            count = int(d.get('students_count', 25))
            if not c_name:
                return jsonify({"error": "Укажите название класса"}), 400
            try:
                cursor.execute("INSERT INTO classes (name, students_count) VALUES (?, ?)", (c_name, count))
                conn.commit()
                return jsonify({"success": True, "message": "Класс успешно добавлен"})
            except sqlite3.IntegrityError:
                return jsonify({"error": "Класс с таким названием уже существует"}), 400

        # 2. Редактирование существующего класса (название и число учеников)
        elif request.method == 'PUT':
            d = request.json or {}
            c_id = d.get('id')
            c_name = d.get('name', '').strip()
            count = int(d.get('students_count', 25))
            if not c_id or not c_name:
                return jsonify({"error": "Некорректные данные для редактирования"}), 400
            try:
                # Получаем старое имя класса, чтобы обновить записи в ответах
                cursor.execute("SELECT name FROM classes WHERE id = ?", (c_id,))
                old_row = cursor.fetchone()
                if old_row:
                    old_name = old_row['name']
                    cursor.execute("UPDATE registered_students SET class_name = ? WHERE class_name = ?", (c_name, old_name))
                    cursor.execute("UPDATE submissions SET class_name = ? WHERE class_name = ?", (c_name, old_name))

                cursor.execute("UPDATE classes SET name = ?, students_count = ? WHERE id = ?", (c_name, count, c_id))
                conn.commit()
                return jsonify({"success": True, "message": "Данные класса обновлены"})
            except sqlite3.IntegrityError:
                return jsonify({"error": "Класс с таким названием уже существует"}), 400

        # 3. Удаление класса
        elif request.method == 'DELETE':
            c_id = request.args.get('id')
            if not c_id:
                return jsonify({"error": "Не передан ID класса"}), 400
            cursor.execute("DELETE FROM classes WHERE id = ?", (c_id,))
            conn.commit()
            return jsonify({"success": True, "message": "Класс удален"})

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

@app.route('/api/student/check-or-register', methods=['POST'])
def check_or_register_student():
    data = request.json or {}
    s_name = " ".join(data.get('student_name', '').strip().split())
    c_name = data.get('class_name', '').strip()
    device_token = data.get('device_token', '').strip()

    if not s_name or not c_name:
        return jsonify({"error": "Укажите имя, фамилию и класс"}), 400

    parts = s_name.split()
    if len(parts) < 2:
        return jsonify({"error": "Пожалуйста, введите и Фамилию, и Имя!"}), 400

    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM registered_students WHERE LOWER(student_name) = LOWER(?)", (s_name,))
        existing = cursor.fetchone()

        if existing:
            if existing['class_name'] != c_name:
                return jsonify({
                    "error": f"Ученик «{s_name}» уже зарегистрирован за классом «{existing['class_name']}». Сменить класс нельзя!"
                }), 403
            
            if existing['device_token'] and device_token and existing['device_token'] != device_token:
                return jsonify({
                    "error": f"Аккаунт «{s_name}» привязан к другому устройству! Заходить можно только со своего телефона."
                }), 403

            return jsonify({
                "success": True,
                "student_name": existing['student_name'],
                "class_name": existing['class_name'],
                "is_new": False
            })

        if device_token:
            cursor.execute("SELECT * FROM registered_students WHERE device_token = ?", (device_token,))
            device_owner = cursor.fetchone()
            if device_owner:
                return jsonify({
                    "error": f"С этого устройства уже играет «{device_owner['student_name']}» ({device_owner['class_name']}). Второй аккаунт запрещен!"
                }), 403

        now_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        cursor.execute('''
            INSERT INTO registered_students (student_name, class_name, device_token, registered_at)
            VALUES (?, ?, ?, ?)
        ''', (s_name, c_name, device_token, now_str))
        conn.commit()

        return jsonify({
            "success": True,
            "student_name": s_name,
            "class_name": c_name,
            "is_new": True
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

    if not student_name or not class_name or question_id is None or selected_idx is None:
        return jsonify({"error": "Неполные данные"}), 400

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

@app.route('/api/admin/classes', methods=['POST', 'DELETE'])
@login_required
@superadmin_required
def admin_manage_classes():
    with get_db() as conn:
        cursor = conn.cursor()
        if request.method == 'POST':
            d = request.json or {}
            c_name = d.get('name', '').strip()
            count = int(d.get('students_count', 25))
            if not c_name:
                return jsonify({"error": "Укажите название класса"}), 400
            try:
                cursor.execute("INSERT INTO classes (name, students_count) VALUES (?, ?)", (c_name, count))
                conn.commit()
                return jsonify({"success": True})
            except sqlite3.IntegrityError:
                return jsonify({"error": "Класс с таким названием уже существует"}), 400
        elif request.method == 'DELETE':
            c_id = request.args.get('id')
            cursor.execute("DELETE FROM classes WHERE id = ?", (c_id,))
            conn.commit()
            return jsonify({"success": True})

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
            text = d.get('question_text', '').strip()
            opt_a = d.get('opt_a', '').strip()
            opt_b = d.get('opt_b', '').strip()
            opt_c = d.get('opt_c', '').strip()
            opt_d = d.get('opt_d', '').strip()
            correct = int(d.get('correct_idx', 0))
            points = int(d.get('points', 10))
            time_lim = int(d.get('time_limit', 30))

            if not text or not opt_a or not opt_b:
                return jsonify({"error": "Заполните текст вопроса и варианты"}), 400

            cursor.execute('''
                INSERT INTO questions (author_id, author_name, question_text, opt_a, opt_b, opt_c, opt_d, correct_idx, points, time_limit)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ''', (session['user_id'], session['full_name'], text, opt_a, opt_b, opt_c, opt_d, correct, points, time_lim))
            conn.commit()
            return jsonify({"success": True})

        elif request.method == 'DELETE':
            q_id = request.args.get('id')
            if session['role'] == 'superadmin':
                cursor.execute("DELETE FROM questions WHERE id = ?", (q_id,))
            else:
                cursor.execute("DELETE FROM questions WHERE id = ? AND author_id = ?", (q_id, session['user_id']))
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

@app.route('/api/admin/registered-students')
@login_required
def admin_registered_students():
    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM registered_students ORDER BY id DESC")
        return jsonify([dict(r) for r in cursor.fetchall()])

@app.route('/api/admin/users', methods=['GET', 'POST', 'DELETE'])
@login_required
@superadmin_
