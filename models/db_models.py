from database.connection import db

class HospitalModel:
    @staticmethod
    def get_by_mobile(mobile_no):
        row = db.execute_query(
            "SELECT hospital_name, state, mobile_no, password, role FROM hospitals WHERE mobile_no = ?",
            (mobile_no,), fetch_one=True
        )
        if row:
            return {
                "hospital_name": row[0],
                "state": row[1],
                "mobile_no": row[2],
                "password": row[3],
                "role": row[4]
            }
        return None

    @staticmethod
    def create(hospital_name, state, mobile_no, password, role='doctor'):
        return db.execute_query(
            "INSERT INTO hospitals (hospital_name, state, mobile_no, password, role) VALUES (?, ?, ?, ?, ?)",
            (hospital_name, state, mobile_no, password, role), is_write=True
        )

    @staticmethod
    def get_all():
        rows = db.execute_query("SELECT hospital_name, state, mobile_no, role FROM hospitals")
        return [
            {"hospital_name": r[0], "state": r[1], "mobile_no": r[2], "role": r[3]}
            for r in rows
        ]

class PatientModel:
    @staticmethod
    def get_by_id(patient_id):
        row = db.execute_query(
            """SELECT patient_id, name, age, room_number, medical_condition, hospital_name, 
                      ear_threshold, baseline_ear, pupil_distance, mind_thoughts 
               FROM patients WHERE patient_id = ?""",
            (patient_id,), fetch_one=True
        )
        if row:
            return {
                "patient_id": row[0],
                "name": row[1],
                "age": row[2],
                "room_number": row[3],
                "medical_condition": row[4],
                "hospital_name": row[5],
                "ear_threshold": row[6],
                "baseline_ear": row[7],
                "pupil_distance": row[8],
                "mind_thoughts": row[9]
            }
        return None

    @staticmethod
    def create(patient_id, name, age, room_number, medical_condition, hospital_name,
               ear_threshold=0.22, baseline_ear=0.28, pupil_distance=60.0, mind_thoughts='Calm and resting.'):
        return db.execute_query(
            """INSERT INTO patients (patient_id, name, age, room_number, medical_condition, hospital_name, 
                                     ear_threshold, baseline_ear, pupil_distance, mind_thoughts)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (patient_id, name, age, room_number, medical_condition, hospital_name,
             ear_threshold, baseline_ear, pupil_distance, mind_thoughts), is_write=True
        )

    @staticmethod
    def get_all():
        rows = db.execute_query(
            """SELECT patient_id, name, age, room_number, medical_condition, hospital_name, 
                      ear_threshold, baseline_ear, pupil_distance, mind_thoughts FROM patients"""
        )
        return [
            {
                "patient_id": r[0], "name": r[1], "age": r[2], "room_number": r[3], "medical_condition": r[4],
                "hospital_name": r[5], "ear_threshold": r[6], "baseline_ear": r[7], "pupil_distance": r[8],
                "mind_thoughts": r[9]
            }
            for r in rows
        ]

    @staticmethod
    def get_by_hospital(hospital_name):
        rows = db.execute_query(
            """SELECT patient_id, name, age, room_number, medical_condition, hospital_name, 
                      ear_threshold, baseline_ear, pupil_distance, mind_thoughts 
               FROM patients WHERE hospital_name = ?""",
            (hospital_name,)
        )
        return [
            {
                "patient_id": r[0], "name": r[1], "age": r[2], "room_number": r[3], "medical_condition": r[4],
                "hospital_name": r[5], "ear_threshold": r[6], "baseline_ear": r[7], "pupil_distance": r[8],
                "mind_thoughts": r[9]
            }
            for r in rows
        ]

class AlertModel:
    @staticmethod
    def get_active_by_patient(patient_id):
        row = db.execute_query(
            "SELECT id FROM alerts WHERE patient_id = ? AND status = 'active'",
            (patient_id,), fetch_one=True
        )
        return row is not None

    @staticmethod
    def get_active_alert():
        row = db.execute_query(
            """SELECT a.id, a.patient_id, a.message, a.created_at, p.name, p.room_number, p.medical_condition, p.mind_thoughts, a.video_filename
               FROM alerts a JOIN patients p ON a.patient_id = p.patient_id 
               WHERE a.status = 'active' ORDER BY a.created_at DESC LIMIT 1""",
            fetch_one=True
        )
        if row:
            created_at_val = row[3].strftime("%Y-%m-%d %H:%M:%S") if hasattr(row[3], 'strftime') else str(row[3])
            return {
                "alert_id": row[0],
                "patient_id": row[1],
                "message": row[2],
                "created_at": created_at_val,
                "name": row[4],
                "room_number": row[5],
                "medical_condition": row[6],
                "mind_thoughts": row[7],
                "video_filename": row[8]
            }
        return None

    @staticmethod
    def trigger(patient_id, message, video_filename=None):
        # Prevent duplicates
        if AlertModel.get_active_by_patient(patient_id):
            return True
            
        return db.execute_query(
            "INSERT INTO alerts (patient_id, message, status, video_filename) VALUES (?, ?, 'active', ?)",
            (patient_id, message, video_filename), is_write=True
        )

    @staticmethod
    def dismiss_all():
        from datetime import datetime
        now_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        return db.execute_query(
            "UPDATE alerts SET status = 'dismissed', resolved_at = ? WHERE status = 'active'",
            (now_str,), is_write=True
        )

    @staticmethod
    def get_history(limit=15):
        rows = db.execute_query(
            """SELECT a.created_at, a.patient_id, p.name, p.room_number, a.message, a.status, a.resolved_at, a.video_filename
               FROM alerts a JOIN patients p ON a.patient_id = p.patient_id 
               ORDER BY a.created_at DESC LIMIT ?""",
            (limit,)
        )
        history = []
        for r in rows:
            created_at_val = r[0].strftime("%Y-%m-%d %H:%M:%S") if hasattr(r[0], 'strftime') else str(r[0])
            resolved_at_val = r[6].strftime("%Y-%m-%d %H:%M:%S") if (r[6] and hasattr(r[6], 'strftime')) else (str(r[6]) if r[6] else "-")
            history.append({
                "created_at": created_at_val,
                "patient_id": r[1],
                "name": r[2],
                "room_number": r[3],
                "message": r[4],
                "status": r[5],
                "resolved_at": resolved_at_val,
                "video_filename": r[7]
            })
        return history

    @staticmethod
    def get_by_hospital(hospital_name):
        rows = db.execute_query(
            """SELECT a.created_at, a.patient_id, p.name, p.room_number, a.message, a.status, a.resolved_at, a.video_filename 
               FROM alerts a JOIN patients p ON a.patient_id = p.patient_id 
               WHERE p.hospital_name = ? 
               ORDER BY a.created_at DESC""",
            (hospital_name,)
        )
        history = []
        for r in rows:
            created_at_val = r[0].strftime("%Y-%m-%d %H:%M:%S") if hasattr(r[0], 'strftime') else str(r[0])
            resolved_at_val = r[6].strftime("%Y-%m-%d %H:%M:%S") if (r[6] and hasattr(r[6], 'strftime')) else (str(r[6]) if r[6] else "-")
            history.append({
                "created_at": created_at_val,
                "patient_id": r[1],
                "name": r[2],
                "room_number": r[3],
                "message": r[4],
                "status": r[5],
                "resolved_at": resolved_at_val,
                "video_filename": r[7]
            })
        return history
