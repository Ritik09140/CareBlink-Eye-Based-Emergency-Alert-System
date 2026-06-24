import os
import sys
import sqlite3
import subprocess
import time
from datetime import datetime
from flask import Flask, render_template, request, jsonify, redirect, url_for, session, flash
from dotenv import load_dotenv

# Load configuration
load_dotenv()

app = Flask(__name__)
app.secret_key = os.getenv("SECRET_KEY", "careblink_fallback_secret_key_123")

# Auto-create 'all records' folder
os.makedirs("all records", exist_ok=True)

# Database configuration
DB_HOST = os.getenv("DB_HOST", "localhost")
DB_USER = os.getenv("DB_USER", "root")
DB_PASSWORD = os.getenv("DB_PASSWORD", "")
DB_NAME = os.getenv("DB_NAME", "careblink")

# Global variables for camera monitoring and blink syncing
db_engine = "sqlite"
mysql_available = False
camera_process = None
last_blink_time = 0.0 # stores the timestamp of the last normal blink

# Try connecting to MySQL. If fails, fallback to SQLite automatically.
try:
    import mysql.connector
    conn = mysql.connector.connect(
        host=DB_HOST,
        user=DB_USER,
        password=DB_PASSWORD
    )
    cursor = conn.cursor()
    cursor.execute(f"CREATE DATABASE IF NOT EXISTS {DB_NAME}")
    conn.commit()
    cursor.close()
    conn.close()

    mysql_conn_test = mysql.connector.connect(
        host=DB_HOST,
        user=DB_USER,
        password=DB_PASSWORD,
        database=DB_NAME
    )
    mysql_conn_test.close()
    db_engine = "mysql"
    mysql_available = True
    print("\n[CareBlink Database] Successfully connected to MySQL database engine.")
except Exception as e:
    print(f"\n[CareBlink Database WARNING] MySQL connection failed: {e}")
    print("[CareBlink Database INFO] Automatically falling back to local SQLite database ('careblink.db').")
    db_engine = "sqlite"

def get_db_connection():
    if db_engine == "mysql" and mysql_available:
        try:
            return mysql.connector.connect(
                host=DB_HOST,
                user=DB_USER,
                password=DB_PASSWORD,
                database=DB_NAME
            )
        except Exception as err:
            print(f"[Database Error] Lost MySQL connection: {err}. Falling back to SQLite temporary connection.")
            return sqlite3.connect("careblink.db")
    else:
        conn = sqlite3.connect("careblink.db")
        conn.row_factory = sqlite3.Row
        return conn

