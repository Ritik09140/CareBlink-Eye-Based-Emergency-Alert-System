import cv2
import sys
import time
import math
import os
import requests
import urllib.request

# Set stdout encoding to UTF-8 for Windows command prompt to avoid character display errors
if sys.platform.startswith('win'):
    import io
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')

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
        
    # Calculate EAR
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
    
    # Open Webcam
    cap = cv2.VideoCapture(0)
    if not cap.isOpened():
        print("[ERROR] Could not open webcam. Make sure your camera is connected.")
        sys.exit(1)
        
    # Tracking variables
    closed_frames = 0
    blink_timestamps = []
    last_alert_time = 0
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
        h, w, _ = frame.shape
        
        # Convert BGR to RGB for MediaPipe Tasks
        rgb_frame = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
        mp_image = mp.Image(image_format=mp.ImageFormat.SRGB, data=rgb_frame)
        
        # Run inference
        results = detector.detect(mp_image)
        
        current_time = time.time()
        avg_ear = 0.0
        
        if results.face_landmarks:
            landmarks = results.face_landmarks[0]
            
            # Calculate EAR for both eyes
            left_ear = calculate_ear(landmarks, LEFT_EYE_H, LEFT_EYE_V, w, h)
            right_ear = calculate_ear(landmarks, RIGHT_EYE_H, RIGHT_EYE_V, w, h)
            avg_ear = (left_ear + right_ear) / 2.0
            
            # Determine color for drawing based on state
            color = (0, 255, 0) # Green for normal open eyes
            if avg_ear < EAR_THRESHOLD:
                color = (0, 0, 255) # Red for closed eyes
                
            # Draw eye landmarks for visualization
            for idx in [LEFT_EYE_H[0], LEFT_EYE_H[1]] + [pt for pair in LEFT_EYE_V for pt in pair]:
                pt = get_landmark_point(landmarks[idx], w, h)
                cv2.circle(frame, pt, 2, color, -1)
                
            for idx in [RIGHT_EYE_H[0], RIGHT_EYE_H[1]] + [pt for pair in RIGHT_EYE_V for pt in pair]:
                pt = get_landmark_point(landmarks[idx], w, h)
                cv2.circle(frame, pt, 2, color, -1)
                
            # Blink counting logic
            if avg_ear < EAR_THRESHOLD:
                closed_frames += 1
            else:
                if closed_frames >= EAR_CONSEC_FRAMES:
                    # Eye closed long enough, then opened -> Register blink
                    blink_timestamps.append(current_time)
                    print(f"[*] Blink detected! (Total: {len(blink_timestamps)} in current window)")
                    
                    # Notify server about normal blink for real-time sound sync
                    try:
                        requests.post("http://localhost:5000/api/blink", json={"patient_id": patient_id}, timeout=0.5)
                    except Exception:
                        pass
                closed_frames = 0
                
        # Filter blink timestamps (only keep blinks in the last 5 seconds)
        blink_timestamps = [t for t in blink_timestamps if current_time - t <= ALARM_WINDOW_SEC]
        current_blinks = len(blink_timestamps)
        
        # Check for emergency alert condition
        cooldown_active = (current_time - last_alert_time) < COOLDOWN_SEC
        
        if current_blinks >= ALARM_BLINK_COUNT and not cooldown_active:
            print("\n!!! EMERGENCY ALERT TRIGGERED !!!")
            last_alert_time = current_time
            blink_timestamps = []
            
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

            # Send API Alert to Flask Web Server (including video filename)
            payload = {
                "patient_id": patient_id,
                "message": "Emergency: 5 rapid eye blinks detected from patient!",
                "video_filename": video_filename_val
            }
            try:
                response = requests.post("http://localhost:5000/api/alerts", json=payload, timeout=3)
                if response.status_code == 200:
                    print("[API SUCCESS] Emergency Alert POSTed successfully.")
            except Exception as e:
                print(f"[API FAILED] Could not contact Flask server: {e}")

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
        cv2.rectangle(frame, (10, 10), (380, 150), (25, 20, 15), -1)
        cv2.rectangle(frame, (10, 10), (380, 150), (60, 60, 60), 1)
        
        cv2.putText(frame, "CareBlink Patient Monitor", (20, 35), 
                    cv2.FONT_HERSHEY_SIMPLEX, 0.6, (6, 182, 212), 2)
        cv2.putText(frame, f"Patient ID: {patient_id}", (20, 60), 
                    cv2.FONT_HERSHEY_SIMPLEX, 0.5, (255, 255, 255), 1)
        cv2.putText(frame, f"Current EAR: {avg_ear:.3f}", (20, 85), 
                    cv2.FONT_HERSHEY_SIMPLEX, 0.5, (255, 255, 255), 1)
        cv2.putText(frame, "Blinks (5s Window): ", (20, 110), 
                    cv2.FONT_HERSHEY_SIMPLEX, 0.5, (255, 255, 255), 1)
        
        count_color = (0, 255, 0)
        if current_blinks >= 3:
            count_color = (0, 255, 255)
        if current_blinks >= 4:
            count_color = (0, 0, 255)
        cv2.putText(frame, str(current_blinks), (180, 110), 
                    cv2.FONT_HERSHEY_SIMPLEX, 0.6, count_color, 2)
                    
        if cooldown_active:
            cv2.putText(frame, "ALERT COOLDOWN", (20, 135), 
                        cv2.FONT_HERSHEY_SIMPLEX, 0.5, (0, 140, 255), 1)
        else:
            cv2.putText(frame, "MONITORING ACTIVE", (20, 135), 
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
