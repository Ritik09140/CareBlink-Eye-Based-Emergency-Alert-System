import os
import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from utils.logger import app_logger, error_logger

class NotificationService:
    @staticmethod
    def send_email_alert(patient_name, room_number, message):
        """Sends an email notification via SMTP."""
        smtp_server = os.getenv("SMTP_SERVER")
        smtp_port = os.getenv("SMTP_PORT")
        smtp_user = os.getenv("SMTP_USER")
        smtp_password = os.getenv("SMTP_PASSWORD")
        smtp_to = os.getenv("SMTP_TO")

        if not all([smtp_server, smtp_port, smtp_user, smtp_password, smtp_to]):
            app_logger.warning("SMTP configuration is incomplete. Skipping email alert dispatch.")
            return False

        try:
            # Build Email content
            subject = f"🚨 EMERGENCY: CareBlink Patient alert for {patient_name} (Room {room_number})"
            body = f"""
            Emergency Alert Details:
            ------------------------
            Patient Name: {patient_name}
            Room/Bed: {room_number}
            Alert Message: {message}
            Timestamp: {os.times()}
            
            Please check the CareBlink dashboard immediately.
            """

            msg = MIMEMultipart()
            msg['From'] = smtp_user
            msg['To'] = smtp_to
            msg['Subject'] = subject
            msg.attach(MIMEText(body, 'plain'))

            # Setup server connection
            server = smtplib.SMTP(smtp_server, int(smtp_port))
            server.starttls()
            server.login(smtp_user, smtp_password)
            server.sendmail(smtp_user, smtp_to, msg.as_string())
            server.quit()
            
            app_logger.info(f"Successfully dispatched emergency email alert to {smtp_to}")
            return True
        except Exception as e:
            error_logger.error(f"Failed to send email alert: {e}")
            return False

    @staticmethod
    def send_sms_alert(patient_name, room_number, message):
        """SMS alert dispatch stub (e.g., Twilio integration)."""
        twilio_sid = os.getenv("TWILIO_ACCOUNT_SID")
        twilio_auth_token = os.getenv("TWILIO_AUTH_TOKEN")
        twilio_from = os.getenv("TWILIO_FROM_NUMBER")
        twilio_to = os.getenv("TWILIO_TO_NUMBER")

        if not all([twilio_sid, twilio_auth_token, twilio_from, twilio_to]):
            app_logger.warning("Twilio SMS configuration is incomplete. Skipping SMS alert dispatch.")
            return False

        try:
            # Twilio integration placeholder using requests (avoiding direct dependency on twilio helper package for simplicity)
            import requests
            url = f"https://api.twilio.com/2010-04-01/Accounts/{twilio_sid}/Messages.json"
            sms_body = f"CareBlink Emergency! Patient {patient_name} in {room_number}: {message}"
            
            payload = {
                "From": twilio_from,
                "To": twilio_to,
                "Body": sms_body
            }
            
            response = requests.post(url, data=payload, auth=(twilio_sid, twilio_auth_token), timeout=5)
            if response.status_code in [200, 201]:
                app_logger.info(f"Successfully dispatched emergency SMS to {twilio_to}")
                return True
            else:
                error_logger.error(f"Twilio API error: {response.text}")
                return False
        except Exception as e:
            error_logger.error(f"Failed to dispatch SMS alert: {e}")
            return False