def init_db():
    conn = get_db_connection()
    cursor = conn.cursor()
    
    if db_engine == "mysql" and mysql_available:
        cursor.execute("""
        CREATE TABLE IF NOT EXISTS hospitals (
            id INT AUTO_INCREMENT PRIMARY KEY,
            hospital_name VARCHAR(100) NOT NULL,
            state VARCHAR(100) NOT NULL,
            mobile_no VARCHAR(20) UNIQUE NOT NULL,
            password VARCHAR(100) NOT NULL,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
        """)
        cursor.execute("""
        CREATE TABLE IF NOT EXISTS patients (
            id INT AUTO_INCREMENT PRIMARY KEY,
            patient_id VARCHAR(50) UNIQUE NOT NULL,
            name VARCHAR(100) NOT NULL,
            age INT NOT NULL,
            room_number VARCHAR(20) NOT NULL,
            medical_condition VARCHAR(255) NOT NULL,
            hospital_name VARCHAR(100) DEFAULT 'St. Jude Medical Center',
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
        """)
        cursor.execute("""
        CREATE TABLE IF NOT EXISTS alerts (
            id INT AUTO_INCREMENT PRIMARY KEY,
            patient_id VARCHAR(50) NOT NULL,
            message VARCHAR(255) NOT NULL,
            status VARCHAR(20) DEFAULT 'active',
            video_filename VARCHAR(255) DEFAULT NULL,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            resolved_at TIMESTAMP NULL,
            FOREIGN KEY (patient_id) REFERENCES patients(patient_id) ON DELETE CASCADE
        )
        """)
        # MySQL Migrations
        try:
            cursor.execute("ALTER TABLE patients ADD COLUMN hospital_name VARCHAR(100) DEFAULT 'St. Jude Medical Center'")
        except Exception:
            pass
        try:
            cursor.execute("ALTER TABLE alerts ADD COLUMN video_filename VARCHAR(255) DEFAULT NULL")
        except Exception:
            pass

        # Seed default hospital
        cursor.execute("SELECT COUNT(*) FROM hospitals")
        if cursor.fetchone()[0] == 0:
            cursor.execute("""
            INSERT INTO hospitals (hospital_name, state, mobile_no, password)
            VALUES ('St. Jude Medical Center', 'California', '1234567890', 'password123')
            """)
        cursor.execute("SELECT COUNT(*) FROM patients")
        if cursor.fetchone()[0] == 0:
            cursor.execute("""
            INSERT INTO patients (patient_id, name, age, room_number, medical_condition, hospital_name)
            VALUES 
            ('PT-2045', 'Arthur Dent', 42, 'Room 101', 'Locked-in Syndrome (Non-verbal, full eye mobility)', 'St. Jude Medical Center'),
            ('PT-3091', 'Sarah Connor', 35, 'Room 304', 'Severe Motor Neurone Disease (MND)', 'Metro General Clinic')
            """)
        conn.commit()
    else:
        cursor.execute("""
        CREATE TABLE IF NOT EXISTS hospitals (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            hospital_name TEXT NOT NULL,
            state TEXT NOT NULL,
            mobile_no TEXT UNIQUE NOT NULL,
            password TEXT NOT NULL,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
        """)
        cursor.execute("""
        CREATE TABLE IF NOT EXISTS patients (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            patient_id TEXT UNIQUE NOT NULL,
            name TEXT NOT NULL,
            age INTEGER NOT NULL,
            room_number TEXT NOT NULL,
            medical_condition TEXT NOT NULL,
            hospital_name TEXT DEFAULT 'St. Jude Medical Center',
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
        """)
        cursor.execute("""
        CREATE TABLE IF NOT EXISTS alerts (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            patient_id TEXT NOT NULL,
            message TEXT NOT NULL,
            status TEXT DEFAULT 'active',
            video_filename TEXT DEFAULT NULL,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            resolved_at TIMESTAMP NULL,
            FOREIGN KEY (patient_id) REFERENCES patients(patient_id) ON DELETE CASCADE
        )
        """)
        # SQLite Migrations
        try:
            cursor.execute("ALTER TABLE patients ADD COLUMN hospital_name TEXT DEFAULT 'St. Jude Medical Center'")
        except Exception:
            pass
        try:
            cursor.execute("ALTER TABLE alerts ADD COLUMN video_filename TEXT DEFAULT NULL")
        except Exception:
            pass

        # Seed default hospital
        cursor.execute("SELECT COUNT(*) FROM hospitals")
        if cursor.fetchone()[0] == 0:
            cursor.execute("""
            INSERT INTO hospitals (hospital_name, state, mobile_no, password)
            VALUES (?, ?, ?, ?)
            """, ('St. Jude Medical Center', 'California', '1234567890', 'password123'))
        cursor.execute("SELECT COUNT(*) FROM patients")
        if cursor.fetchone()[0] == 0:
            cursor.executemany("""
            INSERT INTO patients (patient_id, name, age, room_number, medical_condition, hospital_name)
            VALUES (?, ?, ?, ?, ?, ?)
            """, [
                ('PT-2045', 'Arthur Dent', 42, 'Room 101', 'Locked-in Syndrome (Non-verbal, full eye mobility)', 'St. Jude Medical Center'),
                ('PT-3091', 'Sarah Connor', 35, 'Room 304', 'Severe Motor Neurone Disease (MND)', 'Metro General Clinic')
            ])
        conn.commit()
        
    cursor.close()
    conn.close()

# Initialize tables
init_db()

# --- Auth Decorator ---
def login_required(f):
    from functools import wraps
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if 'logged_in' not in session:
            return redirect(url_for('login'))
        return f(*args, **kwargs)
    return decorated_function

