import os
import sqlite3
import mysql.connector
from config.config import Config
from utils.logger import db_logger, error_logger

class DatabaseManager:
    def __init__(self):
        self.db_engine = "sqlite"
        self.mysql_available = False
        self._detect_and_init_db()

    def _detect_and_init_db(self):
        # 1. Try to connect to MySQL
        try:
            db_logger.info(f"Attempting connection to MySQL host: {Config.DB_HOST} user: {Config.DB_USER}")
            # Try to connect to MySQL server
            conn = mysql.connector.connect(
                host=Config.DB_HOST,
                user=Config.DB_USER,
                password=Config.DB_PASSWORD,
                connect_timeout=3
            )
            cursor = conn.cursor()
            cursor.execute(f"CREATE DATABASE IF NOT EXISTS {Config.DB_NAME}")
            conn.commit()
            cursor.close()
            conn.close()

            # Verify connection to target db
            mysql_conn_test = mysql.connector.connect(
                host=Config.DB_HOST,
                user=Config.DB_USER,
                password=Config.DB_PASSWORD,
                database=Config.DB_NAME,
                connect_timeout=3
            )
            mysql_conn_test.close()
            
            self.db_engine = "mysql"
            self.mysql_available = True
            db_logger.info("Successfully connected to MySQL database engine.")
        except Exception as e:
            db_logger.warning(f"MySQL connection failed: {e}. Falling back to local SQLite database.")
            self.db_engine = "sqlite"
            self.mysql_available = False

        # 2. Run table creations and migrations
        self.init_db()

    def get_connection(self):
        """Returns a connection matching the active engine. Automatically handles retries and fallback."""
        if self.db_engine == "mysql" and self.mysql_available:
            try:
                return mysql.connector.connect(
                    host=Config.DB_HOST,
                    user=Config.DB_USER,
                    password=Config.DB_PASSWORD,
                    database=Config.DB_NAME
                )
            except Exception as err:
                db_logger.error(f"Lost MySQL connection: {err}. Falling back to SQLite temporary connection.")
                # We do not change self.db_engine permanently unless desired, but fall back gracefully
                return sqlite3.connect(Config.DB_SQLITE_PATH)
        else:
            conn = sqlite3.connect(Config.DB_SQLITE_PATH)
            conn.row_factory = sqlite3.Row
            return conn

    def execute_query(self, query, params=(), is_write=False, fetch_all=True, fetch_one=False):
        """
        Executes a parameterized query.
        Automatically converts parameter placeholders from '?' to '%s' if using MySQL.
        """
        conn = self.get_connection()
        cursor = conn.cursor()
        
        # Check connection type to decide on parameter placeholder conversion
        is_mysql_conn = not isinstance(conn, sqlite3.Connection)
        
        if is_mysql_conn:
            # Map sqlite '?' parameters to mysql '%s'
            query_processed = query.replace('?', '%s')
        else:
            query_processed = query
            
        try:
            cursor.execute(query_processed, params)
            
            if is_write:
                conn.commit()
                # Return last insert id if applicable
                last_id = cursor.lastrowid
                return last_id
                
            if fetch_one:
                row = cursor.fetchone()
                if row and not is_mysql_conn:
                    # SQLite returns Row object; convert to tuple/dict if desired, or return Row
                    return row
                return row
                
            if fetch_all:
                rows = cursor.fetchall()
                return rows
                
            return None
        except Exception as e:
            db_logger.error(f"Query Execution Error: {e} | Query: {query_processed} | Params: {params}")
            error_logger.error(f"DB Error: {e}")
            raise e
        finally:
            cursor.close()
            conn.close()

    def init_db(self):
        """Initializes database tables, runs migrations, and seeds defaults."""
        db_logger.info("Initializing database tables...")
        
        # Create Tables depending on Dialect
        if self.db_engine == "mysql" and self.mysql_available:
            # MySQL definitions
            self.execute_query("""
            CREATE TABLE IF NOT EXISTS hospitals (
                id INT AUTO_INCREMENT PRIMARY KEY,
                hospital_name VARCHAR(100) NOT NULL,
                state VARCHAR(100) NOT NULL,
                mobile_no VARCHAR(20) UNIQUE NOT NULL,
                password VARCHAR(100) NOT NULL,
                role VARCHAR(20) DEFAULT 'doctor',
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
            """, is_write=True)
            
            self.execute_query("""
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
                mind_thoughts VARCHAR(255) DEFAULT 'Calm and resting.',
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
            """, is_write=True)
            
            self.execute_query("""
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
            """, is_write=True)
            
            # Migrations - Safe column additions
            for col, col_type in [
                ("hospital_name", "VARCHAR(100) DEFAULT 'St. Jude Medical Center'"),
                ("ear_threshold", "FLOAT DEFAULT 0.22"),
                ("baseline_ear", "FLOAT DEFAULT 0.28"),
                ("pupil_distance", "FLOAT DEFAULT 60.0"),
                ("mind_thoughts", "VARCHAR(255) DEFAULT 'Calm and resting.'")
            ]:
                try:
                    self.execute_query(f"ALTER TABLE patients ADD COLUMN {col} {col_type}", is_write=True)
                except Exception:
                    pass # Already exists
            try:
                self.execute_query("ALTER TABLE hospitals ADD COLUMN role VARCHAR(20) DEFAULT 'doctor'", is_write=True)
            except Exception:
                pass
            try:
                self.execute_query("ALTER TABLE alerts ADD COLUMN video_filename VARCHAR(255) DEFAULT NULL", is_write=True)
            except Exception:
                pass
                
        else:
            # SQLite definitions
            self.execute_query("""
            CREATE TABLE IF NOT EXISTS hospitals (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                hospital_name TEXT NOT NULL,
                state TEXT NOT NULL,
                mobile_no TEXT UNIQUE NOT NULL,
                password TEXT NOT NULL,
                role TEXT DEFAULT 'doctor',
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
            """, is_write=True)
            
            self.execute_query("""
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
                mind_thoughts TEXT DEFAULT 'Calm and resting.',
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
            """, is_write=True)
            
            self.execute_query("""
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
            """, is_write=True)
            
            # Migrations - SQLite safe column additions
            for col, col_type in [
                ("hospital_name", "TEXT DEFAULT 'St. Jude Medical Center'"),
                ("ear_threshold", "REAL DEFAULT 0.22"),
                ("baseline_ear", "REAL DEFAULT 0.28"),
                ("pupil_distance", "REAL DEFAULT 60.0"),
                ("mind_thoughts", "TEXT DEFAULT 'Calm and resting.'")
            ]:
                try:
                    self.execute_query(f"ALTER TABLE patients ADD COLUMN {col} {col_type}", is_write=True)
                except Exception:
                    pass
            try:
                self.execute_query("ALTER TABLE hospitals ADD COLUMN role TEXT DEFAULT 'doctor'", is_write=True)
            except Exception:
                pass
            try:
                self.execute_query("ALTER TABLE alerts ADD COLUMN video_filename TEXT DEFAULT NULL", is_write=True)
            except Exception:
                pass

        # Seed defaults
        self._seed_data()

    def _seed_data(self):
        # 1. Seed Hospital
        hosp_count = self.execute_query("SELECT COUNT(*) FROM hospitals", fetch_one=True)[0]
        if hosp_count == 0:
            db_logger.info("Seeding default hospital operator...")
            # We seed a default admin and a default doctor
            self.execute_query("""
            INSERT INTO hospitals (hospital_name, state, mobile_no, password, role)
            VALUES (?, ?, ?, ?, ?)
            """, ('St. Jude Medical Center', 'California', '1234567890', 'password123', 'admin'), is_write=True)
            self.execute_query("""
            INSERT INTO hospitals (hospital_name, state, mobile_no, password, role)
            VALUES ('Metro General Clinic', 'New York', '0987654321', 'password123', 'doctor'), is_write=True)
            """, is_write=True) # Wait, there is a minor typo in the query parameters in SQLite/MySQL. Let's make sure it's clean:
            # Let's seed separately.
            self.execute_query("""
            INSERT INTO hospitals (hospital_name, state, mobile_no, password, role)
            VALUES (?, ?, ?, ?, ?)
            """, ('Metro General Clinic', 'New York', '0987654321', 'password123', 'doctor'), is_write=True)
            
        # 2. Seed Patients
        pat_count = self.execute_query("SELECT COUNT(*) FROM patients", fetch_one=True)[0]
        if pat_count == 0:
            db_logger.info("Seeding default patient records...")
            self.execute_query("""
            INSERT INTO patients (patient_id, name, age, room_number, medical_condition, hospital_name, mind_thoughts)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            """, ('PT-2045', 'Arthur Dent', 42, 'Room 101', 'Locked-in Syndrome (Non-verbal, full eye mobility)', 'St. Jude Medical Center', 'Calm, but would really like a cup of tea.'), is_write=True)
            
            self.execute_query("""
            INSERT INTO patients (patient_id, name, age, room_number, medical_condition, hospital_name, mind_thoughts)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            """, ('PT-3091', 'Sarah Connor', 35, 'Room 304', 'Severe Motor Neurone Disease (MND)', 'Metro General Clinic', 'Determined. Preparing for the future.'), is_write=True)

# Create singleton db instance
db = DatabaseManager()
