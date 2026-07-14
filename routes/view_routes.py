import time
from flask import Blueprint, render_template, redirect, url_for, session, Response, send_from_directory
from services.camera_service import get_camera_status
from utils.logger import app_logger

views_bp = Blueprint('views', __name__)

def login_required(f):
    from functools import wraps
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if 'logged_in' not in session:
            return redirect(url_for('auth.login'))
        return f(*args, **kwargs)
    return decorated_function

@views_bp.route('/')
@login_required
def index():
    return render_template('index.html')

@views_bp.route('/video_feed')
def video_feed():
    def gen():
        while True:
            cam = get_camera_status()
            if cam is None:
                break
            frame = cam.get_frame()
            if frame is not None:
                yield (b'--frame\r\n'
                       b'Content-Type: image/jpeg\r\n\r\n' + frame + b'\r\n')
            time.sleep(0.04)  # Limit to ~25 FPS
            
    return Response(gen(), mimetype='multipart/x-mixed-replace; boundary=frame')

@views_bp.route('/all_records/<path:filename>')
@login_required
def serve_record_video(filename):
    # Safe path serve from 'all records' folder
    import os
    records_dir = os.path.join(os.getcwd(), "all records")
    return send_from_directory(records_dir, filename)