@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        mobile_no = request.form.get('mobile_no', '').strip()
        password = request.form.get('password', '').strip()
        
        # Backwards compatibility check
        if (mobile_no == 'doctor' or mobile_no == '1234567890') and password == 'password123':
            session['logged_in'] = True
            session['hospital_name'] = "St. Jude Medical Center"
            session['state'] = "California"
            session['mobile_no'] = mobile_no
            flash('Login successful!', 'success')
            start_camera_stream()
            return redirect(url_for('index'))
            
        # Database lookup
        conn = get_db_connection()
        cursor = conn.cursor()
        try:
            if db_engine == "mysql" and mysql_available:
                cursor.execute("SELECT hospital_name, state, mobile_no FROM hospitals WHERE mobile_no = %s AND password = %s", (mobile_no, password))
                row = cursor.fetchone()
                if row:
                    session['logged_in'] = True
                    session['hospital_name'] = row[0]
                    session['state'] = row[1]
                    session['mobile_no'] = row[2]
                    flash('Login successful!', 'success')
                    start_camera_stream()
                    return redirect(url_for('index'))
            else:
                cursor.execute("SELECT hospital_name, state, mobile_no FROM hospitals WHERE mobile_no = ? AND password = ?", (mobile_no, password))
                row = cursor.fetchone()
                if row:
                    session['logged_in'] = True
                    session['hospital_name'] = row["hospital_name"]
                    session['state'] = row["state"]
                    session['mobile_no'] = row["mobile_no"]
                    flash('Login successful!', 'success')
                    start_camera_stream()
                    return redirect(url_for('index'))
            
            flash('Invalid Mobile Number or Password.', 'danger')
        except Exception as e:
            flash(f'Database error: {e}', 'danger')
        finally:
            cursor.close()
            conn.close()
            
    return render_template('login.html')

@app.route('/register', methods=['POST'])
def register():
    hospital_name = request.form.get('hospital_name', '').strip()
    state = request.form.get('state', '').strip()
    mobile_no = request.form.get('mobile_no', '').strip()
    password = request.form.get('password', '').strip()
    
    if not all([hospital_name, state, mobile_no, password]):
        flash('All fields are required.', 'danger')
        return redirect(url_for('login'))
        
    conn = get_db_connection()
    cursor = conn.cursor()
    try:
        if db_engine == "mysql" and mysql_available:
            cursor.execute("""
                INSERT INTO hospitals (hospital_name, state, mobile_no, password)
                VALUES (%s, %s, %s, %s)
            """, (hospital_name, state, mobile_no, password))
        else:
            cursor.execute("""
                INSERT INTO hospitals (hospital_name, state, mobile_no, password)
                VALUES (?, ?, ?, ?)
            """, (hospital_name, state, mobile_no, password))
        conn.commit()
        flash('Registration successful! Please login.', 'success')
    except Exception as e:
        flash(f'Registration failed (Mobile number may already exist): {e}', 'danger')
    finally:
        cursor.close()
        conn.close()
        
    return redirect(url_for('login'))

@app.route('/logout')
def logout():
    session.pop('logged_in', None)
    session.pop('hospital_name', None)
    session.pop('state', None)
    session.pop('mobile_no', None)
    stop_camera_stream()
    return redirect(url_for('login'))

@app.route('/')
@login_required
def index():
    return render_template('index.html')


# ==========================================================================
# Subprocess Camera Control Functions
# ==========================================================================

def start_camera_stream(patient_id="PT-2045"):
    global camera_process
    # Check if process is already running
    if camera_process and camera_process.poll() is None:
        print("[Camera Control] Camera is already running.")
        return True
    
    try:
        print(f"[Camera Control] Automatically spawning camera stream for patient {patient_id}...")
        # Start detector.py as a subprocess passing patient_id as argument so it doesn't block on prompt
        camera_process = subprocess.Popen(
            [sys.executable, "detector.py", patient_id],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL
        )
        return True
    except Exception as e:
        print(f"[Camera Control Error] Failed to launch detector.py: {e}")
        return False

