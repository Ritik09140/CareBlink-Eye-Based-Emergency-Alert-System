import cv2
import sys
import time
import math
import os
import requests
import urllib.request
import threading

# Set stdout encoding to UTF-8 for Windows command prompt to avoid character display errors
if sys.platform.startswith('win'):
    import io
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')

def send_api_request_async(url, payload, timeout=1.0):
    """Sends a POST request in a separate daemon thread to avoid blocking the main OpenCV video loop."""
    def run():
        try:
            requests.post(url, json=payload, timeout=timeout)
        except Exception:
            pass
    threading.Thread(target=run, daemon=True).start()

# Coordinates indexes for MediaPipe Face Mesh
# Left Eye landmarks
LEFT_EYE_H = (33, 133)
LEFT_EYE_V = [(160, 144), (159, 145), (158, 153)]

# Right Eye landmarks
RIGHT_EYE_H = (362, 263)
RIGHT_EYE_V = [(385, 380), (386, 373), (387, 374)]

# EAR parameters
EAR_THRESHOLD = 0.22      # Threshold below which eye is considered closed
EAR_CONSEC_FRAMES = 2     # Number of consecutive frames the eye must remain closed to register a blink

# Alarm config
ALARM_BLINK_COUNT = 5     # Number of blinks required
ALARM_WINDOW_SEC = 5.0    # Time window (in seconds) to count blinks
COOLDOWN_SEC = 10.0       # Cooldown period after triggering alert to avoid duplicate posts

MODEL_FILE = "face_landmarker.task"
MODEL_URL = "https://storage.googleapis.com/mediapipe-models/face_landmarker/face_landmarker/float16/1/face_landmarker.task"

def download_model():
    if not os.path.exists(MODEL_FILE):
        print(f"\n[*] Downloading Face Landmarker model file ({MODEL_FILE}) from Google APIs CDN...")
        print("    Please wait, this is a one-time setup (approx. 5.6 MB)...")
        try:
            req = urllib.request.Request(
                MODEL_URL, 
                headers={'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64)'}
            )
            with urllib.request.urlopen(req) as response, open(MODEL_FILE, 'wb') as out_file:
                out_file.write(response.read())
            print("[✔] Model downloaded successfully.")
        except Exception as e:
            print(f"[ERROR] Failed to download model file: {e}")
            print(f"Please download the file manually from: {MODEL_URL} and place it in this folder.")
            sys.exit(1)

def get_landmark_point(landmark, img_width, img_height):
    return (int(landmark.x * img_width), int(landmark.y * img_height))

def distance(p1, p2):
    return math.sqrt((p1[0] - p2[0])**2 + (p1[1] - p2[1])**2)

def calculate_ear(landmarks, horizontal_idx, vertical_idxs, w, h):
    # Get horizontal points
    h_p1 = get_landmark_point(landmarks[horizontal_idx[0]], w, h)
    h_p2 = get_landmark_point(landmarks[horizontal_idx[1]], w, h)
    
    # Calculate vertical distances
    v_dists = []
    for top_idx, bot_idx in vertical_idxs:
        top_p = get_landmark_point(landmarks[top_idx], w, h)
        bot_p = get_landmark_point(landmarks[bot_idx], w, h)
        v_dists.append(distance(top_p, bot_p))
    
    # Horizontal distance
    h_dist = distance(h_p1, h_p2)
    
    if h_dist == 0:
        return 0.0
        
    avg_v_dist = sum(v_dists) / len(vertical_idxs)
    return avg_v_dist / h_dist

