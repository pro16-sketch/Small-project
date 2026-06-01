from flask import Flask, render_template, request, jsonify, session, redirect, url_for, flash
import sqlite3
from datetime import datetime
import os
import secrets
from werkzeug.security import generate_password_hash, check_password_hash
from functools import wraps
import base64
import json
from dotenv import load_dotenv
import google.generativeai as genai

# Load environment variables from .env file if it exists
load_dotenv()

# Configure Google Gemini API Key
gemini_key = os.getenv("GEMINI_API_KEY") or os.getenv("GOOGLE_API_KEY")
if gemini_key:
    genai.configure(api_key=gemini_key)


app = Flask(__name__)
app.secret_key = secrets.token_hex(16)
app.config['UPLOAD_FOLDER'] = 'static/uploads'

# Create upload folder if it doesn't exist
os.makedirs(app.config['UPLOAD_FOLDER'], exist_ok=True)

# ---------------- DATABASE SETUP ----------------
def get_db():
    conn = sqlite3.connect("database.db")
    conn.row_factory = sqlite3.Row
    return conn

def init_db():
    conn = get_db()
    cur = conn.cursor()
    
    # Users table
    cur.execute("""
        CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            username TEXT UNIQUE NOT NULL,
            password TEXT NOT NULL,
            email TEXT,
            role TEXT DEFAULT 'student',
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)
    
    # Exams table
    cur.execute("""
        CREATE TABLE IF NOT EXISTS exams (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            title TEXT NOT NULL,
            description TEXT,
            duration INTEGER NOT NULL,
            created_by INTEGER,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            is_active INTEGER DEFAULT 1,
            FOREIGN KEY (created_by) REFERENCES users (id)
        )
    """)
    
    # Questions table
    cur.execute("""
        CREATE TABLE IF NOT EXISTS questions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            exam_id INTEGER,
            question_text TEXT NOT NULL,
            option_a TEXT,
            option_b TEXT,
            option_c TEXT,
            option_d TEXT,
            correct_answer TEXT,
            points INTEGER DEFAULT 1,
            negative_marks REAL DEFAULT 0,
            FOREIGN KEY (exam_id) REFERENCES exams (id)
        )
    """)
    
    # Add negative_marks column if it doesn't exist (migration)
    try:
        cur.execute("ALTER TABLE questions ADD COLUMN negative_marks REAL DEFAULT 0")
    except sqlite3.OperationalError:
        pass  # Column already exists
    
    # Exam sessions table
    cur.execute("""
        CREATE TABLE IF NOT EXISTS exam_sessions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            exam_id INTEGER,
            user_id INTEGER,
            start_time TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            end_time TIMESTAMP,
            status TEXT DEFAULT 'in_progress',
            score INTEGER,
            FOREIGN KEY (exam_id) REFERENCES exams (id),
            FOREIGN KEY (user_id) REFERENCES users (id)
        )
    """)
    
    # Answers table
    cur.execute("""
        CREATE TABLE IF NOT EXISTS answers (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            session_id INTEGER,
            question_id INTEGER,
            answer TEXT,
            is_correct INTEGER,
            FOREIGN KEY (session_id) REFERENCES exam_sessions (id),
            FOREIGN KEY (question_id) REFERENCES questions (id)
        )
    """)
    
    # Violations table
    cur.execute("""
        CREATE TABLE IF NOT EXISTS violations (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            session_id INTEGER,
            type TEXT,
            description TEXT,
            timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            severity TEXT DEFAULT 'medium',
            FOREIGN KEY (session_id) REFERENCES exam_sessions (id)
        )
    """)
    
    # Proctoring snapshots table
    cur.execute("""
        CREATE TABLE IF NOT EXISTS snapshots (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            session_id INTEGER,
            image_path TEXT,
            timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            face_detected INTEGER DEFAULT 0,
            multiple_faces INTEGER DEFAULT 0,
            FOREIGN KEY (session_id) REFERENCES exam_sessions (id)
        )
    """)
    
    # Create default admin account
    try:
        cur.execute("INSERT INTO users (username, password, email, role) VALUES (?, ?, ?, ?)",
                   ('admin', generate_password_hash('admin123'), 'admin@exam.com', 'admin'))
    except sqlite3.IntegrityError:
        pass  # Admin already exists
    
    conn.commit()
    conn.close()

init_db()

# ---------------- AUTHENTICATION DECORATORS ----------------
def login_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if 'user_id' not in session:
            flash('Please login first', 'error')
            return redirect(url_for('login'))
        return f(*args, **kwargs)
    return decorated_function

def admin_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if 'user_id' not in session or session.get('role') != 'admin':
            flash('Admin access required', 'error')
            return redirect(url_for('login'))
        return f(*args, **kwargs)
    return decorated_function

# ---------------- AUTHENTICATION ROUTES ----------------
@app.route("/")
def home():
    if 'user_id' in session:
        if session.get('role') == 'admin':
            return redirect(url_for('admin_dashboard'))
        else:
            return redirect(url_for('student_dashboard'))
    return redirect(url_for('login'))

@app.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        username = request.form.get('username')
        password = request.form.get('password')
        
        conn = get_db()
        user = conn.execute("SELECT * FROM users WHERE username = ?", (username,)).fetchone()
        conn.close()
        
        if user and check_password_hash(user['password'], password):
            session['user_id'] = user['id']
            session['username'] = user['username']
            session['role'] = user['role']
            flash('Login successful!', 'success')
            
            if user['role'] == 'admin':
                return redirect(url_for('admin_dashboard'))
            else:
                return redirect(url_for('student_dashboard'))
        else:
            flash('Invalid credentials', 'error')
    
    return render_template("login.html")

@app.route("/register", methods=["GET", "POST"])
def register():
    if request.method == "POST":
        username = request.form.get('username')
        password = request.form.get('password')
        email = request.form.get('email')
        
        conn = get_db()
        try:
            conn.execute("INSERT INTO users (username, password, email, role) VALUES (?, ?, ?, ?)",
                        (username, generate_password_hash(password), email, 'student'))
            conn.commit()
            flash('Registration successful! Please login.', 'success')
            return redirect(url_for('login'))
        except sqlite3.IntegrityError:
            flash('Username already exists', 'error')
        finally:
            conn.close()
    
    return render_template("register.html")

@app.route("/logout")
def logout():
    session.clear()
    flash('Logged out successfully', 'success')
    return redirect(url_for('login'))

# ---------------- ADMIN ROUTES ----------------
@app.route("/admin/dashboard")
@admin_required
def admin_dashboard():
    conn = get_db()
    
    # Get statistics
    total_students = conn.execute("SELECT COUNT(*) as count FROM users WHERE role='student'").fetchone()['count']
    total_exams = conn.execute("SELECT COUNT(*) as count FROM exams").fetchone()['count']
    active_sessions = conn.execute("SELECT COUNT(*) as count FROM exam_sessions WHERE status='in_progress'").fetchone()['count']
    total_violations = conn.execute("SELECT COUNT(*) as count FROM violations").fetchone()['count']
    completed_sessions = conn.execute("SELECT COUNT(*) as count FROM exam_sessions WHERE status='completed'").fetchone()['count']
    banned_sessions = conn.execute("SELECT COUNT(*) as count FROM exam_sessions WHERE status='banned'").fetchone()['count']
    
    # Get students who participated (taken at least one exam)
    students_participated = conn.execute("""
        SELECT COUNT(DISTINCT user_id) as count 
        FROM exam_sessions 
        WHERE status='completed'
    """).fetchone()['count']
    
    # Get exam completion statistics for bar chart
    exam_stats = conn.execute("""
        SELECT e.title, COUNT(es.id) as attempts, 
               COUNT(DISTINCT es.user_id) as unique_students,
               COALESCE(AVG(es.score), 0) as avg_score
        FROM exams e
        LEFT JOIN exam_sessions es ON e.id = es.exam_id AND es.status = 'completed'
        GROUP BY e.id, e.title
        ORDER BY attempts DESC
        LIMIT 10
    """).fetchall()
    
    # Get student participation stats (how many students took each exam)
    student_participation = conn.execute("""
        SELECT e.title, COUNT(DISTINCT es.user_id) as student_count
        FROM exams e
        LEFT JOIN exam_sessions es ON e.id = es.exam_id AND es.status = 'completed'
        GROUP BY e.id, e.title
        ORDER BY student_count DESC
        LIMIT 10
    """).fetchall()
    
    # Get violation types for pie chart
    violation_stats = conn.execute("""
        SELECT type, COUNT(*) as count
        FROM violations
        GROUP BY type
        ORDER BY count DESC
    """).fetchall()
    
    # Get session status distribution for pie chart
    session_stats = conn.execute("""
        SELECT status, COUNT(*) as count
        FROM exam_sessions
        GROUP BY status
    """).fetchall()
    
    # Get recent exams
    exams = conn.execute("""
        SELECT e.*, u.username as creator 
        FROM exams e 
        JOIN users u ON e.created_by = u.id 
        ORDER BY e.created_at DESC 
        LIMIT 10
    """).fetchall()
    
    conn.close()
    
    return render_template("admin_dashboard.html", 
                          total_students=total_students,
                          students_participated=students_participated,
                          total_exams=total_exams,
                          active_sessions=active_sessions,
                          total_violations=total_violations,
                          completed_sessions=completed_sessions,
                          banned_sessions=banned_sessions,
                          exams=exams,
                          exam_stats=exam_stats,
                          student_participation=student_participation,
                          violation_stats=violation_stats,
                          session_stats=session_stats)

@app.route("/admin/create_exam", methods=["GET", "POST"])
@admin_required
def create_exam():
    if request.method == "POST":
        title = request.form.get('title')
        description = request.form.get('description')
        duration = request.form.get('duration')
        
        conn = get_db()
        cur = conn.cursor()
        cur.execute("INSERT INTO exams (title, description, duration, created_by) VALUES (?, ?, ?, ?)",
                   (title, description, duration, session['user_id']))
        exam_id = cur.lastrowid
        conn.commit()
        conn.close()
        
        flash('Exam created successfully!', 'success')
        return redirect(url_for('add_questions', exam_id=exam_id))
    
    return render_template("create_exam.html")

@app.route("/admin/exam/<int:exam_id>/add_questions", methods=["GET", "POST"])
@admin_required
def add_questions(exam_id):
    if request.method == "POST":
        question_text = request.form.get('question_text')
        option_a = request.form.get('option_a')
        option_b = request.form.get('option_b')
        option_c = request.form.get('option_c')
        option_d = request.form.get('option_d')
        correct_answer = request.form.get('correct_answer')
        points = request.form.get('points', 1)
        negative_marks = request.form.get('negative_marks', 0)
        
        conn = get_db()
        conn.execute("""
            INSERT INTO questions (exam_id, question_text, option_a, option_b, option_c, option_d, correct_answer, points, negative_marks)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (exam_id, question_text, option_a, option_b, option_c, option_d, correct_answer, points, negative_marks))
        conn.commit()
        conn.close()
        
        flash('Question added successfully!', 'success')
        
        if request.form.get('add_more'):
            return redirect(url_for('add_questions', exam_id=exam_id))
        else:
            return redirect(url_for('admin_dashboard'))
    
    conn = get_db()
    exam = conn.execute("SELECT * FROM exams WHERE id = ?", (exam_id,)).fetchone()
    questions = conn.execute("SELECT * FROM questions WHERE exam_id = ?", (exam_id,)).fetchall()
    conn.close()
    
    return render_template("add_questions.html", exam=exam, questions=questions)