def stop_camera_stream():
    global camera_process
    if camera_process:
        print("[Camera Control] Terminating detector camera process...")
        try:
            if sys.platform.startswith('win'):
                # Force kill process tree on Windows to ensure OpenCV window closes instantly
                subprocess.run(["taskkill", "/F", "/T", "/PID", str(camera_process.pid)], capture_output=True)
            else:
                camera_process.terminate()
            camera_process = None
            print("[Camera Control] Camera terminated successfully.")
            return True
        except Exception as e:
            print(f"[Camera Control Error] Failed to stop camera process: {e}")
    return False


# ==========================================================================
# API Endpoints
# ==========================================================================

@app.route('/api/camera/start', methods=['POST'])
@login_required
def api_start_camera():
    data = request.json or {}
    patient_id = data.get('patient_id', 'PT-2045')
    success = start_camera_stream(patient_id)
    return jsonify({"success": success})

@app.route('/api/camera/stop', methods=['POST'])
@login_required
def api_stop_camera():
    success = stop_camera_stream()
    return jsonify({"success": success})

@app.route('/api/camera/status', methods=['GET'])
@login_required
def api_camera_status():
    global camera_process
    is_running = camera_process is not None and camera_process.poll() is None
    return jsonify({"is_running": is_running})

@app.route('/api/blink', methods=['POST'])
def api_record_blink():
    """
    Endpoint called by detector.py when a normal blink occurs.
    Allows dashboard to play a soft blink beep sound.
    """
    global last_blink_time
    last_blink_time = time.time()
    return jsonify({"success": True})

@app.route('/api/patients', methods=['GET', 'POST'])
@login_required
def api_patients():
    conn = get_db_connection()
    cursor = conn.cursor()
    
    if request.method == 'POST':
        data = request.json
        patient_id = data.get('patient_id')
        name = data.get('name')
        age = data.get('age')
        room_number = data.get('room_number')
        medical_condition = data.get('medical_condition')
        hospital_name = session.get('hospital_name', 'St. Jude Medical Center')
        
        if not all([patient_id, name, age, room_number, medical_condition]):
            return jsonify({"success": False, "message": "All fields are required."}), 400
            
        try:
            if db_engine == "mysql" and mysql_available:
                cursor.execute("""
                INSERT INTO patients (patient_id, name, age, room_number, medical_condition, hospital_name)
                VALUES (%s, %s, %s, %s, %s, %s)
                """, (patient_id, name, age, room_number, medical_condition, hospital_name))
            else:
                cursor.execute("""
                INSERT INTO patients (patient_id, name, age, room_number, medical_condition, hospital_name)
                VALUES (?, ?, ?, ?, ?, ?)
                """, (patient_id, name, age, room_number, medical_condition, hospital_name))
            conn.commit()
            return jsonify({"success": True, "message": "Patient registered."})
        except Exception as e:
            return jsonify({"success": False, "message": str(e)}), 500
        finally:
            cursor.close()
            conn.close()
            
    # GET: return list
    try:
        cursor.execute("SELECT patient_id, name, age, room_number, medical_condition FROM patients")
        rows = cursor.fetchall()
        patients_list = []
        for r in rows:
            if db_engine == "mysql" and mysql_available:
                patients_list.append({
                    "patient_id": r[0], "name": r[1], "age": r[2], "room_number": r[3], "medical_condition": r[4]
                })
            else:
                patients_list.append({
                    "patient_id": r["patient_id"], "name": r["name"], "age": r["age"], 
                    "room_number": r["room_number"], "medical_condition": r["medical_condition"]
                })
        return jsonify(patients_list)
    except Exception as e:
        return jsonify({"error": str(e)}), 500
    finally:
        cursor.close()
        conn.close()

