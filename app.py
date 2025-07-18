from flask import Flask, render_template, request, redirect, session, url_for, flash
import sqlite3
from werkzeug.security import generate_password_hash, check_password_hash

app = Flask(__name__)
app.secret_key = 'my_super_secret_key_123'  # Change this to something secure
DATABASE = 'blood_sugar.db'

# --- Create Users Table ---
conn = sqlite3.connect('users.db')
c = conn.cursor()
c.execute('''
    CREATE TABLE IF NOT EXISTS users (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        username TEXT UNIQUE NOT NULL,
        password TEXT NOT NULL
    )
''')
conn.commit()
conn.close()

# --- Create Blood Sugar Table ---
def create_table():
    conn = sqlite3.connect(DATABASE)
    c = conn.cursor()
    c.execute('''CREATE TABLE IF NOT EXISTS blood_sugar_entries (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    user_id INTEGER,
                    date TEXT,
                    time TEXT,
                    reading_mmol REAL,
                    reading_mgdl REAL,
                    time_of_day TEXT,
                    classification TEXT
                )''')
    conn.commit()
    conn.close()

# --- Classify Reading ---
def classify_reading(mgdl):
    if mgdl < 70:
        return "Low"
    elif 70 <= mgdl <= 130:
        return "Normal"
    elif 131 <= mgdl <= 180:
        return "Borderline"
    elif 181 <= mgdl <= 250:
        return "High"
    else:
        return "Dangerous"

# --- Calculate HbA1c ---
def calculate_hba1c_from_db(user_id):
    conn = sqlite3.connect(DATABASE)
    c = conn.cursor()
    c.execute("SELECT reading_mgdl FROM blood_sugar_entries WHERE user_id = ?", (user_id,))
    results = c.fetchall()
    conn.close()

    if not results:
        return None, None, None

    values = [row[0] for row in results]
    avg_mgdl = sum(values) / len(values)
    hba1c_dcct = (avg_mgdl + 46.7) / 28.7
    hba1c_ifcc = (hba1c_dcct - 2.15) * 10.929
    return round(avg_mgdl, 1), round(hba1c_dcct, 2), round(hba1c_ifcc, 1)

def get_chart_data(user_id, unit='mgdl'):
    conn = sqlite3.connect(DATABASE)
    c = conn.cursor()
    c.execute("""SELECT date, time, reading_mgdl, reading_mmol, classification 
                 FROM blood_sugar_entries 
                 WHERE user_id = ? 
                 ORDER BY date, time""", (user_id,))
    results = c.fetchall()
    conn.close()
    
    chart_data = {
        'labels': [],
        'readings': [],
        'colors': [],
        'legend': {
            'Low': '#ff6b6b',
            'Normal': '#51cf66', 
            'Borderline': '#ffd43b',
            'High': '#ff8787',
            'Dangerous': '#c92a2a'
        },
        'unit': unit
    }
    
    for row in results:
        chart_data['labels'].append(f"{row[0]} {row[1]}")
        # Choose reading based on unit
        reading = row[2] if unit == 'mgdl' else row[3]
        chart_data['readings'].append(reading)
        chart_data['colors'].append(chart_data['legend'].get(row[4], '#666'))
    
    return chart_data

@app.route('/', methods=['GET', 'POST'])
def index():
    if 'user_id' not in session:
        return redirect(url_for('login'))

    user_id = session['user_id']

    # Get blood sugar entries from your database for this user
    conn = sqlite3.connect('blood_sugar.db')
    c = conn.cursor()
    c.execute('SELECT date, value, unit FROM blood_sugar WHERE user_id = ? ORDER BY date', (user_id,))
    rows = c.fetchall()
    conn.close()

    # Convert to list of dictionaries (optional, helps with template logic)
    entries = [{'date': row[0], 'value': row[1], 'unit': row[2]} for row in rows]

    # Prepare chart data
    chart_labels = [entry['date'] for entry in entries]
    chart_readings = [entry['value'] for entry in entries]
    unit = entries[0]['unit'] if entries else 'mg/dL'  # fallback if no data

    chart_data = {
        'labels': chart_labels,
        'readings': chart_readings,
        'unit': unit
    }

    return render_template('index.html', entries=entries, chart_data=chart_data)


    create_table()
    user_id = session['user_id']
    chart_data = get_chart_data(user_id, 'mgdl')

    if request.method == 'POST':
        date = request.form['date']
        time = request.form['time']
        reading = float(request.form['reading'])
        unit = request.form['unit']
        time_of_day = request.form['time_of_day']

        if unit == 'mmol':
            reading_mmol = reading
            reading_mgdl = reading * 18.0
        else:
            reading_mgdl = reading
            reading_mmol = reading / 18.0

        classification = classify_reading(reading_mgdl)

        conn = sqlite3.connect(DATABASE)
        c = conn.cursor()
        c.execute('''INSERT INTO blood_sugar_entries 
                     (user_id, date, time, reading_mmol, reading_mgdl, time_of_day, classification)
                     VALUES (?, ?, ?, ?, ?, ?, ?)''',
                  (user_id, date, time, reading_mmol, reading_mgdl, time_of_day, classification))
        conn.commit()
        conn.close()
        return redirect('/')

    conn = sqlite3.connect(DATABASE)
    c = conn.cursor()
    c.execute("""SELECT date, time, reading_mmol, reading_mgdl, time_of_day, classification 
               FROM blood_sugar_entries WHERE user_id = ? ORDER BY id DESC""", (user_id,))
    entries = c.fetchall()
    conn.close()

    avg_mgdl, hba1c_dcct, hba1c_ifcc = calculate_hba1c_from_db(user_id)
    return render_template('index.html', entries=entries,
                           avg_mgdl=avg_mgdl,
                           hba1c_dcct=hba1c_dcct,
                           hba1c_ifcc=hba1c_ifcc,
                           chart_data=chart_data)

# --- Register ---
@app.route('/register', methods=['GET', 'POST'])
def register():
    if request.method == 'POST':
        username = request.form['username'].strip().lower()
        password = request.form['password']
        hashed_password = generate_password_hash(password)

        try:
            conn = sqlite3.connect('users.db')
            c = conn.cursor()
            c.execute("INSERT INTO users (username, password) VALUES (?, ?)", (username, hashed_password))
            conn.commit()
            conn.close()
            flash('Account created! Please log in.', 'success')
            return redirect(url_for('login'))
        except sqlite3.IntegrityError:
            flash('Username already exists. Please try another.', 'danger')

    return render_template('register.html')

# --- Login ---
@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        username = request.form['username'].strip().lower()
        password = request.form['password']

        conn = sqlite3.connect('users.db')
        c = conn.cursor()
        c.execute("SELECT id, password FROM users WHERE username = ?", (username,))
        user = c.fetchone()
        conn.close()

        if user and check_password_hash(user[1], password):
            session['user_id'] = user[0]
            session['username'] = username
            return redirect(url_for('index'))
        else:
            flash('Invalid username or password', 'danger')

    return render_template('login.html')

# --- Logout ---
@app.route('/logout')
def logout():
    session.clear()
    return redirect(url_for('login'))

if __name__ == '__main__':
    app.run(debug=True)
