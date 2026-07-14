import os
import cv2
import time
import math
import threading
import requests
import urllib.request
from models.db_models import PatientModel, AlertModel
from services.notification_service import NotificationService
from utils.logger import camera_logger, error_logger

# Global camera tracking variable
camera_instance = None
last_blink_time = 0.0

class VideoCamera:
    def __init__(self, patient_id="PT-2045"):
        self.patient_id = patient_id
        camera_logger.info(f"Initializing VideoCamera stream for patient: {patient_id}")
        
        # Try DirectShow first on Windows, fallback to default
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
        self.records_dir = os.path.join(os.getcwd(), "all records")
        os.makedirs(self.records_dir, exist_ok=True)
        
        # Load custom patient profile
        if patient_id != "TEMP":
            p = PatientModel.get_by_id(patient_id)
            if p:
                self.EAR_THRESHOLD = float(p["ear_threshold"]) if p["ear_threshold"] is not None else 0.22
                self.baseline_ear = float(p["baseline_ear"]) if p["baseline_ear"] is not None else 0.28
                self.pupil_distance = float(p["pupil_distance"]) if p["pupil_distance"] is not None else 60.0
                camera_logger.info(f"Loaded customized metrics for {patient_id}: Threshold={self.EAR_THRESHOLD:.3f}, Baseline={self.baseline_ear:.3f}")
                
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
        
        # Launch frame grabber thread
        self.thread = threading.Thread(target=self.update, args=())
        self.thread.daemon = True
        self.thread.start()
        
    def ensure_model_exists(self):
        MODEL_FILE = "face_landmarker.task"
        MODEL_URL = "https://storage.googleapis.com/mediapipe-models/face_landmarker/face_landmarker/float16/1/face_landmarker.task"
        if not os.path.exists(MODEL_FILE):
            camera_logger.info("Downloading Face Landmarker model from Google CDN...")
            try:
                req = urllib.request.Request(
                    MODEL_URL, 
                    headers={'User-Agent': 'Mozilla/5.0'}
                )
                with urllib.request.urlopen(req) as response, open(MODEL_FILE, 'wb') as out_file:
                    out_file.write(response.read())
                camera_logger.info("MediaPipe Face Landmarker Model downloaded successfully.")
            except Exception as e:
                error_logger.error(f"Failed to download MediaPipe model: {e}")

    def stop(self):
        camera_logger.info("Stopping VideoCamera capture...")
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
        global last_blink_time
        
        while self.is_running:
            if not self.cap.isOpened():
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
                
                # Estimate Pupil Distance
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
                
                # Gaze direction offset
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
                
                if avg_gaze_offset < -0.09:
                    self.current_gaze = "right"
                elif avg_gaze_offset > 0.09:
                    self.current_gaze = "left"
                else:
                    self.current_gaze = "center"
                
                # Gaze shift triggers
                if self.current_gaze in ["left", "right"]:
                    if self.last_active_gaze is not None and self.current_gaze != self.last_active_gaze:
                        self.gaze_shift_timestamps.append(current_time)
                        camera_logger.info(f"Horizontal Gaze Shift: {self.last_active_gaze} -> {self.current_gaze}")
                    self.last_active_gaze = self.current_gaze
                
                color = (0, 255, 0)
                if avg_ear < self.EAR_THRESHOLD:
                    color = (0, 0, 255)
                    
                # Drawing details onto preview stream
                for idx in [self.LEFT_EYE_H[0], self.LEFT_EYE_H[1]] + [pt for pair in self.LEFT_EYE_V for pt in pair]:
                    pt = self.get_landmark_point(landmarks[idx], w, h)
                    cv2.circle(frame, pt, 2, color, -1)
                for idx in [self.RIGHT_EYE_H[0], self.RIGHT_EYE_H[1]] + [pt for pair in self.RIGHT_EYE_V for pt in pair]:
                    pt = self.get_landmark_point(landmarks[idx], w, h)
                    cv2.circle(frame, pt, 2, color, -1)
                
                cv2.circle(frame, p_left_iris, 3, (255, 255, 0), -1)
                cv2.circle(frame, p_right_iris, 3, (255, 255, 0), -1)
                    
                if avg_ear < self.EAR_THRESHOLD:
                    self.closed_frames += 1
                else:
                    if self.closed_frames >= self.EAR_CONSEC_FRAMES:
                        if self.blink_timestamps:
                            time_since_last = current_time - self.blink_timestamps[-1]
                            if time_since_last > 1.2:
                                self.blink_timestamps = [current_time]
                            else:
                                self.blink_timestamps.append(current_time)
                        else:
                            self.blink_timestamps.append(current_time)
                        last_blink_time = time.time()
                        
                        # Post local sync blink status asynchronously
                        def fire_blink_notice():
                            try:
                                requests.post("http://localhost:5000/api/blink", json={"patient_id": self.patient_id}, timeout=0.5)
                            except Exception:
                                pass
                        threading.Thread(target=fire_blink_notice, daemon=True).start()
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
                camera_logger.warning(f"EMERGENCY DETECTED for patient {self.patient_id}: {alert_msg}")
                
                # Start video recording
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
                    error_logger.error(f"Could not start video recording: {ev}")
                    
                # Create alert record
                AlertModel.trigger(self.patient_id, alert_msg, video_filename_val)
                
                # Dispatch notification
                p = PatientModel.get_by_id(self.patient_id)
                if p:
                    # Thread notifications so they don't block video logic
                    threading.Thread(
                        target=NotificationService.send_email_alert,
                        args=(p["name"], p["room_number"], alert_msg),
                        daemon=True
                    ).start()
                    threading.Thread(
                        target=NotificationService.send_sms_alert,
                        args=(p["name"], p["room_number"], alert_msg),
                        daemon=True
                    ).start()
                
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
                    error_logger.error(f"Failed to record frame: {ev}")
                    if self.video_writer:
                        self.video_writer.release()
                    self.video_writer = None
                    
            # Draw HUD
            cv2.rectangle(frame, (10, 10), (380, 160), (25, 20, 15), -1)
            cv2.rectangle(frame, (10, 10), (380, 160), (60, 60, 60), 1)
            
            cv2.putText(frame, "CareBlink Patient Monitor", (20, 30), cv2.FONT_HERSHEY_SIMPLEX, 0.6, (6, 182, 212), 2)
            cv2.putText(frame, f"Patient ID: {self.patient_id}", (20, 50), cv2.FONT_HERSHEY_SIMPLEX, 0.5, (255, 255, 255), 1)
            cv2.putText(frame, f"EAR: {avg_ear:.3f} (Thresh: {self.EAR_THRESHOLD:.2f})", (20, 70), cv2.FONT_HERSHEY_SIMPLEX, 0.5, (255, 255, 255), 1)
            cv2.putText(frame, f"Gaze: {self.current_gaze.upper()} (Offset: {avg_gaze_offset:+.3f})", (20, 90), cv2.FONT_HERSHEY_SIMPLEX, 0.5, (255, 255, 255), 1)
            cv2.putText(frame, f"Est. PD: {self.current_pd:.1f} mm", (20, 110), cv2.FONT_HERSHEY_SIMPLEX, 0.5, (255, 255, 255), 1)
            cv2.putText(frame, f"Blinks: {current_blinks} | Shifts: {current_gaze_shifts}", (20, 130), cv2.FONT_HERSHEY_SIMPLEX, 0.5, (255, 255, 255), 1)
                        
            if cooldown_active:
                cv2.putText(frame, "ALERT COOLDOWN", (20, 150), cv2.FONT_HERSHEY_SIMPLEX, 0.5, (0, 140, 255), 1)
            else:
                cv2.putText(frame, "MONITORING ACTIVE", (20, 150), cv2.FONT_HERSHEY_SIMPLEX, 0.5, (16, 185, 129), 1)
                            
            if (current_time - self.last_alert_time) < 4.0:
                if int(current_time * 4) % 2 == 0:
                    cv2.rectangle(frame, (0, 0), (w, h), (0, 0, 255), 8)
                    cv2.putText(frame, "!!! EMERGENCY ALERT !!!", (w // 2 - 180, h // 2), cv2.FONT_HERSHEY_SIMPLEX, 1.0, (0, 0, 255), 3)
                                
            ret_enc, jpeg = cv2.imencode('.jpg', frame)
            if ret_enc:
                with self.lock:
                    self.latest_frame = jpeg.tobytes()
                    
            time.sleep(0.04)  # ~25 FPS

def start_camera_stream(patient_id="PT-2045"):
    global camera_instance
    if camera_instance is not None:
        return True
    try:
        camera_instance = VideoCamera(patient_id)
        return True
    except Exception as e:
        error_logger.error(f"Failed to start camera: {e}")
        return False

def stop_camera_stream():
    global camera_instance
    if camera_instance is not None:
        try:
            camera_instance.stop()
            camera_instance = None
            return True
        except Exception as e:
            error_logger.error(f"Failed to stop camera: {e}")
    return False

def get_camera_status():
    global camera_instance
    return camera_instance