@app.route('/api/alerts', methods=['POST'])
def api_trigger_alert():
    data = request.json or {}
    patient_id = data.get('patient_id', 'PT-2045')
    message = data.get('message', 'Emergency: 5 rapid eye blinks detected!')
    video_filename = data.get('video_filename', None)
    
    conn = get_db_connection()
    cursor = conn.cursor()
    
    try:
        if db_engine == "mysql" and mysql_available:
            cursor.execute("SELECT patient_id FROM patients WHERE patient_id = %s", (patient_id,))
        else:
            cursor.execute("SELECT patient_id FROM patients WHERE patient_id = ?", (patient_id,))
            
        if not cursor.fetchone():
            return jsonify({"success": False, "message": "Patient does not exist."}), 404
        
        # Check duplicate active alert
        if db_engine == "mysql" and mysql_available:
            cursor.execute("SELECT id FROM alerts WHERE patient_id = %s AND status = 'active'", (patient_id,))
        else:
            cursor.execute("SELECT id FROM alerts WHERE patient_id = ? AND status = 'active'", (patient_id,))
            
        if cursor.fetchone():
            return jsonify({"success": True, "message": "Alert is already active."})

        # Insert active alert
        if db_engine == "mysql" and mysql_available:
            cursor.execute("INSERT INTO alerts (patient_id, message, status, video_filename) VALUES (%s, %s, 'active', %s)", (patient_id, message, video_filename))
        else:
            cursor.execute("INSERT INTO alerts (patient_id, message, status, video_filename) VALUES (?, ?, 'active', ?)", (patient_id, message, video_filename))
        conn.commit()
        return jsonify({"success": True, "message": "Alert triggered."})
    except Exception as e:
        return jsonify({"success": False, "message": str(e)}), 500
    finally:
        cursor.close()
        conn.close()

@app.route('/api/alerts/active', methods=['GET'])
@login_required
def api_active_alerts():
    conn = get_db_connection()
    cursor = conn.cursor()
    
    try:
        query = """
            SELECT a.id, a.patient_id, a.message, a.created_at, p.name, p.room_number, p.medical_condition 
            FROM alerts a JOIN patients p ON a.patient_id = p.patient_id 
            WHERE a.status = 'active' LIMIT 1
        """
        cursor.execute(query)
        row = cursor.fetchone()
        
        if row:
            if db_engine == "mysql" and mysql_available:
                created_at_str = row[3].strftime("%Y-%m-%d %H:%M:%S") if isinstance(row[3], datetime) else str(row[3])
                alert_info = {
                    "alert_id": row[0], "patient_id": row[1], "message": row[2], "created_at": created_at_str,
                    "name": row[4], "room_number": row[5], "medical_condition": row[6]
                }
            else:
                alert_info = {
                    "alert_id": row["id"], "patient_id": row["patient_id"], "message": row["message"], 
                    "created_at": row["created_at"], "name": row["name"], "room_number": row["room_number"], 
                    "medical_condition": row["medical_condition"]
                }
            return jsonify({"has_active": True, "alert": alert_info, "last_blink_time": last_blink_time})
        return jsonify({"has_active": False, "last_blink_time": last_blink_time})
    except Exception as e:
        return jsonify({"error": str(e)}), 500
    finally:
        cursor.close()
        conn.close()

@app.route('/api/alerts/dismiss', methods=['POST'])
@login_required
def api_dismiss_alert():
    conn = get_db_connection()
    cursor = conn.cursor()
    now_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    try:
        if db_engine == "mysql" and mysql_available:
            cursor.execute("UPDATE alerts SET status = 'dismissed', resolved_at = %s WHERE status = 'active'", (now_str,))
        else:
            cursor.execute("UPDATE alerts SET status = 'dismissed', resolved_at = ? WHERE status = 'active'", (now_str,))
        conn.commit()
        return jsonify({"success": True})
    except Exception as e:
        return jsonify({"success": False, "message": str(e)}), 500
    finally:
        cursor.close()
        conn.close()

