from flask import current_app, request, jsonify, redirect, url_for, flash
from functools import wraps
from pathlib import Path
import os
from dotenv import load_dotenv
import logging
from cryptography.fernet import Fernet
import time
from datetime import datetime
from flask_login import current_user

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler('generated/logs/app.log'),
        logging.StreamHandler()
    ]
)

# === Rate Limiting ===
def rate_limit(limit=5, per=60):
    """Rate limiting decorator"""
    def decorator(f):
        requests = {}
        
        @wraps(f)
        def wrapped(*args, **kwargs):
            now = time.time()
            ip = request.remote_addr
            
            # Clean old requests
            requests[ip] = [req for req in requests.get(ip, []) if now - req < per]
            
            # Check rate limit
            if len(requests.get(ip, [])) >= limit:
                return jsonify({'error': 'Rate limit exceeded'}), 429
            
            # Add new request
            requests.setdefault(ip, []).append(now)
            
            return f(*args, **kwargs)
        return wrapped
    return decorator

# === CONFIG ===
class Config:
    def __init__(self):
        self.config_path = Path(__file__).parent / "blog_config.env"
        self.api_key_path = Path(__file__).parent / "api.key"
        self.load_config()

    def load_config(self):
        """Load configuration from environment file"""
        default_config = {
            'BASE_URL': '',
            'USERNAME': '',
            'APP_PASSWORD': '',
            'TOOL_PROMPT': '',
            'GENERAL_PROMPT': '',
            'GUIDE_PROMPT': '',
            'AUTO_SYNC': 'false',
            'SCHEDULED_SYNC': 'false',
            'SYNC_INTERVAL': '6',
            'AUTO_CLEANUP': 'false',
            'MAIL_SERVER': 'smtp.gmail.com',
            'MAIL_PORT': 587,
            'MAIL_USE_TLS': True,
            'MAIL_USERNAME': '',
            'MAIL_PASSWORD': '',
            'MAIL_DEFAULT_SENDER': '',
            'BACKUP_ENCRYPTION_KEY': Fernet.generate_key().decode()
        }

        if not self.config_path.exists():
            return default_config

        load_dotenv(self.config_path)
        config = default_config.copy()
        
        for key in default_config.keys():
            if key != 'OPENAI_API_KEY':
                config[key] = os.getenv(key, default_config[key])
        
        return config

    def save_config(self, config_data):
        """Save configuration to environment file"""
        try:
            with open(self.config_path, 'w') as f:
                for key, value in config_data.items():
                    if key != 'OPENAI_API_KEY':
                        f.write(f"{key}={value}\n")
            return True
        except Exception as e:
            logging.error(f"Failed to save configuration: {e}")
            return False

def save_sync_log(message):
    """Save a message to the sync log file"""
    try:
        log_dir = 'generated/logs'
        os.makedirs(log_dir, exist_ok=True)
        
        log_file = os.path.join(log_dir, 'sync.log')
        timestamp = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        
        with open(log_file, 'a', encoding='utf-8') as f:
            f.write(f"[{timestamp}] {message}\n")
            
    except Exception as e:
        logging.error(f"Failed to save sync log: {str(e)}")

def ensure_directories():
    """Ensure all required directories exist"""
    directories = [
        'user_data',
        'generated/logs',
        'generated/backups',
        'generated/topics'
    ]
    
    for directory in directories:
        os.makedirs(directory, exist_ok=True)

def get_user_data_dir(user_id):
    """Get the directory for user-specific data files"""
    data_dir = os.path.join('user_data', f'user_{user_id}')
    os.makedirs(data_dir, exist_ok=True)
    return data_dir

def create_backup_filename():
    """Create a unique backup filename with timestamp"""
    timestamp = datetime.now().strftime('%Y%m%d_%H%M')
    return f'backup_{timestamp}.json'

# Initialize configuration
config_manager = Config()

def admin_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if not current_user.is_authenticated or not getattr(current_user, 'is_admin', False):
            flash('You do not have permission to access this page.', 'danger')
            return redirect(url_for('index'))
        return f(*args, **kwargs)
    return decorated_function

def get_embedding_cached(text, api_key, cache):
    """Get embedding with caching"""
    # your implementation
    pass

def load_topic_embeddings():
    """Load topic embeddings"""
    # your implementation
    pass

def save_topic_embeddings(embeddings):
    """Save topic embeddings"""
    # your implementation
    pass 