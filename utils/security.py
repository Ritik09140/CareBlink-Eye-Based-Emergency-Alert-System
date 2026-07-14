import re
from werkzeug.security import generate_password_hash, check_password_hash
from utils.logger import error_logger

class SecurityHelper:
    @staticmethod
    def hash_password(password):
        """Hashes the user password using pbkdf2:sha256."""
        return generate_password_hash(password, method='pbkdf2:sha256')

    @staticmethod
    def verify_password(hash_val, password):
        """Verifies clear password against stored hash."""
        if not hash_val or not password:
            return False
        return check_password_hash(hash_val, password)

    @staticmethod
    def sanitize_string(text, max_len=255):
        """Sanitizes text inputs by stripping trailing spaces and removing invalid tags."""
        if not text:
            return ""
        # Strip string
        cleaned = str(text).strip()
        # Prevent length overflow
        if len(cleaned) > max_len:
            cleaned = cleaned[:max_len]
        # Strip potentially malicious characters
        cleaned = re.sub(r'[<>]', '', cleaned)
        return cleaned

    @staticmethod
    def validate_mobile(mobile_no):
        """Validates standard mobile formats (digits, length between 8 and 15)."""
        if not mobile_no:
            return False
        return bool(re.match(r'^\+?[0-9]{8,15}$', str(mobile_no).strip()))

    @staticmethod
    def allowed_file(filename, allowed_extensions={'mp4', 'jpg', 'jpeg', 'png'}):
        """Checks if a file extension is allowed."""
        return '.' in filename and \
               filename.rsplit('.', 1)[1].lower() in allowed_extensions