@app.route('/api/alerts/history', methods=['GET'])
@login_required
def api_alerts_history():
    conn = get_db_connection()
    cursor = conn.cursor()
    try:
        query = """
            SELECT a.created_at, a.patient_id, p.name, p.room_number, a.message, a.status, a.resolved_at 
            FROM alerts a JOIN patients p ON a.patient_id = p.patient_id 
            ORDER BY a.created_at DESC LIMIT 15
        """
        cursor.execute(query)
        rows = cursor.fetchall()
        
        history = []
        for r in rows:
            if db_engine == "mysql" and mysql_available:
                created_at_str = r[0].strftime("%Y-%m-%d %H:%M:%S") if isinstance(r[0], datetime) else str(r[0])
                resolved_at_str = r[6].strftime("%Y-%m-%d %H:%M:%S") if isinstance(r[6], datetime) else (str(r[6]) if r[6] else "-")
                history.append({
                    "created_at": created_at_str, "patient_id": r[1], "name": r[2], 
                    "room_number": r[3], "message": r[4], "status": r[5], "resolved_at": resolved_at_str
                })
            else:
                history.append({
                    "created_at": r["created_at"], "patient_id": r["patient_id"], "name": r["name"],
                    "room_number": r["room_number"], "message": r["message"], "status": r["status"],
                    "resolved_at": r["resolved_at"] if r["resolved_at"] else "-"
                })
        return jsonify(history)
    except Exception as e:
        return jsonify({"error": str(e)}), 500
    finally:
        cursor.close()
        conn.close()

@app.route('/api/hospital/records', methods=['GET'])
@login_required
def api_hospital_records():
    hospital_name = session.get('hospital_name', 'St. Jude Medical Center')
    state = session.get('state', 'California')
    
    conn = get_db_connection()
    cursor = conn.cursor()
    
    try:
        # Query patients registered under this hospital
        if db_engine == "mysql" and mysql_available:
            cursor.execute("SELECT patient_id, name, age, room_number, medical_condition FROM patients WHERE hospital_name = %s", (hospital_name,))
            p_rows = cursor.fetchall()
            patients = []
            for r in p_rows:
                patients.append({
                    "patient_id": r[0], "name": r[1], "age": r[2], "room_number": r[3], "medical_condition": r[4]
                })
        else:
            cursor.execute("SELECT patient_id, name, age, room_number, medical_condition FROM patients WHERE hospital_name = ?", (hospital_name,))
            p_rows = cursor.fetchall()
            patients = []
            for r in p_rows:
                patients.append({
                    "patient_id": r["patient_id"], "name": r["name"], "age": r["age"],
                    "room_number": r["room_number"], "medical_condition": r["medical_condition"]
                })
                
        # Query alert logs with video filename for this hospital's patients
        query = """
            SELECT a.created_at, a.patient_id, p.name, p.room_number, a.message, a.status, a.video_filename 
            FROM alerts a JOIN patients p ON a.patient_id = p.patient_id 
            WHERE p.hospital_name = ? 
            ORDER BY a.created_at DESC
        """
        if db_engine == "mysql" and mysql_available:
            cursor.execute(query.replace("?", "%s"), (hospital_name,))
            a_rows = cursor.fetchall()
            alerts = []
            for r in a_rows:
                created_at_str = r[0].strftime("%Y-%m-%d %H:%M:%S") if isinstance(r[0], datetime) else str(r[0])
                alerts.append({
                    "created_at": created_at_str, "patient_id": r[1], "name": r[2],
                    "room_number": r[3], "message": r[4], "status": r[5], "video_filename": r[6]
                })
        else:
            cursor.execute(query, (hospital_name,))
            a_rows = cursor.fetchall()
            alerts = []
            for r in a_rows:
                alerts.append({
                    "created_at": r["created_at"], "patient_id": r["patient_id"], "name": r["name"],
                    "room_number": r["room_number"], "message": r["message"], "status": r["status"],
                    "video_filename": r["video_filename"]
                })
                
        return jsonify({
            "hospital_name": hospital_name,
            "state": state,
            "patients": patients,
            "alerts": alerts
        })
    except Exception as e:
        return jsonify({"error": str(e)}), 500
    finally:
        cursor.close()
        conn.close()

from flask import send_from_directory
@app.route('/all_records/<path:filename>')
@login_required
def serve_record_video(filename):
    return send_from_directory('all records', filename)

if __name__ == '__main__':
    port = int(os.getenv("FLASK_PORT", 5000))
    app.run(host="0.0.0.0", port=port, debug=True)