@app.route("/admin/exam/<int:exam_id>/generate_questions", methods=["POST"]) 
@admin_required
def generate_questions_ai(exam_id):
    try:
        # Check if API key is configured
        if not (os.getenv("GEMINI_API_KEY") or os.getenv("GOOGLE_API_KEY")):
            return jsonify({
                "error": "Gemini API key is not configured",
                "hint": "Please add your GEMINI_API_KEY in the environment or inside a .env file."
            }), 500

        payload = request.get_json(silent=True) or {}
        topic = (payload.get("topic") or "general knowledge").strip()
        num_questions = int(payload.get("num_questions") or 3)
        num_questions = max(1, min(num_questions, 10))
        model_name = os.getenv("GEMINI_MODEL", "gemini-1.5-flash")

        schema_hint = {
            "questions": [
                {
                    "question_text": "string",
                    "option_a": "string",
                    "option_b": "string",
                    "option_c": "string",
                    "option_d": "string",
                    "correct_answer": "A|B|C|D",
                    "points": 1,
                    "negative_marks": 0
                }
            ]
        }

        prompt = (
            f"Create {num_questions} multiple-choice questions about '{topic}'. "
            "Each must have 4 options (A-D) and exactly one correct answer. "
            "Return strictly as JSON matching this schema without extra text: "
            f"{json.dumps(schema_hint)}."
        )

        # Ask Gemini to return JSON-formatted output
        model = genai.GenerativeModel(model_name)
        response = model.generate_content(
            prompt,
            generation_config={"response_mime_type": "application/json"}
        )
        content = response.text or "{}"
        data = json.loads(content)
        questions = data.get("questions", [])

        if not isinstance(questions, list) or not questions:
            return jsonify({"error": "AI returned no questions"}), 400

        conn = get_db()
        inserted = 0
        for q in questions:
            try:
                conn.execute(
                    """
                    INSERT INTO questions (exam_id, question_text, option_a, option_b, option_c, option_d, correct_answer, points, negative_marks)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        exam_id,
                        q.get("question_text", "").strip(),
                        q.get("option_a", "").strip(),
                        q.get("option_b", "").strip(),
                        q.get("option_c", "").strip(),
                        q.get("option_d", "").strip(),
                        (q.get("correct_answer") or "").strip()[:1].upper(),
                        int(q.get("points", 1) or 1),
                        float(q.get("negative_marks", 0) or 0.0),
                    ),
                )
                inserted += 1
            except Exception:
                # Skip malformed entries
                pass
        conn.commit()
        conn.close()

        return jsonify({"status": "ok", "inserted": inserted})
    except json.JSONDecodeError:
        return jsonify({"error": "Failed to parse AI response. Try again."}), 500
    except Exception as e:
        return jsonify({
            "error": "AI generation failed",
            "details": str(e),
            "hint": "Ensure GEMINI_API_KEY is configured in the environment or a .env file, and you have internet access."
        }), 500


@app.route("/admin/violations")
@admin_required
def view_violations():
    conn = get_db()
    violations = conn.execute("""
        SELECT v.*, u.username, e.title as exam_title, es.start_time
        FROM violations v
        JOIN exam_sessions es ON v.session_id = es.id
        JOIN users u ON es.user_id = u.id
        JOIN exams e ON es.exam_id = e.id
        ORDER BY v.timestamp DESC
    """).fetchall()
    conn.close()
    
    return render_template("violations.html", violations=violations)

@app.route("/admin/session/<int:session_id>")
@admin_required
def view_session_details(session_id):
    conn = get_db()
    
    session_data = conn.execute("""
        SELECT es.*, u.username, e.title as exam_title
        FROM exam_sessions es
        JOIN users u ON es.user_id = u.id
        JOIN exams e ON es.exam_id = e.id
        WHERE es.id = ?
    """, (session_id,)).fetchone()
    
    violations = conn.execute("""
        SELECT * FROM violations 
        WHERE session_id = ? 
        ORDER BY timestamp
    """, (session_id,)).fetchall()
    
    snapshots = conn.execute("""
        SELECT * FROM snapshots 
        WHERE session_id = ? 
        ORDER BY timestamp
    """, (session_id,)).fetchall()
    
    answers = conn.execute("""
        SELECT a.*, q.question_text, q.correct_answer
        FROM answers a
        JOIN questions q ON a.question_id = q.id
        WHERE a.session_id = ?
    """, (session_id,)).fetchall()
    
    conn.close()
    
    return render_template("session_details.html", 
                          session=session_data, 
                          violations=violations,
                          snapshots=snapshots,
                          answers=answers)

# ---------------- STUDENT ROUTES ----------------
@app.route("/student/dashboard")
@login_required
def student_dashboard():
    conn = get_db()
    
    # Get available exams
    available_exams = conn.execute("""
        SELECT e.* FROM exams e
        WHERE e.is_active = 1
        AND e.id NOT IN (
            SELECT exam_id FROM exam_sessions 
            WHERE user_id = ? AND (status = 'completed' OR status = 'banned')
        )
    """, (session['user_id'],)).fetchall()
    
    # Get completed exams
    completed_exams_raw = conn.execute("""
        SELECT e.*, es.score, es.start_time, es.end_time
        FROM exams e
        JOIN exam_sessions es ON e.id = es.exam_id
        WHERE es.user_id = ? AND es.status = 'completed'
        ORDER BY es.end_time DESC
    """, (session['user_id'],)).fetchall()
    
    # Calculate duration for each completed exam
    completed_exams = []
    for exam in completed_exams_raw:
        exam_dict = dict(exam)
        if exam['start_time'] and exam['end_time']:
            try:
                start = datetime.strptime(exam['start_time'], '%Y-%m-%d %H:%M:%S')
                end = datetime.strptime(exam['end_time'], '%Y-%m-%d %H:%M:%S')
                duration_seconds = (end - start).total_seconds()
                exam_dict['duration_minutes'] = int(duration_seconds / 60)
            except:
                exam_dict['duration_minutes'] = 0
        else:
            exam_dict['duration_minutes'] = 0
        completed_exams.append(exam_dict)
    
    # Get banned exams
    banned_exams = conn.execute("""
        SELECT e.*, es.start_time
        FROM exams e
        JOIN exam_sessions es ON e.id = es.exam_id
        WHERE es.user_id = ? AND es.status = 'banned'
        ORDER BY es.start_time DESC
    """, (session['user_id'],)).fetchall()
    
    conn.close()
    
    return render_template("student_dashboard.html", 
                          available_exams=available_exams,
                          completed_exams=completed_exams,
                          banned_exams=banned_exams)

@app.route("/exam/<int:exam_id>/start")
@login_required
def start_exam(exam_id):
    conn = get_db()
    
    # Check if student was previously banned from this exam
    banned_session = conn.execute("""
        SELECT * FROM exam_sessions 
        WHERE exam_id = ? AND user_id = ? AND status = 'banned'
    """, (exam_id, session['user_id'])).fetchone()
    
    if banned_session:
        flash('You have been permanently banned from this exam due to excessive violations in a previous attempt', 'error')
        conn.close()
        return redirect(url_for('student_dashboard'))
    
    # Check if already completed
    existing = conn.execute("""
        SELECT * FROM exam_sessions 
        WHERE exam_id = ? AND user_id = ? AND status = 'completed'
    """, (exam_id, session['user_id'])).fetchone()
    
    if existing:
        flash('You have already completed this exam', 'error')
        conn.close()
        return redirect(url_for('student_dashboard'))
    
    # Create new session
    cur = conn.cursor()
    cur.execute("""
        INSERT INTO exam_sessions (exam_id, user_id, status)
        VALUES (?, ?, 'in_progress')
    """, (exam_id, session['user_id']))
    session_id = cur.lastrowid
    conn.commit()
    conn.close()
    
    return redirect(url_for('take_exam', session_id=session_id))

@app.route("/exam/session/<int:session_id>")
@login_required
def take_exam(session_id):
    conn = get_db()
    
    # Verify session belongs to user
    exam_session = conn.execute("""
        SELECT es.*, e.title, e.description, e.duration
        FROM exam_sessions es
        JOIN exams e ON es.exam_id = e.id
        WHERE es.id = ? AND es.user_id = ?
    """, (session_id, session['user_id'])).fetchone()
    
    if not exam_session:
        flash('Invalid exam session', 'error')
        conn.close()
        return redirect(url_for('student_dashboard'))
    
    if exam_session['status'] == 'completed':
        flash('This exam has already been completed', 'error')
        conn.close()
        return redirect(url_for('student_dashboard'))
    
    if exam_session['status'] == 'banned':
        flash('You have been banned from this exam due to excessive violations', 'error')
        conn.close()
        return redirect(url_for('student_dashboard'))
    
    # Get questions
    questions = conn.execute("""
        SELECT * FROM questions WHERE exam_id = ?
    """, (exam_session['exam_id'],)).fetchall()
    
    conn.close()
    
    # Convert to dict for easier template access
    exam_session_dict = dict(exam_session)
    
    return render_template("take_exam.html", 
                          exam_session=exam_session_dict, 
                          questions=questions)

@app.route("/exam/submit/<int:session_id>", methods=["POST"])
@login_required
def submit_exam(session_id):
    conn = get_db()
    
    # Verify session
    exam_session = conn.execute("""
        SELECT * FROM exam_sessions 
        WHERE id = ? AND user_id = ?
    """, (session_id, session['user_id'])).fetchone()
    
    if not exam_session:
        conn.close()
        return jsonify({"error": "Invalid session"}), 403
    
    # Get answers from request
    data = request.json
    answers = data.get('answers', {})
    
    # Get questions with correct answers
    questions = conn.execute("""
        SELECT * FROM questions WHERE exam_id = ?
    """, (exam_session['exam_id'],)).fetchall()
    
    total_score = 0
    max_score = 0
    
    # Process each answer
    for question in questions:
        max_score += question['points']
        student_answer = answers.get(str(question['id']), '')
        is_correct = (student_answer == question['correct_answer'])
        
        if is_correct:
            total_score += question['points']
        elif student_answer:  # If answered but wrong, apply negative marking
            total_score -= question['negative_marks']
        
        conn.execute("""
            INSERT INTO answers (session_id, question_id, answer, is_correct)
            VALUES (?, ?, ?, ?)
        """, (session_id, question['id'], student_answer, 1 if is_correct else 0))
    
    # Update session
    conn.execute("""
        UPDATE exam_sessions 
        SET end_time = CURRENT_TIMESTAMP, status = 'completed', score = ?
        WHERE id = ?
    """, (total_score, session_id))
    
    conn.commit()
    conn.close()
    
    return jsonify({
        "status": "success",
        "score": total_score,
        "max_score": max_score
    })

# ---------------- PROCTORING API ROUTES ----------------
@app.route("/log_violation", methods=["POST"])
@login_required
def log_violation():
    data = request.json
    session_id = data.get('session_id')
    v_type = data.get('type')
    description = data.get('description', '')
    severity = data.get('severity', 'medium')
    
    conn = get_db()
    
    # Log the violation
    conn.execute("""
        INSERT INTO violations (session_id, type, description, severity)
        VALUES (?, ?, ?, ?)
    """, (session_id, v_type, description, severity))
    conn.commit()
    
    # Check total violations for this session
    violation_count = conn.execute("""
        SELECT COUNT(*) as count FROM violations WHERE session_id = ?
    """, (session_id,)).fetchone()['count']
    
    banned = False
    # If violations exceed 20, ban the student from the exam
    if violation_count > 20:
        conn.execute("""
            UPDATE exam_sessions 
            SET status = 'banned', end_time = CURRENT_TIMESTAMP
            WHERE id = ?
        """, (session_id,))
        conn.commit()
        banned = True
    
    conn.close()
    
    return jsonify({"status": "logged", "violation_count": violation_count, "banned": banned})

@app.route("/analyze_face", methods=["POST"])
@login_required
def analyze_face():
    """Use Gemini vision to detect faces in real-time"""
    try:
        # Check if API key is configured
        if not (os.getenv("GEMINI_API_KEY") or os.getenv("GOOGLE_API_KEY")):
            return jsonify({
                "error": "Gemini API key is not configured",
                "hint": "Please add your GEMINI_API_KEY in the environment or inside a .env file."
            }), 500

        data = request.json
        image_data = data.get('image', '')
        
        if not image_data:
            return jsonify({"error": "No image provided"}), 400
        
        # Extract base64 image data and MIME type
        mime_type = "image/jpeg"
        if ',' in image_data:
            header, base64_str = image_data.split(',', 1)
            if 'image/' in header:
                parts = header.split(';')
                if parts:
                    mime_type = parts[0].replace('data:', '')
            image_data = base64_str
        
        image_bytes = base64.b64decode(image_data)
        image_part = {
            "mime_type": mime_type,
            "data": image_bytes
        }
        
        # Use Gemini vision model to analyze the image
        model_name = os.getenv("GEMINI_VISION_MODEL", "gemini-1.5-flash")
        
        prompt = (
            "Analyze this image and count the number of human faces visible. "
            "Respond ONLY with a JSON object in this exact format: "
            '{"face_count": <number>, "description": "<brief description>"}. '
            "Be accurate - if you see 0 faces, say 0. If you see 1 face, say 1. If you see 2 or more, say the exact number."
        )
        
        # Call Gemini with vision
        model = genai.GenerativeModel(model_name)
        response = model.generate_content(
            [prompt, image_part],
            generation_config={"response_mime_type": "application/json"}
        )
        
        response_text = response.text or '{}'
        analysis = json.loads(response_text)
        
        face_count = int(analysis.get('face_count', 0))
        description = analysis.get('description', '')
        
        return jsonify({
            "face_count": face_count,
            "description": description,
            "no_face": face_count == 0,
            "multiple_faces": face_count > 1
        })
        
    except json.JSONDecodeError:
        return jsonify({"error": "Failed to parse AI response"}), 500
    except Exception as e:
        return jsonify({
            "error": "Face detection failed",
            "details": str(e),
            "hint": "Ensure GEMINI_API_KEY is configured in the environment or a .env file, and you have internet access."
        }) , 500

@app.route("/save_snapshot", methods=["POST"])
@login_required
def save_snapshot():
    data = request.json
    session_id = data.get('session_id')
    image_data = data.get('image')
    face_detected = data.get('face_detected', 0)
    multiple_faces = data.get('multiple_faces', 0)
    
    # Decode base64 image
    image_data = image_data.split(',')[1]
    image_bytes = base64.b64decode(image_data)
    
    # Save image
    filename = f"snapshot_{session_id}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.jpg"
    filepath = os.path.join(app.config['UPLOAD_FOLDER'], filename)
    
    with open(filepath, 'wb') as f:
        f.write(image_bytes)
    
    # Save to database
    conn = get_db()
    conn.execute("""
        INSERT INTO snapshots (session_id, image_path, face_detected, multiple_faces)
        VALUES (?, ?, ?, ?)
    """, (session_id, filename, face_detected, multiple_faces))
    conn.commit()
    conn.close()
    
    return jsonify({"status": "saved"})

if __name__ == "__main__":
    app.run(debug=True)
