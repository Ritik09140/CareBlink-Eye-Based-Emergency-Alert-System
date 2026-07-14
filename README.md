# CareBlink – Smart Eye Blink Patient Emergency Alert System

CareBlink is an assistive biometric technology platform designed for non-verbal patients (e.g., individuals with Locked-in Syndrome or severe Motor Neurone Disease) who retain control over their eye movements. By combining **Computer Vision (OpenCV + MediaPipe)** with a resilient **Flask web service**, CareBlink monitors eye aspect ratios and gaze shifts in real time to dispatch automated emergency notifications and telemetry logs to ward dashboards.

---

## 📂 Project Architecture

The project has been refactored from a monolithic app into a clean production architecture separating views, controllers, data models, and helper services:

```
CareBlink/
├── app.py                      # Application launcher and config registers
├── detector.py                 # Standalone Computer Vision webcam engine
├── requirements.txt            # Python dependencies with version constraints
├── Dockerfile                  # Container build directives
├── docker-compose.yml          # Container multi-service orchestration definition
├── Procfile                    # Deployment service command file
├── runtime.txt                 # Target Python runtime specs
├── deployment.md               # Cloud hosting setup procedures
├── .env.example                # Sample environment configuration template
├── config/
│   └── config.py               # Environment loader and security setups
├── database/
│   └── connection.py           # SQL dialect mapper and SQLite fallback loop
├── models/
│   └── db_models.py            # Data entity mapping for Hospitals, Patients, and Alerts
├── routes/
│   ├── auth_routes.py          # Blueprints for Operator login/logout and registration
│   ├── api_routes.py           # REST APIs for telemetry, calibration, and incidents
│   └── view_routes.py          # Renders main templates and serves video clips
├── services/
│   ├── camera_service.py       # Decoupled CV camera loop and MediaPipe interface
│   └── notification_service.py # Email and SMS alert dispatchers
├── utils/
│   ├── logger.py               # Custom log streams (app, camera, db, error)
│   └── security.py             # Password verification, sanitization, and input validators
├── templates/
│   ├── login.html              # Secure Bootstrap 5 login/register interface
│   └── index.html              # Multi-Dashboard Operator Portal template
├── static/
│   ├── css/
│   │   └── style.css           # Premium Dark Mode, glassmorphic layout rules
│   └── js/
│       └── dashboard.js        # Event listeners, Web Audio sirens, Chart.js, SheetJS, jsPDF
├── logs/                       # Folder containing runtime logger outputs
└── tests/
    ├── test_db.py              # Test suite for DB dialects
    ├── test_auth.py            # Test suite for auth credentials and filters
    ├── test_api.py             # Test suite for JSON APIs
    └── test_detector.py        # Offline eye tracking algorithms calculations test
```

---

## 🛠️ Prerequisites & Installation

### 1. Python Environment
Ensure you have **Python 3.8+** installed:
```bash
python --version
```

### 2. Install Project Dependencies
Install all required packages:
```bash
pip install -r requirements.txt
```

### 3. Database Resilience
CareBlink features a dual-database driver:
- It automatically detects and connects to a local MySQL instance based on your `.env` settings.
- If MySQL is unavailable, it **automatically falls back to SQLite** (`careblink.db`), creating the database and seeding tables with zero config.

To set up MySQL manually, verify your `.env` contains:
```env
DB_HOST=localhost
DB_USER=root
DB_PASSWORD=your_mysql_password
DB_NAME=careblink
```

---

## 🚀 Running the Project

### Step 1: Launch the Flask Server
```bash
python app.py
```
Open **`http://127.0.0.1:5000`** in your browser.
Log in with the default operator credentials:
- **Mobile Number:** `1234567890` (or `doctor`)
- **Password:** `password123`

### Step 2: Triggering Eye Calibration
1. Navigate to the **Patients Registry** tab.
2. Click **Scan Eyes & Auto-Fill**.
3. Look straight at your camera. The system will perform an automated 3.5-second scan to calculate your **baseline EAR** and **Pupil Distance** parameters.
4. Click **Apply & Close** to auto-fill the registry form.
5. Click **Register Patient** to commit the patient profile.

### Step 3: Simulating Emergency Signals
1. Select the registered patient from the dropdown on the **Live Monitor** tab and click **Start**.
2. Blink **5 times rapidly within 5 seconds**.
3. The video stream will outline a red **`!!! EMERGENCY ALERT !!!`** banner and record a 5-second telemetry clip.
4. The dashboard will trigger:
   - A strobing **Red Virtual Bulb**.
   - An active wailing **Emergency Siren** (Web Audio API).
   - An **Emergency Toast Notification**.
   - Email/SMS notifications to shift physicians.
5. Click **Dismiss Alarm** to reset the system.

---

## 📊 Feature Dashboards

The portal provides segmented dashboard consoles accessible from the sidebar:
- **Live Monitor Dashboard:** Visual telemetry feeds, neural thought decoder (translates blink counts to message intents), and emergency panels.
- **Patients Registry:** Database management console with eye calibration scanner and Excel spreadsheets exporting tools.
- **Alert Logs:** Incidents history tracker equipped with filterable tables and Excel export capabilities.
- **Hospital Records:** Segregated data directories by facility showcasing saved **Video Telemetry Clips**.
- **Doctor Portal:** Configures physicians shift contact details and sensitivity sliders for the OpenCV calibration.
- **Patient Telemetry:** Displays EAR tracking vectors in real time on Chart.js line graphs.
- **Emergency Siren HUD:** High-visibility layout meant for nurse station terminals featuring flashing warning indicators.
- **Admin Console:** Terminal logging viewer and dialect monitoring parameters.

---

## 🧪 Verification & Automated Testing

A dedicated test suite verifies app integrity before committing changes:
```bash
python -m unittest discover -s tests -p "test_*.py"
```

---

## 🚢 Deployment Guide

Refer to [deployment.md](file:///z:/CareBlink%20%E2%80%93%20Smart%20Eye-Based%20Patient%20Emergency%20Alert%20System/deployment.md) for step-by-step guidance on running CareBlink inside **Docker Compose** or deploying to cloud platforms like **Render**, **Railway**, or **PythonAnywhere**.
