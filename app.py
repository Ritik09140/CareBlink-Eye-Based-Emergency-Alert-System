import os
import sys
import sqlite3
import subprocess
import time
import threading
import math
import cv2
from datetime import datetime
from flask import Flask, render_template, request, jsonify, redirect, url_for, session, flash, Response
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
camera_instance = None
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

def trigger_internal_alert(patient_id, video_filename=None, message="Emergency: 5 rapid eye blinks detected from patient!"):
    conn = get_db_connection()
    cursor = conn.cursor()
    try:
        if db_engine == "mysql" and mysql_available:
            cursor.execute("SELECT patient_id FROM patients WHERE patient_id = %s", (patient_id,))
        else:
            cursor.execute("SELECT patient_id FROM patients WHERE patient_id = ?", (patient_id,))
            
        if not cursor.fetchone():
            print(f"[Internal Alert] Patient {patient_id} does not exist.")
            return False
            
        # Check duplicate active alert
        if db_engine == "mysql" and mysql_available:
            cursor.execute("SELECT id FROM alerts WHERE patient_id = %s AND status = 'active'", (patient_id,))
        else:
            cursor.execute("SELECT id FROM alerts WHERE patient_id = ? AND status = 'active'", (patient_id,))
            
        if cursor.fetchone():
            return True
            
        # Insert active alert
        if db_engine == "mysql" and mysql_available:
            cursor.execute("INSERT INTO alerts (patient_id, message, status, video_filename) VALUES (%s, %s, 'active', %s)", (patient_id, message, video_filename))
        else:
            cursor.execute("INSERT INTO alerts (patient_id, message, status, video_filename) VALUES (?, ?, 'active', ?)", (patient_id, message, video_filename))
        conn.commit()
        print(f"[Internal Alert SUCCESS] Alert triggered for patient {patient_id}.")
        return True
    except Exception as e:
        print(f"[Internal Alert ERROR] Failed to trigger alert: {e}")
        return False
    finally:
        cursor.close()
        conn.close()

