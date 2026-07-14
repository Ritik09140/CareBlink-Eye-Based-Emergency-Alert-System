import os
import logging
from logging.handlers import RotatingFileHandler

# Ensure logs directory exists
LOGS_DIR = os.path.join(os.getcwd(), "logs")
os.makedirs(LOGS_DIR, exist_ok=True)

# Common Formatter
formatter = logging.Formatter(
    '[%(asctime)s] %(levelname)s in %(module)s (%(threadName)s): %(message)s'
)

def setup_logger(name, filename, level=logging.INFO):
    """Utility function to setup a logger writing to a rotating file."""
    log_file = os.path.join(LOGS_DIR, filename)
    handler = RotatingFileHandler(log_file, maxBytes=10*1024*1024, backupCount=5, encoding="utf-8")
    handler.setFormatter(formatter)
    
    logger = logging.getLogger(name)
    logger.setLevel(level)
    # Avoid duplicate handlers if setup is called multiple times
    if not logger.handlers:
        logger.addHandler(handler)
    return logger

# Define individual loggers
app_logger = setup_logger("app_logger", "app.log")
error_logger = setup_logger("error_logger", "error.log", level=logging.ERROR)
camera_logger = setup_logger("camera_logger", "camera.log")
db_logger = setup_logger("db_logger", "database.log")
