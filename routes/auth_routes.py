from flask import Blueprint, render_template, request, redirect, url_for, session, flash
from models.db_models import HospitalModel
from utils.security import SecurityHelper
from utils.logger import app_logger

auth_bp = Blueprint('auth', __name__)

@auth_bp.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        mobile_no = SecurityHelper.sanitize_string(request.form.get('mobile_no', ''))
        password = request.form.get('password', '').strip()
        
        # Backwards compatibility / Demo login bypass
        if (mobile_no == 'doctor' or mobile_no == '1234567890') and password == 'password123':
            session['logged_in'] = True
            session['hospital_name'] = "St. Jude Medical Center"
            session['state'] = "California"
            session['mobile_no'] = mobile_no
            session['role'] = 'admin'
            flash('Login successful (Demo mode)!', 'success')
            app_logger.info("Demo administrator logged in successfully.")
            
            # Start camera for default patient in the background
            from services.camera_service import start_camera_stream
            start_camera_stream("PT-2045")
            return redirect(url_for('views.index'))
            
        # Database credentials verification
        hosp = HospitalModel.get_by_mobile(mobile_no)
        if hosp:
            stored_hash = hosp['password']
            # Support both hashed and clear text for legacy seeds
            is_valid = SecurityHelper.verify_password(stored_hash, password) or (stored_hash == password)
            
            if is_valid:
                session['logged_in'] = True
                session['hospital_name'] = hosp['hospital_name']
                session['state'] = hosp['state']
                session['mobile_no'] = hosp['mobile_no']
                session['role'] = hosp.get('role', 'doctor')
                
                flash('Login successful!', 'success')
                app_logger.info(f"Hospital Operator login successful: {mobile_no}")
                
                from services.camera_service import start_camera_stream
                start_camera_stream("PT-2045")
                return redirect(url_for('views.index'))
        
        flash('Invalid Mobile Number or Password.', 'danger')
        app_logger.warning(f"Failed login attempt for mobile number: {mobile_no}")
            
    return render_template('login.html')

@auth_bp.route('/register', methods=['POST'])
def register():
    hospital_name = SecurityHelper.sanitize_string(request.form.get('hospital_name', ''))
    state = SecurityHelper.sanitize_string(request.form.get('state', ''))
    mobile_no = SecurityHelper.sanitize_string(request.form.get('mobile_no', ''))
    password = request.form.get('password', '').strip()
    role = SecurityHelper.sanitize_string(request.form.get('role', 'doctor'))
    
    if not all([hospital_name, state, mobile_no, password]):
        flash('All registration fields are required.', 'danger')
        return redirect(url_for('auth.login'))
        
    if not SecurityHelper.validate_mobile(mobile_no):
        flash('Invalid mobile number format. Use numeric values only.', 'danger')
        return redirect(url_for('auth.login'))
        
    # Check if user already exists
    if HospitalModel.get_by_mobile(mobile_no):
        flash('Registration failed: Mobile number already registered.', 'danger')
        return redirect(url_for('auth.login'))

    # Hash user password
    hashed_pwd = SecurityHelper.hash_password(password)
    
    try:
        HospitalModel.create(hospital_name, state, mobile_no, hashed_pwd, role)
        flash('Registration successful! Please login.', 'success')
        app_logger.info(f"New hospital registered: {hospital_name} ({state})")
    except Exception as e:
        flash(f'Registration failed: {e}', 'danger')
        
    return redirect(url_for('auth.login'))

@auth_bp.route('/logout')
def logout():
    mobile = session.get('mobile_no', 'Unknown')
    session.pop('logged_in', None)
    session.pop('hospital_name', None)
    session.pop('state', None)
    session.pop('mobile_no', None)
    session.pop('role', None)
    
    # Close active webcam stream
    from services.camera_service import stop_camera_stream
    stop_camera_stream()
    
    flash('You have been logged out successfully.', 'info')
    app_logger.info(f"Operator logged out: {mobile}")
    return redirect(url_for('auth.login'))
