import os
from flask import Flask, jsonify, render_template
from config.config import Config
from database.connection import db
from routes.auth_routes import auth_bp
from routes.api_routes import api_bp
from routes.view_routes import views_bp
from utils.logger import app_logger, error_logger

app = Flask(__name__)
app.config.from_object(Config)

# Auto-create necessary directories
os.makedirs(app.config["UPLOAD_FOLDER"], exist_ok=True)
os.makedirs(os.path.join(os.getcwd(), "all records"), exist_ok=True)

# Register Blueprints
app.register_blueprint(auth_bp)
app.register_blueprint(api_bp)
app.register_blueprint(views_bp)

# Global Error Handlers
@app.errorhandler(404)
def page_not_found(e):
    app_logger.info(f"404 page redirect: {request.url if 'request' in globals() else 'URL not resolved'}")
    return render_template('index.html'), 404

@app.errorhandler(500)
def server_error(e):
    error_logger.error(f"Internal server exception: {e}")
    return jsonify({"success": False, "message": "An internal server error occurred."}), 500

@app.teardown_appcontext
def shutdown_session(exception=None):
    pass

if __name__ == '__main__':
    port = app.config["FLASK_PORT"]
    debug = app.config["DEBUG"]
    app_logger.info(f"Launching CareBlink Flask server on port: {port} with debug={debug}")
    app.run(host="0.0.0.0", port=port, debug=debug)
