import time
import random
import string
from flask import Blueprint, request, jsonify, session
from models.db_models import PatientModel, AlertModel
from services.camera_service import start_camera_stream, stop_camera_stream, get_camera_status, last_blink_time
from utils.security import SecurityHelper
from database.connection import db

api_bp = Blueprint('api', __name__)

def login_required_json(f):
    from functools import wraps
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if 'logged_in' not in session:
            return jsonify({"success": False, "message": "Unauthorized access. Please login."}), 401
        return f(*args, **kwargs)
    return decorated_function

@api_bp.route('/api/camera/start', methods=['POST'])
@login_required_json
def start_camera():
    data = request.json or {}
    patient_id = SecurityHelper.sanitize_string(data.get('patient_id', 'PT-2045'))
    success = start_camera_stream(patient_id)
    return jsonify({"success": success})

@api_bp.route('/api/camera/stop', methods=['POST'])
@login_required_json
def stop_camera():
    success = stop_camera_stream()
    return jsonify({"success": success})

@api_bp.route('/api/camera/status', methods=['GET'])
@login_required_json
def camera_status():
    cam = get_camera_status()
    is_running = cam is not None
    
    current_ear = 0.0
    current_blinks = 0
    patient_id = "N/A"
    patient_name = "N/A"
    patient_age = "N/A"
    room_number = "N/A"
    medical_condition = "N/A"
    mind_thoughts = "Calm and resting."
    ear_threshold = 0.22
    baseline_ear = 0.28
    pupil_distance = 60.0
    face_detected = False
    current_pd = 60.0
    current_gaze = "center"
    
    if is_running:
        current_ear = cam.get_current_ear()
        current_blinks = cam.get_current_blinks()
        patient_id = cam.patient_id
        face_detected = cam.face_detected
        current_pd = getattr(cam, 'current_pd', 60.0)
        current_gaze = getattr(cam, 'current_gaze', 'center')
        
        p = PatientModel.get_by_id(patient_id)
        if p:
            patient_name = p["name"]
            patient_age = p["age"]
            room_number = p["room_number"]
            medical_condition = p["medical_condition"]
            ear_threshold = float(p["ear_threshold"]) if p["ear_threshold"] is not None else 0.22
            baseline_ear = float(p["baseline_ear"]) if p["baseline_ear"] is not None else 0.28
            pupil_distance = float(p["pupil_distance"]) if p["pupil_distance"] is not None else 60.0
            mind_thoughts = p["mind_thoughts"] if p["mind_thoughts"] is not None else "Calm and resting."

    return jsonify({
        "is_running": is_running,
        "current_ear": round(current_ear, 3),
        "current_blinks": current_blinks,
        "patient_id": patient_id,
        "patient_name": patient_name,
        "patient_age": patient_age,
        "room_number": room_number,
        "medical_condition": medical_condition,
        "mind_thoughts": mind_thoughts,
        "ear_threshold": round(ear_threshold, 3),
        "baseline_ear": round(baseline_ear, 3),
        "pupil_distance": round(pupil_distance, 1),
        "current_pd": round(current_pd, 1),
        "current_gaze": current_gaze,
        "face_detected": face_detected
    })

@api_bp.route('/api/patient/<patient_id>/threshold', methods=['GET'])
def patient_threshold(patient_id):
    p = PatientModel.get_by_id(patient_id)
    if p:
        return jsonify({
            "success": True,
            "ear_threshold": p["ear_threshold"],
            "baseline_ear": p["baseline_ear"],
            "pupil_distance": p["pupil_distance"]
        })
    return jsonify({"success": False, "message": "Patient not found"}), 404

@api_bp.route('/api/camera/scan_calibration', methods=['POST'])
@login_required_json
def scan_calibration():
    # Attempt to open local stream if offline
    cam = get_camera_status()
    temp_camera = False
    if cam is None:
        success = start_camera_stream("TEMP")
        if not success:
            return jsonify({"success": False, "message": "Failed to initialize calibration webcam."}), 500
        temp_camera = True
        time.sleep(1.5)  # Warm up delay
        cam = get_camera_status()
        
    ears = []
    pds = []
    start_time = time.time()
    
    # Collect frames for 3.5 seconds
    while time.time() - start_time < 3.5:
        if cam and cam.face_detected:
            ears.append(cam.current_ear)
            if hasattr(cam, 'current_pd'):
                pds.append(cam.current_pd)
        time.sleep(0.1)
        
    if temp_camera:
        stop_camera_stream()
        
    if len(ears) < 10:
        return jsonify({"success": False, "message": "Face not detected. Ensure lighting is clear and look straight ahead."}), 400
        
    valid_ears = [e for e in ears if e >= 0.16]
    if not valid_ears:
        valid_ears = ears
    baseline_ear = sum(valid_ears) / len(valid_ears)
    ear_threshold = baseline_ear * 0.75
    avg_pd = sum(pds) / len(pds) if pds else 60.0
    
    first_names = ["Jayraj", "Kabir", "Vihaan", "Aditya", "Sai", "Arjun", "Aryan", "Reyansh", "Krishna", "Atharva", "Rohan"]
    last_names = ["Khanguda", "Sharma", "Verma", "Gupta", "Patel", "Mehta", "Singh", "Joshi", "Rao", "Nair"]
    name = f"{random.choice(first_names)} {random.choice(last_names)}"
    
    rand_suffix = ''.join(random.choices(string.ascii_uppercase + string.digits, k=4))
    patient_id = f"PT-EYE-{rand_suffix}"
    
    age = int(22 + (avg_pd % 12) * 4)
    room = f"Room {random.randint(101, 308)}"
    condition = "Locked-in Syndrome (Eye Responsive)" if avg_pd > 62 else "Severe MND (Standard Coordination)"
    
    thoughts = [
        "I need a glass of water.",
        "I feel cold, please adjust the room temperature.",
        "I am feeling okay, thank you.",
        "Please call the nurse, I feel slightly uncomfortable.",
        "I would like to rest for a while.",
        "The lighting in the room is too bright."
    ]
    
    return jsonify({
        "success": True,
        "patient_id": patient_id,
        "name": name,
        "baseline_ear": round(baseline_ear, 3),
        "ear_threshold": round(ear_threshold, 3),
        "pupil_distance": round(avg_pd, 1),
        "age": age,
        "room_number": room,
        "medical_condition": condition,
        "mind_thoughts": random.choice(thoughts)
    })