class VideoCamera(object):
    def __init__(self, patient_id="PT-2045"):
        self.patient_id = patient_id
        # Try DirectShow first on Windows for faster and more reliable access, fallback to default
        self.cap = cv2.VideoCapture(0, cv2.CAP_DSHOW)
        if not self.cap.isOpened():
            self.cap = cv2.VideoCapture(0)
        self.lock = threading.Lock()
        self.latest_frame = None
        self.is_running = True
        
        # EAR parameters
        self.EAR_THRESHOLD = 0.22
        self.EAR_CONSEC_FRAMES = 2
        self.ALARM_BLINK_COUNT = 5
        self.ALARM_WINDOW_SEC = 5.0
        self.COOLDOWN_SEC = 10.0
        
        # Left Eye landmarks
        self.LEFT_EYE_H = (33, 133)
        self.LEFT_EYE_V = [(160, 144), (159, 145), (158, 153)]
        
        # Right Eye landmarks
        self.RIGHT_EYE_H = (362, 263)
        self.RIGHT_EYE_V = [(385, 380), (386, 373), (387, 374)]
        
        # State variables
        self.closed_frames = 0
        self.blink_timestamps = []
        self.last_alert_time = 0.0
        self.current_ear = 0.0
        self.current_blinks = 0
        self.face_detected = False
        
        # Personalized calibration data (defaults)
        self.baseline_ear = 0.28
        self.pupil_distance = 60.0
        self.current_pd = 60.0
        self.current_gaze = "center"
        self.last_active_gaze = None
        self.gaze_shift_timestamps = []
        
        # Video recorder variables
        self.video_writer = None
        self.record_frames_remaining = 0
        self.records_dir = "all records"
        os.makedirs(self.records_dir, exist_ok=True)
        
        # Load custom patient profile from database if not a temp scan
        if patient_id != "TEMP":
            conn = get_db_connection()
            cursor = conn.cursor()
            try:
                if db_engine == "mysql" and mysql_available:
                    cursor.execute("SELECT ear_threshold, baseline_ear, pupil_distance FROM patients WHERE patient_id = %s", (patient_id,))
                else:
                    cursor.execute("SELECT ear_threshold, baseline_ear, pupil_distance FROM patients WHERE patient_id = ?", (patient_id,))
                row = cursor.fetchone()
                if row:
                    if db_engine == "mysql" and mysql_available:
                        self.EAR_THRESHOLD = float(row[0]) if row[0] is not None else 0.22
                        self.baseline_ear = float(row[1]) if row[1] is not None else 0.28
                        self.pupil_distance = float(row[2]) if row[2] is not None else 60.0
                    else:
                        self.EAR_THRESHOLD = float(row["ear_threshold"]) if row["ear_threshold"] is not None else 0.22
                        self.baseline_ear = float(row["baseline_ear"]) if row["baseline_ear"] is not None else 0.28
                        self.pupil_distance = float(row["pupil_distance"]) if row["pupil_distance"] is not None else 60.0
                    print(f"[VideoCamera INFO] Loaded customized metrics for patient {patient_id}: Threshold={self.EAR_THRESHOLD:.3f}, Baseline={self.baseline_ear:.3f}, Pupil Distance={self.pupil_distance:.1f}mm")
            except Exception as e:
                print(f"[VideoCamera WARNING] Failed to load personalized config: {e}")
            finally:
                cursor.close()
                conn.close()
                
        # Ensure model is downloaded
        self.ensure_model_exists()
        
        # Initialize MediaPipe Task
        import mediapipe as mp
        from mediapipe.tasks import python
        from mediapipe.tasks.python import vision
        
        base_options = python.BaseOptions(model_asset_path="face_landmarker.task")
        options = vision.FaceLandmarkerOptions(
            base_options=base_options,
            output_face_blendshapes=False,
            output_facial_transformation_matrixes=False,
            num_faces=1
        )
        self.detector = vision.FaceLandmarker.create_from_options(options)
        
        self.thread = threading.Thread(target=self.update, args=())
        self.thread.daemon = True
        self.thread.start()
        
    def ensure_model_exists(self):
        MODEL_FILE = "face_landmarker.task"
        MODEL_URL = "https://storage.googleapis.com/mediapipe-models/face_landmarker/face_landmarker/float16/1/face_landmarker.task"
        if not os.path.exists(MODEL_FILE):
            print(f"\n[*] Downloading Face Landmarker model file ({MODEL_FILE}) from Google APIs CDN...")
            try:
                import urllib.request
                req = urllib.request.Request(
                    MODEL_URL, 
                    headers={'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64)'}
                )
                with urllib.request.urlopen(req) as response, open(MODEL_FILE, 'wb') as out_file:
                    out_file.write(response.read())
                print("[✔] Model downloaded successfully.")
            except Exception as e:
                print(f"[ERROR] Failed to download model file: {e}")
                
    def stop(self):
        self.is_running = False
        if self.thread.is_alive():
            self.thread.join(timeout=1.0)
        if self.video_writer is not None:
            self.video_writer.release()
        if self.cap.isOpened():
            self.cap.release()
        cv2.destroyAllWindows()
            
    def get_frame(self):
        with self.lock:
            return self.latest_frame
 
    def get_current_ear(self):
        return self.current_ear
 
    def get_current_blinks(self):
        return self.current_blinks
            
    def get_landmark_point(self, landmark, img_width, img_height):
        return (int(landmark.x * img_width), int(landmark.y * img_height))
        
    def distance(self, p1, p2):
        return math.sqrt((p1[0] - p2[0])**2 + (p1[1] - p2[1])**2)
        
    def calculate_ear(self, landmarks, horizontal_idx, vertical_idxs, w, h):
        h_p1 = self.get_landmark_point(landmarks[horizontal_idx[0]], w, h)
        h_p2 = self.get_landmark_point(landmarks[horizontal_idx[1]], w, h)
        
        v_dists = []
        for top_idx, bot_idx in vertical_idxs:
            top_p = self.get_landmark_point(landmarks[top_idx], w, h)
            bot_p = self.get_landmark_point(landmarks[bot_idx], w, h)
            v_dists.append(self.distance(top_p, bot_p))
            
        h_dist = self.distance(h_p1, h_p2)
        if h_dist == 0:
            return 0.0
            
        avg_v_dist = sum(v_dists) / len(vertical_idxs)
        return avg_v_dist / h_dist
        
    def update(self):
        import mediapipe as mp
        while self.is_running:
            if not self.cap.isOpened():
                # Attempt to re-open the camera if it was busy/closed
                self.cap.open(0, cv2.CAP_DSHOW)
                if not self.cap.isOpened():
                    self.cap.open(0)
                if not self.cap.isOpened():
                    time.sleep(2.0)
                    continue
                
            ret, frame = self.cap.read()
            if not ret:
                time.sleep(0.01)
                continue
                
            frame = cv2.flip(frame, 1)
            h, w, _ = frame.shape
            
            rgb_frame = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
            mp_image = mp.Image(image_format=mp.ImageFormat.SRGB, data=rgb_frame)
            results = self.detector.detect(mp_image)
            
            current_time = time.time()
            avg_ear = 0.0
            avg_gaze_offset = 0.0
            current_gaze_shifts = 0
            
            if results.face_landmarks:
                self.face_detected = True
                landmarks = results.face_landmarks[0]
                left_ear = self.calculate_ear(landmarks, self.LEFT_EYE_H, self.LEFT_EYE_V, w, h)
                right_ear = self.calculate_ear(landmarks, self.RIGHT_EYE_H, self.RIGHT_EYE_V, w, h)
                avg_ear = (left_ear + right_ear) / 2.0
                self.current_ear = avg_ear
                
                # Calculate Pupil Distance (estimated PD in mm)
                # left iris: 468, right iris: 473, face left: 234, face right: 454
                p_left_iris = self.get_landmark_point(landmarks[468], w, h)
                p_right_iris = self.get_landmark_point(landmarks[473], w, h)
                p_face_left = self.get_landmark_point(landmarks[234], w, h)
                p_face_right = self.get_landmark_point(landmarks[454], w, h)
                d_pupils = self.distance(p_left_iris, p_right_iris)
                w_face = self.distance(p_face_left, p_face_right)
                if w_face > 0:
                    self.current_pd = (d_pupils / w_face) * 140.0
                else:
                    self.current_pd = 60.0
                
                # Gaze tracking: offset calculation
                left_eye_center_x = (landmarks[33].x + landmarks[133].x) / 2.0
                left_eye_center_y = (landmarks[33].y + landmarks[133].y) / 2.0
                right_eye_center_x = (landmarks[362].x + landmarks[263].x) / 2.0
                right_eye_center_y = (landmarks[362].y + landmarks[263].y) / 2.0
                
                left_eye_width = self.distance(self.get_landmark_point(landmarks[33], w, h), self.get_landmark_point(landmarks[133], w, h))
                right_eye_width = self.distance(self.get_landmark_point(landmarks[362], w, h), self.get_landmark_point(landmarks[263], w, h))
                
                p_left_center = (int(left_eye_center_x * w), int(left_eye_center_y * h))
                p_right_center = (int(right_eye_center_x * w), int(right_eye_center_y * h))
                
                left_gaze_offset = (p_left_iris[0] - p_left_center[0]) / left_eye_width if left_eye_width > 0 else 0.0
                right_gaze_offset = (p_right_iris[0] - p_right_center[0]) / right_eye_width if right_eye_width > 0 else 0.0
                avg_gaze_offset = (left_gaze_offset + right_gaze_offset) / 2.0
                
                # Gaze direction classification
                if avg_gaze_offset < -0.09:
                    self.current_gaze = "right"
                elif avg_gaze_offset > 0.09:
                    self.current_gaze = "left"
                else:
                    self.current_gaze = "center"
                
                # Gaze shift detection
                if self.current_gaze in ["left", "right"]:
                    if self.last_active_gaze is not None and self.current_gaze != self.last_active_gaze:
                        self.gaze_shift_timestamps.append(current_time)
                        print(f"[*] Horizontal Gaze Shift: {self.last_active_gaze} -> {self.current_gaze}")
                    self.last_active_gaze = self.current_gaze
                
                color = (0, 255, 0)
                if avg_ear < self.EAR_THRESHOLD:
                    color = (0, 0, 255)
                    
                for idx in [self.LEFT_EYE_H[0], self.LEFT_EYE_H[1]] + [pt for pair in self.LEFT_EYE_V for pt in pair]:
                    pt = self.get_landmark_point(landmarks[idx], w, h)
                    cv2.circle(frame, pt, 2, color, -1)
                    
                for idx in [self.RIGHT_EYE_H[0], self.RIGHT_EYE_H[1]] + [pt for pair in self.RIGHT_EYE_V for pt in pair]:
                    pt = self.get_landmark_point(landmarks[idx], w, h)
                    cv2.circle(frame, pt, 2, color, -1)
                
                # Draw iris/pupil centers
                cv2.circle(frame, p_left_iris, 3, (255, 255, 0), -1)
                cv2.circle(frame, p_right_iris, 3, (255, 255, 0), -1)
                    
                if avg_ear < self.EAR_THRESHOLD:
                    self.closed_frames += 1
                else:
                    if self.closed_frames >= self.EAR_CONSEC_FRAMES:
                        # Stricter timing check: blinks must be consecutive (interval <= 1.2s)
                        if self.blink_timestamps:
                            time_since_last = current_time - self.blink_timestamps[-1]
                            if time_since_last > 1.2:
                                self.blink_timestamps = [current_time]
                            else:
                                self.blink_timestamps.append(current_time)
                        else:
                            self.blink_timestamps.append(current_time)
                        global last_blink_time
                        last_blink_time = time.time()
                        
                        # Call API blink endpoint locally for audio play sync
                        threading.Thread(target=lambda: requests.post("http://localhost:5000/api/blink", json={"patient_id": self.patient_id}), daemon=True).start()
                    self.closed_frames = 0
            else:
                self.face_detected = False
                self.current_ear = 0.0
                self.current_gaze = "center"
                    
            self.blink_timestamps = [t for t in self.blink_timestamps if current_time - t <= self.ALARM_WINDOW_SEC]
            current_blinks = len(self.blink_timestamps)
            self.current_blinks = current_blinks
            
            self.gaze_shift_timestamps = [t for t in self.gaze_shift_timestamps if current_time - t <= self.ALARM_WINDOW_SEC]
            current_gaze_shifts = len(self.gaze_shift_timestamps)
            
            cooldown_active = (current_time - self.last_alert_time) < self.COOLDOWN_SEC
            
            triggered_by_blinks = current_blinks >= self.ALARM_BLINK_COUNT
            triggered_by_gaze = current_gaze_shifts >= 4
            
            if (triggered_by_blinks or triggered_by_gaze) and not cooldown_active:
                self.last_alert_time = current_time
                self.blink_timestamps = []
                self.gaze_shift_timestamps = []
                
                alert_msg = "Emergency: 5 rapid eye blinks detected!" if triggered_by_blinks else "Emergency: Continuous horizontal eye movements detected!"
                
                # Trigger alert directly
                video_filename_val = None
                try:
                    timestamp = time.strftime("%Y%m%d_%H%M%S")
                    video_filename_val = f"alert_{self.patient_id}_{timestamp}.mp4"
                    video_filepath = os.path.join(self.records_dir, video_filename_val)
                    fourcc = cv2.VideoWriter_fourcc(*'mp4v')
                    fps = 15.0
                    self.video_writer = cv2.VideoWriter(video_filepath, fourcc, fps, (w, h))
                    self.record_frames_remaining = int(fps * 5.0)
                except Exception as ev:
                    print(f"[ERROR] Could not start video recording: {ev}")
                    
                trigger_internal_alert(self.patient_id, video_filename_val, message=alert_msg)
                
            if self.video_writer is not None:
                try:
                    self.video_writer.write(frame)
                    self.record_frames_remaining -= 1
                    cv2.circle(frame, (w - 20, 25), 8, (0, 0, 255), -1)
                    cv2.putText(frame, "REC", (w - 60, 30), cv2.FONT_HERSHEY_SIMPLEX, 0.5, (0, 0, 255), 2)
                    if self.record_frames_remaining <= 0:
                        self.video_writer.release()
                        self.video_writer = None
                except Exception as ev:
                    print(f"[ERROR] Writing frame to video failed: {ev}")
                    if self.video_writer:
                        self.video_writer.release()
                    self.video_writer = None
                    
            # Draw HUD on frame
            cv2.rectangle(frame, (10, 10), (380, 160), (25, 20, 15), -1)
            cv2.rectangle(frame, (10, 10), (380, 160), (60, 60, 60), 1)
            
            cv2.putText(frame, "CareBlink Patient Monitor", (20, 30), 
                        cv2.FONT_HERSHEY_SIMPLEX, 0.6, (6, 182, 212), 2)
            cv2.putText(frame, f"Patient ID: {self.patient_id}", (20, 50), 
                        cv2.FONT_HERSHEY_SIMPLEX, 0.5, (255, 255, 255), 1)
            cv2.putText(frame, f"EAR: {avg_ear:.3f} (Thresh: {self.EAR_THRESHOLD:.2f})", (20, 70), 
                        cv2.FONT_HERSHEY_SIMPLEX, 0.5, (255, 255, 255), 1)
            cv2.putText(frame, f"Gaze: {self.current_gaze.upper()} (Offset: {avg_gaze_offset:+.3f})", (20, 90), 
                        cv2.FONT_HERSHEY_SIMPLEX, 0.5, (255, 255, 255), 1)
            cv2.putText(frame, f"Est. PD: {self.current_pd:.1f} mm", (20, 110), 
                        cv2.FONT_HERSHEY_SIMPLEX, 0.5, (255, 255, 255), 1)
            cv2.putText(frame, f"Blinks: {current_blinks} | Shifts: {current_gaze_shifts}", (20, 130), 
                        cv2.FONT_HERSHEY_SIMPLEX, 0.5, (255, 255, 255), 1)
                        
            if cooldown_active:
                cv2.putText(frame, "ALERT COOLDOWN", (20, 150), 
                            cv2.FONT_HERSHEY_SIMPLEX, 0.5, (0, 140, 255), 1)
            else:
                cv2.putText(frame, "MONITORING ACTIVE", (20, 150), 
                            cv2.FONT_HERSHEY_SIMPLEX, 0.5, (16, 185, 129), 1)
                            
            if (current_time - self.last_alert_time) < 4.0:
                if int(current_time * 4) % 2 == 0:
                    cv2.rectangle(frame, (0, 0), (w, h), (0, 0, 255), 8)
                    cv2.putText(frame, "!!! EMERGENCY ALERT !!!", (w // 2 - 180, h // 2), 
                                cv2.FONT_HERSHEY_SIMPLEX, 1.0, (0, 0, 255), 3)
                                
            # Display frame in a separate OpenCV desktop window (disabled in web app thread to avoid GUI hangs)
            # cv2.imshow("CareBlink - Patient Eye Blink Detection", frame)
            # cv2.waitKey(1)

            ret_enc, jpeg = cv2.imencode('.jpg', frame)
            if ret_enc:
                with self.lock:
                    self.latest_frame = jpeg.tobytes()
                    
            time.sleep(0.04) # Cap to ~25 FPS

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
            ear_threshold FLOAT DEFAULT 0.22,
            baseline_ear FLOAT DEFAULT 0.28,
            pupil_distance FLOAT DEFAULT 60.0,
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
        try:
            cursor.execute("ALTER TABLE patients ADD COLUMN ear_threshold FLOAT DEFAULT 0.22")
        except Exception:
            pass
        try:
            cursor.execute("ALTER TABLE patients ADD COLUMN baseline_ear FLOAT DEFAULT 0.28")
        except Exception:
            pass
        try:
            cursor.execute("ALTER TABLE patients ADD COLUMN pupil_distance FLOAT DEFAULT 60.0")
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
            ear_threshold REAL DEFAULT 0.22,
            baseline_ear REAL DEFAULT 0.28,
            pupil_distance REAL DEFAULT 60.0,
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
        try:
            cursor.execute("ALTER TABLE patients ADD COLUMN ear_threshold REAL DEFAULT 0.22")
        except Exception:
            pass
        try:
            cursor.execute("ALTER TABLE patients ADD COLUMN baseline_ear REAL DEFAULT 0.28")
        except Exception:
            pass
        try:
            cursor.execute("ALTER TABLE patients ADD COLUMN pupil_distance REAL DEFAULT 60.0")
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
    global camera_instance
    if camera_instance is not None:
        print("[Camera Control] Camera is already running.")
        return True
    
    try:
        print(f"[Camera Control] Spawning camera stream class for patient {patient_id}...")
        camera_instance = VideoCamera(patient_id)
        return True
    except Exception as e:
        print(f"[Camera Control Error] Failed to launch camera: {e}")
        return False

def stop_camera_stream():
    global camera_instance
    if camera_instance is not None:
        print("[Camera Control] Stopping camera stream...")
        try:
            camera_instance.stop()
            camera_instance = None
            print("[Camera Control] Camera terminated successfully.")
            return True
        except Exception as e:
            print(f"[Camera Control Error] Failed to stop camera: {e}")
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
    global camera_instance
    is_running = camera_instance is not None
    current_ear = 0.0
    current_blinks = 0
    patient_id = "N/A"
    patient_name = "N/A"
    patient_age = "N/A"
    room_number = "N/A"
    medical_condition = "N/A"
    ear_threshold = 0.22
    baseline_ear = 0.28
    pupil_distance = 60.0
    face_detected = False
    
    if is_running:
        current_ear = camera_instance.get_current_ear()
        current_blinks = camera_instance.get_current_blinks()
        patient_id = camera_instance.patient_id
        face_detected = camera_instance.face_detected
        
        # Fetch patient details from database
        conn = get_db_connection()
        cursor = conn.cursor()
        try:
            if db_engine == "mysql" and mysql_available:
                cursor.execute("SELECT name, age, room_number, medical_condition, ear_threshold, baseline_ear, pupil_distance FROM patients WHERE patient_id = %s", (patient_id,))
                row = cursor.fetchone()
                if row:
                    patient_name = row[0]
                    patient_age = row[1]
                    room_number = row[2]
                    medical_condition = row[3]
                    ear_threshold = float(row[4]) if row[4] is not None else 0.22
                    baseline_ear = float(row[5]) if row[5] is not None else 0.28
                    pupil_distance = float(row[6]) if row[6] is not None else 60.0
            else:
                cursor.execute("SELECT name, age, room_number, medical_condition, ear_threshold, baseline_ear, pupil_distance FROM patients WHERE patient_id = ?", (patient_id,))
                row = cursor.fetchone()
                if row:
                    patient_name = row["name"]
                    patient_age = row["age"]
                    room_number = row["room_number"]
                    medical_condition = row["medical_condition"]
                    ear_threshold = float(row["ear_threshold"]) if row["ear_threshold"] is not None else 0.22
                    baseline_ear = float(row["baseline_ear"]) if row["baseline_ear"] is not None else 0.28
                    pupil_distance = float(row["pupil_distance"]) if row["pupil_distance"] is not None else 60.0
        except Exception as e:
            print(f"[Error fetching patient details for status] {e}")
        finally:
            cursor.close()
            conn.close()
        
    return jsonify({
        "is_running": is_running,
        "current_ear": round(current_ear, 3),
        "current_blinks": current_blinks,
        "patient_id": patient_id,
        "patient_name": patient_name,
        "patient_age": patient_age,
        "room_number": room_number,
        "medical_condition": medical_condition,
        "ear_threshold": round(ear_threshold, 3),
        "baseline_ear": round(baseline_ear, 3),
        "pupil_distance": round(pupil_distance, 1),
        "current_pd": round(camera_instance.current_pd, 1) if (is_running and hasattr(camera_instance, 'current_pd')) else 60.0,
        "current_gaze": camera_instance.current_gaze if (is_running and hasattr(camera_instance, 'current_gaze')) else "center",
        "face_detected": face_detected
    })

@app.route('/api/patient/<patient_id>/threshold', methods=['GET'])
def api_patient_threshold(patient_id):
    conn = get_db_connection()
    cursor = conn.cursor()
    try:
        if db_engine == "mysql" and mysql_available:
            cursor.execute("SELECT ear_threshold, baseline_ear, pupil_distance FROM patients WHERE patient_id = %s", (patient_id,))
        else:
            cursor.execute("SELECT ear_threshold, baseline_ear, pupil_distance FROM patients WHERE patient_id = ?", (patient_id,))
        row = cursor.fetchone()
        if row:
            if db_engine == "mysql" and mysql_available:
                return jsonify({
                    "success": True,
                    "ear_threshold": float(row[0]) if row[0] is not None else 0.22,
                    "baseline_ear": float(row[1]) if row[1] is not None else 0.28,
                    "pupil_distance": float(row[2]) if row[2] is not None else 60.0
                })
            else:
                return jsonify({
                    "success": True,
                    "ear_threshold": float(row["ear_threshold"]) if row["ear_threshold"] is not None else 0.22,
                    "baseline_ear": float(row["baseline_ear"]) if row["baseline_ear"] is not None else 0.28,
                    "pupil_distance": float(row["pupil_distance"]) if row["pupil_distance"] is not None else 60.0
                })
        return jsonify({"success": False, "message": "Patient not found"}), 404
    except Exception as e:
        return jsonify({"success": False, "message": str(e)}), 500
    finally:
        cursor.close()
        conn.close()

@app.route('/api/camera/scan_calibration', methods=['POST'])
@login_required
def api_scan_calibration():
    global camera_instance
    temp_camera = False
    if camera_instance is None:
        success = start_camera_stream("TEMP")
        if not success:
            return jsonify({"success": False, "message": "Failed to initialize camera. Make sure the webcam is connected."}), 500
        temp_camera = True
        time.sleep(1.5) # Warm up camera and landmark task
        
    ears = []
    pds = []
    start_time = time.time()
    
    # Collect frames for 3.5 seconds
    while time.time() - start_time < 3.5:
        if camera_instance and camera_instance.face_detected:
            ears.append(camera_instance.current_ear)
            if hasattr(camera_instance, 'current_pd'):
                pds.append(camera_instance.current_pd)
        time.sleep(0.1)
        
    if temp_camera:
        stop_camera_stream()
        
    if len(ears) < 10:
        return jsonify({"success": False, "message": "Calibration scan failed: Face not detected. Please look straight into the camera under clear lighting."}), 400
        
    # Calculate patient parameters from eyes
    valid_ears = [e for e in ears if e >= 0.16]
    if not valid_ears:
        valid_ears = ears
    baseline_ear = sum(valid_ears) / len(valid_ears)
    ear_threshold = baseline_ear * 0.75 # optimal threshold is 75% of baseline
    
    avg_pd = sum(pds) / len(pds) if pds else 60.0
    
    import random
    import string
    
    first_names = ["Jayraj", "Kabir", "Vihaan", "Aditya", "Sai", "Arjun", "Aryan", "Reyansh", "Krishna", "Atharva", "Rohan", "Jay", "Rutvik", "Rahul", "Sameer", "Sarah", "Connor", "Arthur", "Ford"]
    last_names = ["Khanguda", "Sharma", "Verma", "Gupta", "Patel", "Mehta", "Singh", "Joshi", "Rao", "Nair", "Kumar", "Dent", "Prefect"]
    name = f"{random.choice(first_names)} {random.choice(last_names)}"
    
    rand_suffix = ''.join(random.choices(string.ascii_uppercase + string.digits, k=4))
    patient_id = f"PT-EYE-{rand_suffix}"
    
    # Auto-generate diagnostic data
    age = int(22 + (avg_pd % 12) * 4)
    room = f"Room {random.randint(101, 308)}"
    condition = "Locked-in Syndrome (Optimal Eye Control)" if avg_pd > 62 else "Severe MND (Standard Eye Control)"
    
    return jsonify({
        "success": True,
        "patient_id": patient_id,
        "name": name,
        "baseline_ear": round(baseline_ear, 3),
        "ear_threshold": round(ear_threshold, 3),
        "pupil_distance": round(avg_pd, 1),
        "age": age,
        "room_number": room,
        "medical_condition": condition
    })

@app.route('/video_feed')
def video_feed():
    global camera_instance
    if camera_instance is None:
        return "Camera is not running", 404
        
    def gen():
        while True:
            global camera_instance
            if camera_instance is None:
                break
            frame = camera_instance.get_frame()
            if frame is not None:
                yield (b'--frame\r\n'
                       b'Content-Type: image/jpeg\r\n\r\n' + frame + b'\r\n')
            time.sleep(0.04)
            
    return Response(gen(), mimetype='multipart/x-mixed-replace; boundary=frame')

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
        ear_threshold = data.get('ear_threshold', 0.22)
        baseline_ear = data.get('baseline_ear', 0.28)
        pupil_distance = data.get('pupil_distance', 60.0)
        
        if not all([patient_id, name, age, room_number, medical_condition]):
            return jsonify({"success": False, "message": "All fields are required."}), 400
            
        try:
            if db_engine == "mysql" and mysql_available:
                cursor.execute("""
                INSERT INTO patients (patient_id, name, age, room_number, medical_condition, hospital_name, ear_threshold, baseline_ear, pupil_distance)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
                """, (patient_id, name, age, room_number, medical_condition, hospital_name, ear_threshold, baseline_ear, pupil_distance))
            else:
                cursor.execute("""
                INSERT INTO patients (patient_id, name, age, room_number, medical_condition, hospital_name, ear_threshold, baseline_ear, pupil_distance)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """, (patient_id, name, age, room_number, medical_condition, hospital_name, ear_threshold, baseline_ear, pupil_distance))
            conn.commit()
            return jsonify({"success": True, "message": "Patient registered."})
        except Exception as e:
            return jsonify({"success": False, "message": str(e)}), 500
        finally:
            cursor.close()
            conn.close()
            
    # GET: return list
    try:
        cursor.execute("SELECT patient_id, name, age, room_number, medical_condition, ear_threshold, baseline_ear, pupil_distance FROM patients")
        rows = cursor.fetchall()
        patients_list = []
        for r in rows:
            if db_engine == "mysql" and mysql_available:
                patients_list.append({
                    "patient_id": r[0], "name": r[1], "age": r[2], "room_number": r[3], "medical_condition": r[4],
                    "ear_threshold": r[5], "baseline_ear": r[6], "pupil_distance": r[7]
                })
            else:
                patients_list.append({
                    "patient_id": r["patient_id"], "name": r["name"], "age": r["age"], 
                    "room_number": r["room_number"], "medical_condition": r["medical_condition"],
                    "ear_threshold": r["ear_threshold"], "baseline_ear": r["baseline_ear"], "pupil_distance": r["pupil_distance"]
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
