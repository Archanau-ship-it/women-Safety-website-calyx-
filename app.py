from flask import Flask, render_template, request, redirect, url_for, session, flash, jsonify
from werkzeug.security import generate_password_hash, check_password_hash
import sqlite3
import os
from datetime import datetime
import json

app = Flask(__name__)
app.secret_key = 'calyx_secret_key_2026_change_in_production'

UPLOAD_FOLDER = 'static/uploads'
app.config['UPLOAD_FOLDER'] = UPLOAD_FOLDER
os.makedirs(UPLOAD_FOLDER, exist_ok=True)
app.config['MAX_CONTENT_LENGTH'] = 50 * 1024 * 1024  # 50MB


def get_db():
    """Get a database connection with optimized settings."""
    conn = sqlite3.connect('database.db', timeout=20)
    conn.execute("PRAGMA journal_mode=WAL")   # prevents locking
    conn.execute("PRAGMA synchronous=NORMAL")
    conn.row_factory = sqlite3.Row
    return conn


def init_db():
    with get_db() as conn:
        conn.execute('''CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            email TEXT UNIQUE NOT NULL,
            phone TEXT NOT NULL,
            emergency_phones TEXT NOT NULL,
            password TEXT NOT NULL,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )''')
        conn.execute('''CREATE TABLE IF NOT EXISTS reports (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER,
            description TEXT NOT NULL,
            location TEXT NOT NULL,
            latitude REAL,
            longitude REAL,
            evidence_files TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (user_id) REFERENCES users (id)
        )''')
        conn.commit()


@app.route('/', methods=['GET', 'POST'])
def login():
    if 'user_id' in session:
        return redirect(url_for('dashboard'))

    if request.method == 'POST':
        username = request.form['username']
        password = request.form['password']

        with get_db() as conn:
            user = conn.execute(
                "SELECT * FROM users WHERE email = ? OR name = ?",
                (username, username)
            ).fetchone()

        if user and check_password_hash(user["password"], password):
            session["user_id"] = user["id"]
            session["user_name"] = user["name"]
            session["emergency_phones"] = json.loads(user["emergency_phones"])
            return redirect(url_for("dashboard"))
        elif not user:
            flash("No account found. Please register first.", "error")
            return redirect(url_for("register"))
        else:
            flash("Wrong password. Please try again.", "error")

    return render_template('index.html')


@app.route('/register', methods=['GET', 'POST'])
def register():
    if request.method == 'POST':
        name = request.form['name']
        email = request.form['email']
        password = generate_password_hash(request.form['password'])

        emergency_phones = []
        for i in range(1, 6):
            phone_key = f'emergency_phone_{i}'
            if phone_key in request.form and request.form[phone_key].strip():
                emergency_phones.append(request.form[phone_key].strip())

        if not emergency_phones:
            flash('At least one emergency phone is required', 'error')
            return render_template('register.html')

        try:
            with get_db() as conn:
                conn.execute(
                    "INSERT INTO users (name, email, phone, emergency_phones, password) VALUES (?, ?, ?, ?, ?)",
                    (name, email, emergency_phones[0], json.dumps(emergency_phones), password)
                )
                conn.commit()
            flash('Registration successful! Please login.', 'success')
            return redirect(url_for('login'))
        except sqlite3.IntegrityError:
            flash('Email already exists', 'error')

    return render_template('register.html')


@app.route('/dashboard')
def dashboard():
    if 'user_id' not in session:
        return redirect(url_for('login'))
    return render_template('dashboard.html')


@app.route('/report')
def report():
    if 'user_id' not in session:
        return redirect(url_for('login'))
    return render_template('report.html')


@app.route('/sos', methods=['POST'])
def sos():
    if 'user_id' not in session:
        return jsonify({'error': 'Unauthorized'}), 401

    data = request.json
    user_id = session['user_id']
    emergency_phones = session.get('emergency_phones', [])

    with get_db() as conn:
        cursor = conn.execute(
            "INSERT INTO reports (user_id, description, location, latitude, longitude) VALUES (?, ?, ?, ?, ?)",
            (user_id, "🚨 SOS EMERGENCY ALERT", data.get('location', 'Unknown'),
             data.get('lat'), data.get('lng'))
        )
        report_id = cursor.lastrowid
        conn.commit()

    print(f"🚨 SOS TRIGGERED by User ID: {user_id}")
    print(f"📍 Location: {data.get('lat')}, {data.get('lng')}")
    print(f"📱 Emergency contacts: {emergency_phones}")

    return jsonify({
        'status': 'success',
        'message': f'SOS sent to {len(emergency_phones)} contacts',
        'report_id': report_id
    })


@app.route('/submit_report', methods=['POST'])
def submit_report():
    if 'user_id' not in session:
        return jsonify({'error': 'Unauthorized'}), 401

    description = request.form.get('description', '')
    location = request.form.get('location', 'Unknown')
    lat = request.form.get('latitude')
    lng = request.form.get('longitude')

    evidence_files = []
    for file in request.files.getlist('evidence'):
        if file and file.filename:
            filename = f"{datetime.now().strftime('%Y%m%d_%H%M%S')}_{file.filename}"
            filepath = os.path.join(app.config['UPLOAD_FOLDER'], filename)
            file.save(filepath)
            evidence_files.append(filename)

    with get_db() as conn:
        conn.execute(
            "INSERT INTO reports (user_id, description, location, latitude, longitude, evidence_files) VALUES (?, ?, ?, ?, ?, ?)",
            (session['user_id'], description, location, lat, lng, json.dumps(evidence_files))
        )
        conn.commit()

    return jsonify({'status': 'success', 'message': 'Report submitted successfully'})


@app.route('/api/reports')
def get_reports():
    if 'user_id' not in session:
        return jsonify({'error': 'Unauthorized'}), 401

    with get_db() as conn:
        reports = conn.execute(
            "SELECT * FROM reports WHERE user_id = ? ORDER BY created_at DESC",
            (session['user_id'],)
        ).fetchall()

    return jsonify([{
        'id': r['id'],
        'description': r['description'],
        'location': r['location'],
        'evidence': json.loads(r['evidence_files']) if r['evidence_files'] else [],
        'created_at': r['created_at']
    } for r in reports])


@app.route('/logout')
def logout():
    session.clear()
    return redirect(url_for('login'))


if __name__ == '__main__':
    init_db()
    app.run(debug=True, host='127.0.0.1', port=5000)