@api_bp.route('/api/blink', methods=['POST'])
def record_blink():
    global last_blink_time
    last_blink_time = time.time()
    return jsonify({"success": True})

@api_bp.route('/api/patients', methods=['GET', 'POST'])
@login_required_json
def patients():
    if request.method == 'POST':
        data = request.json or {}
        patient_id = SecurityHelper.sanitize_string(data.get('patient_id', ''))
        name = SecurityHelper.sanitize_string(data.get('name', ''))
        age = int(data.get('age', 0))
        room_number = SecurityHelper.sanitize_string(data.get('room_number', ''))
        medical_condition = SecurityHelper.sanitize_string(data.get('medical_condition', ''))
        hospital_name = session.get('hospital_name', 'St. Jude Medical Center')
        
        ear_threshold = float(data.get('ear_threshold', 0.22))
        baseline_ear = float(data.get('baseline_ear', 0.28))
        pupil_distance = float(data.get('pupil_distance', 60.0))
        mind_thoughts = SecurityHelper.sanitize_string(data.get('mind_thoughts', 'Calm and resting.'))
        
        if not all([patient_id, name, age, room_number, medical_condition]):
            return jsonify({"success": False, "message": "All fields are required."}), 400
            
        try:
            PatientModel.create(
                patient_id, name, age, room_number, medical_condition, hospital_name,
                ear_threshold, baseline_ear, pupil_distance, mind_thoughts
            )
            return jsonify({"success": True, "message": "Patient registered successfully."})
        except Exception as e:
            return jsonify({"success": False, "message": str(e)}), 500
            
    # GET list
    try:
        patients_list = PatientModel.get_all()
        return jsonify(patients_list)
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@api_bp.route('/api/alerts', methods=['POST'])
def trigger_alert():
    data = request.json or {}
    patient_id = SecurityHelper.sanitize_string(data.get('patient_id', 'PT-2045'))
    message = SecurityHelper.sanitize_string(data.get('message', 'Emergency: 5 rapid eye blinks detected!'))
    video_filename = SecurityHelper.sanitize_string(data.get('video_filename', ''))
    
    # Check if patient exists
    p = PatientModel.get_by_id(patient_id)
    if not p:
        return jsonify({"success": False, "message": "Patient ID does not exist."}), 404
        
    try:
        AlertModel.trigger(patient_id, message, video_filename)
        return jsonify({"success": True, "message": "Alert recorded."})
    except Exception as e:
        return jsonify({"success": False, "message": str(e)}), 500

@api_bp.route('/api/alerts/active', methods=['GET'])
@login_required_json
def active_alerts():
    try:
        alert = AlertModel.get_active_alert()
        # Add db_dialect metadata to sync with client
        return jsonify({
            "has_active": alert is not None,
            "alert": alert,
            "last_blink_time": last_blink_time,
            "db_dialect": f"{db.db_engine.upper()} (Auto)"
        })
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@api_bp.route('/api/alerts/dismiss', methods=['POST'])
@login_required_json
def dismiss_alert():
    try:
        AlertModel.dismiss_all()
        return jsonify({"success": True})
    except Exception as e:
        return jsonify({"success": False, "message": str(e)}), 500

@api_bp.route('/api/alerts/history', methods=['GET'])
@login_required_json
def alerts_history():
    try:
        history = AlertModel.get_history(limit=15)
        return jsonify(history)
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@api_bp.route('/api/hospital/records', methods=['GET'])
@login_required_json
def hospital_records():
    hospital_name = session.get('hospital_name', 'St. Jude Medical Center')
    state = session.get('state', 'California')
    
    try:
        patients_list = PatientModel.get_by_hospital(hospital_name)
        alerts_list = AlertModel.get_by_hospital(hospital_name)
        return jsonify({
            "hospital_name": hospital_name,
            "state": state,
            "patients": patients_list,
            "alerts": alerts_list
        })
    except Exception as e:
        return jsonify({"error": str(e)}), 500
