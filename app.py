from flask import Flask, render_template, request, jsonify, flash, redirect, url_for, send_file
from flask_login import LoginManager, login_required, current_user
from models import User, init_db
from auth_routes import auth_bp
from generate_routes import generate_bp
from settings_routes import settings_bp
from utils import rate_limit
import os
import logging
from datetime import datetime, timedelta
import json
import sqlite3
from cryptography.fernet import Fernet
import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from email.mime.application import MIMEApplication
from flask_sqlalchemy import SQLAlchemy
from logging.handlers import RotatingFileHandler
from apscheduler.schedulers.background import BackgroundScheduler
from services import sync_wordpress_posts

app = Flask(__name__)
app.config['DEBUG'] = True  # Disable debug mode
app.config['TESTING'] = True

# Load configuration
def load_env(path):
    env = {}
    with open(path, "r", encoding="utf-8") as f:
        for line in f:
            if "=" in line:
                key, val = line.strip().split("=", 1)
                env[key] = val
    return env

# Load environment variables
config = load_env(os.path.join(os.path.dirname(__file__), "blog_config.env"))
app.config['SECRET_KEY'] = os.urandom(24)
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///users.db'
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
app.config['PERMANENT_SESSION_LIFETIME'] = timedelta(days=7)
app.config['RATE_LIMIT'] = '1000 per day'

# Only keep global config for email, etc.
app.config['MAIL_SERVER'] = config.get('MAIL_SERVER', '')
app.config['MAIL_PORT'] = int(config.get('MAIL_PORT', 587))
app.config['MAIL_USE_TLS'] = config.get('MAIL_USE_TLS', 'True') == 'True'
app.config['MAIL_USERNAME'] = config.get('MAIL_USERNAME', '')
app.config['MAIL_PASSWORD'] = config.get('MAIL_PASSWORD', '')
app.config['MAIL_DEFAULT_SENDER'] = config.get('MAIL_DEFAULT_SENDER', '')

# Initialize logging with higher level
logging.basicConfig(
    level=logging.WARNING,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler('generated/logs/app.log'),
        logging.StreamHandler()
    ]
)

# Initialize extensions
db = SQLAlchemy(app)
login_manager = LoginManager()
login_manager.init_app(app)
login_manager.login_view = 'auth.login'

# Import and register blueprints
from auth_routes import auth_bp
from settings_routes import settings_bp
from generate_routes import generate_bp
from admin_routes import admin_bp
from topic_routes import topic_bp

app.register_blueprint(auth_bp)
app.register_blueprint(settings_bp)
app.register_blueprint(generate_bp)
app.register_blueprint(admin_bp)
app.register_blueprint(topic_bp)

# Import models after db initialization
from models import User

def migrate_db():
    """Ensure all required columns exist in user_settings and user_posts tables."""
    conn = sqlite3.connect('users.db')
    c = conn.cursor()
    # user_settings: openai_api_key, tool_prompt, general_prompt, guide_prompt, auto_sync_enabled, auto_sync_time
    c.execute("PRAGMA table_info(user_settings)")
    columns = [row[1] for row in c.fetchall()]
    if 'openai_api_key' not in columns:
        c.execute('ALTER TABLE user_settings ADD COLUMN openai_api_key TEXT DEFAULT ""')
        conn.commit()
    if 'tool_prompt' not in columns:
        c.execute('ALTER TABLE user_settings ADD COLUMN tool_prompt TEXT DEFAULT ""')
        conn.commit()
    if 'general_prompt' not in columns:
        c.execute('ALTER TABLE user_settings ADD COLUMN general_prompt TEXT DEFAULT ""')
        conn.commit()
    if 'guide_prompt' not in columns:
        c.execute('ALTER TABLE user_settings ADD COLUMN guide_prompt TEXT DEFAULT ""')
        conn.commit()
    if 'auto_sync_enabled' not in columns:
        c.execute('ALTER TABLE user_settings ADD COLUMN auto_sync_enabled INTEGER DEFAULT 0')
        conn.commit()
    if 'auto_sync_time' not in columns:
        c.execute('ALTER TABLE user_settings ADD COLUMN auto_sync_time TEXT DEFAULT "02:00"')
        conn.commit()
    # user_posts: created_at, wp_post_id, synced
    c.execute("PRAGMA table_info(user_posts)")
    post_columns = [row[1] for row in c.fetchall()]
    if 'created_at' not in post_columns:
        c.execute('ALTER TABLE user_posts ADD COLUMN created_at TEXT')
        conn.commit()
    if 'wp_post_id' not in post_columns:
        c.execute('ALTER TABLE user_posts ADD COLUMN wp_post_id TEXT')
        conn.commit()
    if 'synced' not in post_columns:
        c.execute('ALTER TABLE user_posts ADD COLUMN synced INTEGER DEFAULT 0')
        conn.commit()
    conn.close()

# Call initialization before migration
init_db()
migrate_db()

@login_manager.user_loader
def load_user(user_id):
    return User.get(int(user_id))

@app.route('/')
def index():
    if current_user.is_authenticated:
        return redirect(url_for('generate.generate'))
    return render_template('index.html')

@app.route('/dashboard')
@login_required
def dashboard():
    return render_template('dashboard.html')

def schedule_auto_sync():
    conn = sqlite3.connect('users.db')
    c = conn.cursor()
    c.execute('SELECT user_id, auto_sync_enabled, auto_sync_time FROM user_settings')
    for user_id, enabled, sync_time in c.fetchall():
        if enabled:
            hour, minute = map(int, sync_time.split(':'))
            scheduler.add_job(
                sync_wordpress_posts,
                'cron',
                args=[user_id],
                hour=hour,
                minute=minute,
                id=f'auto_sync_{user_id}',
                replace_existing=True
            )
    conn.close()

scheduler = BackgroundScheduler()
scheduler.start()
schedule_auto_sync()

if __name__ == '__main__':
    # Run the app on all network interfaces (0.0.0.0) on port 5000
    app.run(host='0.0.0.0', port=5001, debug=False) 