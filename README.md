# CareBlink – Smart Eye Blink Emergency Alert System

CareBlink is an assistive technology solution designed for non-verbal patients (e.g., individuals with Locked-in Syndrome or severe Motor Neurone Disease) who cannot speak but retain control over their eye movements. By combining **Computer Vision (OpenCV + MediaPipe)** with a **Flask web dashboard and MySQL**, CareBlink monitors eye blinks in real-time. If a patient blinks 5 times rapidly within 5 seconds, an emergency alert is triggered, stored in the database, and visual and auditory indicators are activated on the doctor's dashboard.

---

## 📂 Project Structure

```
CareBlink/
├── app.py                   # Flask server backend (handles API and sessions)
├── detector.py              # Python Computer Vision script (webcam monitor)
├── db_setup.sql             # SQL script for MySQL database & schema creation
├── requirements.txt         # Required Python packages
├── .env                     # Configuration file for Database credentials
├── templates/
│   ├── login.html           # Doctor Login screen (HTML layout)
│   └── index.html           # Doctor Dashboard console (HTML structure)
└── static/
    ├── css/
    │   └── style.css        # Premium custom styles (Glassmorphism & animations)
    └── js/
        └── dashboard.js     # Dashboard state manager, AJAX polling & synthesized buzzer
```

---

## 🛠️ Prerequisites & Installation

### 1. Python Environment
Make sure you have **Python 3.8+** installed on your system. You can verify it by opening your terminal/command prompt and running:
```bash
python --version
```

### 2. Install Project Dependencies
In your project directory, open your terminal and install all required python libraries:
```bash
pip install -r requirements.txt
```

### 3. Database Server Setup (MySQL)
CareBlink has a dual-database design. It will try to connect to your local MySQL server. If it is not running, **it will automatically fall back to SQLite** (which creates a local database file `careblink.db` in the workspace), requiring **zero configuration** for demo presentations.

To set up MySQL manually:
1. Open your MySQL command-line client or phpMyAdmin.
2. Open and run the `db_setup.sql` script to create the database schema:
   ```bash
   mysql -u root -p < db_setup.sql
   ```
3. (Optional) Adjust your database login details (host, user, password) inside the `.env` file:
   ```env
   DB_HOST=localhost
   DB_USER=root
   DB_PASSWORD=your_mysql_password
   DB_NAME=careblink
   ```

---

## 🚀 Running the Project

### Step 1: Start the Flask Web App
Run the Flask server:
```bash
python app.py
```
Open your web browser and go to: **`http://localhost:5000`**
- You will be redirected to the Login Screen.
- Use the demo doctor credentials:
  - **Username:** `doctor`
  - **Password:** `password123`

### Step 2: Start the Computer Vision Detector Script
In a *separate* terminal window, launch the eye blink tracker script:
```bash
python detector.py
```
- A prompt will ask you to enter a **Patient ID**. Press Enter to use the default profile (`PT-2045` for Arthur Dent) or enter another ID like `PT-3091`.
- A camera window will open showing your webcam feed.
- Center your face in the feed.

### Step 3: Trigger an Emergency Alert
1. Look at the camera window.
2. Blink **5 times quickly (within 5 seconds)**.
3. Observe the output in the camera terminal and on the frame HUD. An indicator will flash **`!!! EMERGENCY ALERT !!!`**.
4. Now check the Flask Web Dashboard in your browser. It will immediately:
   - Glow a **pulsing bright red** virtual bulb.
   - Play a repeating medical alarm buzzer (beeping sound).
   - Display the patient details, time, and room number.
5. Click **"Dismiss & Reset Alarm"** on the dashboard. The buzzer will stop, the virtual bulb will return to solid green, and the incident will be logged in the database.

---

## 📐 How It Works: Step-by-Step

### 1. Eye Aspect Ratio (EAR) Algorithm
The system utilizes **MediaPipe Face Mesh** to locate 468 3D landmarks on the patient's face. For the eyes, specific landmark coordinate indices are extracted:
* **Left Eye horizontal corners:** 33, 133
* **Left Eye vertical edges:** (160, 144), (159, 145), (158, 153)

To calculate whether an eye is open or closed, the **Eye Aspect Ratio (EAR)** is computed:

$$\text{EAR} = \frac{\|p_2 - p_6\| + \|p_3 - p_5\|}{2 \cdot \|p_1 - p_4\|}$$

Where:
* $p_2, p_3, p_5, p_6$ represent vertical coordinate pairs.
* $p_1, p_4$ represent the horizontal outer and inner corners.

When the eyes are open, the EAR values hover around **0.25 to 0.35**. When the eyes are closed, the EAR value drops rapidly to below **0.20**.

### 2. Time-Window Blink Counting
* **State Machine:** When the average EAR of both eyes drops below the threshold (`0.22`), the detector starts counting frames. If it stays closed for at least 2 frames and then opens (EAR rises above threshold), a blink is registered.
* **5 in 5 Rule:** The epoch of each blink is appended to a list. On every frame, the list is cleaned by keeping only blinks that happened in the last 5.0 seconds.
* If the length of the list reaches 5:
  - An emergency is triggered.
  - The script makes an HTTP `POST` request to the web application at `/api/alerts`.
  - A 10-second cooldown is enforced to prevent spamming.

### 3. Alert Propagation to Doctor's Dashboard
```
[Webcam & OpenCV] ──► [MediaPipe Face Mesh] ──► [Compute EAR]
                                                      │ (5 blinks / 5s)
                                                      ▼
[MySQL Log] ◄─── [Flask REST API (app.py)] ◄─── [HTTP POST Request]
                       │
                       ▼ (AJAX Polling /api/alerts/active)
[Browser Dashboard] ───► [Glow Bulb Red & Synthesize Web Audio Alarm]
```

* **Backend Handling:** The Flask endpoint `/api/alerts` accepts the POST request, verifies the patient ID in the database, and inserts a new alert record with the status `active`.
* **Frontend Polling:** The doctor's dashboard (`dashboard.js`) queries the `/api/alerts/active` endpoint every 1.5 seconds.
* **Audio Warning Synthesizer:** When an active alarm payload is received, the frontend uses the browser's built-in **Web Audio API** to generate double-beeps of 980 Hz synthetically, avoiding the need for audio files.
* **Dismissal:** When the doctor clicks "Dismiss", a request goes to `/api/alerts/dismiss` setting the alert status to `dismissed` and recording the resolution timestamp.