def main():
    print("=" * 60)
    print("      CareBlink - Smart Eye Blink Emergency Alert System")
    print("                     [Computer Vision Engine]")
    print("=" * 60)
    
    # Ensure model file exists
    download_model()
    
    # Check if Patient ID is passed as command-line argument (useful for auto-launching subprocess)
    if len(sys.argv) > 1:
        patient_id = sys.argv[1].strip()
    else:
        # Prompt for Patient ID
        patient_id = input("\nEnter Patient ID to monitor [Default: PT-2045]: ").strip()
        if not patient_id:
            patient_id = "PT-2045"
        
    print(f"\n[*] Initializing webcam stream... Monitoring Patient: {patient_id}")
    
    # Fetch personalized config from Flask backend if available
    ear_threshold_val = EAR_THRESHOLD
    baseline_ear_val = 0.28
    pupil_distance_val = 60.0
    try:
        resp = requests.get(f"http://localhost:5000/api/patient/{patient_id}/threshold", timeout=2.0)
        if resp.status_code == 200:
            p_data = resp.json()
            if p_data.get("success"):
                ear_threshold_val = float(p_data["ear_threshold"])
                baseline_ear_val = float(p_data["baseline_ear"])
                pupil_distance_val = float(p_data["pupil_distance"])
                print(f"[✔] Loaded personalized metrics for {patient_id}: Thresh={ear_threshold_val:.3f}, Baseline={baseline_ear_val:.3f}, PD={pupil_distance_val:.1f}mm")
    except Exception as e:
        print(f"[!] Could not fetch personalized metrics from server (using default 0.22): {e}")

    try:
        import mediapipe as mp
        from mediapipe.tasks import python
        from mediapipe.tasks.python import vision
    except ImportError:
        print("\n[ERROR] MediaPipe is not installed. Please run: pip install mediapipe")
        sys.exit(1)
        
    # Initialize MediaPipe Face Landmarker Tasks API
    base_options = python.BaseOptions(model_asset_path=MODEL_FILE)
    options = vision.FaceLandmarkerOptions(
        base_options=base_options,
        output_face_blendshapes=False,
        output_facial_transformation_matrixes=False,
        num_faces=1
    )
    detector = vision.FaceLandmarker.create_from_options(options)
    
    # Open Webcam (try DirectShow first on Windows for stability/speed, fallback to default)
    cap = cv2.VideoCapture(0, cv2.CAP_DSHOW)
    if not cap.isOpened():
        cap = cv2.VideoCapture(0)
    if not cap.isOpened():
        print("[ERROR] Could not open webcam. Make sure your camera is connected.")
        sys.exit(1)
        
    # Tracking variables
    closed_frames = 0
    blink_timestamps = []
    gaze_shift_timestamps = []
    last_alert_time = 0
    last_active_gaze = None
    current_gaze = "center"
    current_pd = 60.0
    
    records_dir = "all records"
    os.makedirs(records_dir, exist_ok=True)
    video_writer = None
    record_frames_remaining = 0
    
    print("\n[✔] System initialized. Press 'q' in the camera window to exit.")
    print("    Keep your face centered. Rapidly blink 5 times within 5 seconds to test.")
    print("-" * 60)
    
    while cap.isOpened():
        ret, frame = cap.read()
        if not ret:
            break
            
        # Flip the frame horizontally for mirror view
        frame = cv2.flip(frame, 1)
        
        # Resize frame to standard width of 640 to ensure super smooth CPU performance (no lag/freezing)
        target_width = 640
        h_orig, w_orig, _ = frame.shape
        if w_orig > target_width:
            aspect_ratio = h_orig / w_orig
            target_height = int(target_width * aspect_ratio)
            frame = cv2.resize(frame, (target_width, target_height))
            
        h, w, _ = frame.shape
        
        # Convert BGR to RGB for MediaPipe Tasks
        rgb_frame = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
        mp_image = mp.Image(image_format=mp.ImageFormat.SRGB, data=rgb_frame)
        
        # Run inference
        results = detector.detect(mp_image)
        
        current_time = time.time()
        avg_ear = 0.0
        avg_gaze_offset = 0.0
        
        if results.face_landmarks:
            landmarks = results.face_landmarks[0]
            
            # Calculate EAR for both eyes
            left_ear = calculate_ear(landmarks, LEFT_EYE_H, LEFT_EYE_V, w, h)
            right_ear = calculate_ear(landmarks, RIGHT_EYE_H, RIGHT_EYE_V, w, h)
            avg_ear = (left_ear + right_ear) / 2.0
            
            # Calculate Pupil Distance (estimated PD in mm)
            # left iris: 468, right iris: 473, face left: 234, face right: 454
            p_left_iris = get_landmark_point(landmarks[468], w, h)
            p_right_iris = get_landmark_point(landmarks[473], w, h)
            p_face_left = get_landmark_point(landmarks[234], w, h)
            p_face_right = get_landmark_point(landmarks[454], w, h)
            d_pupils = distance(p_left_iris, p_right_iris)
            w_face = distance(p_face_left, p_face_right)
            if w_face > 0:
                current_pd = (d_pupils / w_face) * 140.0
            else:
                current_pd = 60.0
                
            # Gaze Offset calculation
            left_eye_center_x = (landmarks[33].x + landmarks[133].x) / 2.0
            left_eye_center_y = (landmarks[33].y + landmarks[133].y) / 2.0
            right_eye_center_x = (landmarks[362].x + landmarks[263].x) / 2.0
            right_eye_center_y = (landmarks[362].y + landmarks[263].y) / 2.0
            
            left_eye_width = distance(get_landmark_point(landmarks[33], w, h), get_landmark_point(landmarks[133], w, h))
            right_eye_width = distance(get_landmark_point(landmarks[362], w, h), get_landmark_point(landmarks[263], w, h))
            
            p_left_center = (int(left_eye_center_x * w), int(left_eye_center_y * h))
            p_right_center = (int(right_eye_center_x * w), int(right_eye_center_y * h))
            
            left_gaze_offset = (p_left_iris[0] - p_left_center[0]) / left_eye_width if left_eye_width > 0 else 0.0
            right_gaze_offset = (p_right_iris[0] - p_right_center[0]) / right_eye_width if right_eye_width > 0 else 0.0
            avg_gaze_offset = (left_gaze_offset + right_gaze_offset) / 2.0
            
            # Classification of gaze state
            if avg_gaze_offset < -0.09:
                current_gaze = "right"
            elif avg_gaze_offset > 0.09:
                current_gaze = "left"
            else:
                current_gaze = "center"
                
            # Gaze shifts
            if current_gaze in ["left", "right"]:
                if last_active_gaze is not None and current_gaze != last_active_gaze:
                    gaze_shift_timestamps.append(current_time)
                    print(f"[*] Horizontal Gaze Shift: {last_active_gaze} -> {current_gaze}")
                last_active_gaze = current_gaze
            
            # Determine color for drawing based on state
            color = (0, 255, 0) # Green for normal open eyes
            if avg_ear < ear_threshold_val:
                color = (0, 0, 255) # Red for closed eyes
                
            # Draw eye landmarks for visualization
            for idx in [LEFT_EYE_H[0], LEFT_EYE_H[1]] + [pt for pair in LEFT_EYE_V for pt in pair]:
                pt = get_landmark_point(landmarks[idx], w, h)
                cv2.circle(frame, pt, 2, color, -1)
                
            for idx in [RIGHT_EYE_H[0], RIGHT_EYE_H[1]] + [pt for pair in RIGHT_EYE_V for pt in pair]:
                pt = get_landmark_point(landmarks[idx], w, h)
                cv2.circle(frame, pt, 2, color, -1)
                
            # Draw irises
            cv2.circle(frame, p_left_iris, 3, (255, 255, 0), -1)
            cv2.circle(frame, p_right_iris, 3, (255, 255, 0), -1)
                
            # Blink counting logic
            if avg_ear < ear_threshold_val:
                closed_frames += 1
            else:
                if closed_frames >= EAR_CONSEC_FRAMES:
                    # Stricter rapid blink timing check (<= 1.2s)
                    if blink_timestamps:
                        time_since_last = current_time - blink_timestamps[-1]
                        if time_since_last > 1.2:
                            blink_timestamps = [current_time]
                        else:
                            blink_timestamps.append(current_time)
                    else:
                        blink_timestamps.append(current_time)
                        
                    print(f"[*] Blink detected! (Total: {len(blink_timestamps)} in current window)")
                    send_api_request_async("http://localhost:5000/api/blink", {"patient_id": patient_id}, timeout=0.5)
                closed_frames = 0
                
        # Filter blink timestamps (only keep blinks in the last 5 seconds)
        blink_timestamps = [t for t in blink_timestamps if current_time - t <= ALARM_WINDOW_SEC]
        current_blinks = len(blink_timestamps)
        
        gaze_shift_timestamps = [t for t in gaze_shift_timestamps if current_time - t <= ALARM_WINDOW_SEC]
        current_gaze_shifts = len(gaze_shift_timestamps)
        
        # Check for emergency alert condition (5 blinks OR 4 gaze shifts)
        cooldown_active = (current_time - last_alert_time) < COOLDOWN_SEC
        triggered_by_blinks = current_blinks >= ALARM_BLINK_COUNT
        triggered_by_gaze = current_gaze_shifts >= 4
        
        if (triggered_by_blinks or triggered_by_gaze) and not cooldown_active:
            print("\n!!! EMERGENCY ALERT TRIGGERED !!!")
            last_alert_time = current_time
            blink_timestamps = []
            gaze_shift_timestamps = []
            
            alert_msg = "Emergency: 5 rapid eye blinks detected!" if triggered_by_blinks else "Emergency: Continuous horizontal eye movements detected!"
            
            # Setup video filename and path beforehand
            video_filename_val = None
            try:
                timestamp = time.strftime("%Y%m%d_%H%M%S")
                video_filename_val = f"alert_{patient_id}_{timestamp}.mp4"
                video_filepath = os.path.join(records_dir, video_filename_val)
                # mp4v is highly compatible for MP4 files in OpenCV
                fourcc = cv2.VideoWriter_fourcc(*'mp4v')
                fps = 15.0
                video_writer = cv2.VideoWriter(video_filepath, fourcc, fps, (w, h))
                record_frames_remaining = int(fps * 5.0) # record for 5 seconds
                print(f"[*] Started recording emergency alert video: {video_filepath}")
            except Exception as ev:
                print(f"[ERROR] Could not start video recording: {ev}")
 
            # Send API Alert to Flask Web Server (including video filename) (non-blocking thread)
            payload = {
                "patient_id": patient_id,
                "message": alert_msg,
                "video_filename": video_filename_val
            }
            send_api_request_async("http://localhost:5000/api/alerts", payload, timeout=3.0)
 
        # Write frame to video file if recording is active
        if video_writer is not None:
            try:
                # Save frame
                video_writer.write(frame)
                record_frames_remaining -= 1
                
                # Draw recording state indicator on the webcam frame
                cv2.circle(frame, (w - 20, 25), 8, (0, 0, 255), -1)
                cv2.putText(frame, "REC", (w - 60, 30), cv2.FONT_HERSHEY_SIMPLEX, 0.5, (0, 0, 255), 2)
                
                if record_frames_remaining <= 0:
                    video_writer.release()
                    video_writer = None
                    print("[*] Finished saving alert video to 'all records' folder.")
            except Exception as ev:
                print(f"[ERROR] Writing frame to video failed: {ev}")
                if video_writer:
                    video_writer.release()
                video_writer = None
                
        # Draw on-screen HUD
        cv2.rectangle(frame, (10, 10), (380, 160), (25, 20, 15), -1)
        cv2.rectangle(frame, (10, 10), (380, 160), (60, 60, 60), 1)
        
        cv2.putText(frame, "CareBlink Patient Monitor", (20, 30), 
                    cv2.FONT_HERSHEY_SIMPLEX, 0.6, (6, 182, 212), 2)
        cv2.putText(frame, f"Patient ID: {patient_id}", (20, 50), 
                    cv2.FONT_HERSHEY_SIMPLEX, 0.5, (255, 255, 255), 1)
        cv2.putText(frame, f"EAR: {avg_ear:.3f} (Thresh: {ear_threshold_val:.2f})", (20, 70), 
                    cv2.FONT_HERSHEY_SIMPLEX, 0.5, (255, 255, 255), 1)
        cv2.putText(frame, f"Gaze: {current_gaze.upper()} (Offset: {avg_gaze_offset:+.3f})", (20, 90), 
                    cv2.FONT_HERSHEY_SIMPLEX, 0.5, (255, 255, 255), 1)
        cv2.putText(frame, f"Est. PD: {current_pd:.1f} mm", (20, 110), 
                    cv2.FONT_HERSHEY_SIMPLEX, 0.5, (255, 255, 255), 1)
        cv2.putText(frame, f"Blinks: {current_blinks} | Shifts: {current_gaze_shifts}", (20, 130), 
                    cv2.FONT_HERSHEY_SIMPLEX, 0.5, (255, 255, 255), 1)
                    
        if cooldown_active:
            cv2.rectangle(frame, (10, 10), (380, 160), (0, 140, 255), 1)
            cv2.putText(frame, "ALERT COOLDOWN", (20, 150), 
                        cv2.FONT_HERSHEY_SIMPLEX, 0.5, (0, 140, 255), 1)
        else:
            cv2.putText(frame, "MONITORING ACTIVE", (20, 150), 
                        cv2.FONT_HERSHEY_SIMPLEX, 0.5, (16, 185, 129), 1)
 
        # Flashing outline
        if (current_time - last_alert_time) < 4.0:
            if int(current_time * 4) % 2 == 0:
                cv2.rectangle(frame, (0, 0), (w, h), (0, 0, 255), 8)
                cv2.putText(frame, "!!! EMERGENCY ALERT !!!", (w // 2 - 180, h // 2), 
                            cv2.FONT_HERSHEY_SIMPLEX, 1.0, (0, 0, 255), 3)
 
        cv2.imshow("CareBlink - Patient Eye Blink Detection", frame)
        key = cv2.waitKey(1) & 0xFF
        if key == ord('q'):
            break
            
    # Cleanup
    if video_writer is not None:
        video_writer.release()
    cap.release()
    cv2.destroyAllWindows()
    detector.close()
    print("\n[-] Camera stream closed. Exiting.")

if __name__ == '__main__':
    main()
