from flask_login import UserMixin
from werkzeug.security import generate_password_hash
import sqlite3
import logging

class User(UserMixin):
    def __init__(self, id, username, password_hash, email=None, is_admin=False):
        self.id = id
        self.username = username
        self.password_hash = password_hash
        self.email = email
        self.is_admin = is_admin
        self._load_settings()

    def _load_settings(self):
        """Load user-specific settings"""
        try:
            conn = sqlite3.connect('users.db')
            c = conn.cursor()
            c.execute('SELECT * FROM user_settings WHERE user_id = ?', (self.id,))
            settings = c.fetchone()
            
            if settings:
                self.settings = {
                    'wordpress_url': settings[1],
                    'wordpress_username': settings[2],
                    'wordpress_password': settings[3],
                    'tool_prompt': settings[4],
                    'general_prompt': settings[5],
                    'guide_prompt': settings[6],
                    'auto_sync': bool(settings[7]),
                    'scheduled_sync': bool(settings[8]),
                    'sync_interval': settings[9],
                    'auto_cleanup': bool(settings[10]),
                    'enable_backup': bool(settings[11]),
                    'encrypt_backup': bool(settings[12]),
                    'email_after_backup': bool(settings[13]),
                    'openai_api_key': settings[14] if len(settings) > 14 else ''
                }
            else:
                # Create default settings
                self.settings = {
                    'wordpress_url': '',
                    'wordpress_username': '',
                    'wordpress_password': '',
                    'tool_prompt': '',
                    'general_prompt': '',
                    'guide_prompt': '',
                    'auto_sync': False,
                    'scheduled_sync': False,
                    'sync_interval': 6,
                    'auto_cleanup': False,
                    'enable_backup': False,
                    'encrypt_backup': False,
                    'email_after_backup': False,
                    'openai_api_key': ''
                }
                c.execute('''INSERT INTO user_settings 
                           (user_id, wordpress_url, wordpress_username, wordpress_password,
                            tool_prompt, general_prompt, guide_prompt, auto_sync,
                            scheduled_sync, sync_interval, auto_cleanup, enable_backup,
                            encrypt_backup, email_after_backup, openai_api_key)
                           VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)''',
                        (self.id, '', '', '', '', '', '', False, False, 6, False, False, False, False, ''))
                conn.commit()
            
            conn.close()
        except Exception as e:
            logging.error(f"Failed to load settings for user {self.username}: {str(e)}")
            self.settings = {}

    def save(self):
        """Save user to database"""
        try:
            conn = sqlite3.connect('users.db')
            c = conn.cursor()
            
            if self.id is None:
                # New user
                c.execute('''INSERT INTO users (username, password_hash, email, is_admin)
                           VALUES (?, ?, ?, ?)''',
                        (self.username, self.password_hash, self.email, self.is_admin))
                self.id = c.lastrowid
            else:
                # Update existing user
                c.execute('''UPDATE users 
                           SET username = ?, password_hash = ?, email = ?, is_admin = ?
                           WHERE id = ?''',
                        (self.username, self.password_hash, self.email, self.is_admin, self.id))
            
            conn.commit()
            conn.close()
            return True
        except Exception as e:
            logging.error(f"Failed to save user {self.username}: {str(e)}")
            return False

    def delete(self):
        """Delete user from database"""
        try:
            conn = sqlite3.connect('users.db')
            c = conn.cursor()
            
            # Delete user settings
            c.execute('DELETE FROM user_settings WHERE user_id = ?', (self.id,))
            
            # Delete user posts
            c.execute('DELETE FROM user_posts WHERE user_id = ?', (self.id,))
            
            # Delete user topics
            c.execute('DELETE FROM user_topics WHERE user_id = ?', (self.id,))
            
            # Delete user
            c.execute('DELETE FROM users WHERE id = ?', (self.id,))
            
            conn.commit()
            conn.close()
            return True
        except Exception as e:
            logging.error(f"Failed to delete user {self.username}: {str(e)}")
            return False

    @staticmethod
    def get(user_id):
        """Get user by ID"""
        try:
            conn = sqlite3.connect('users.db')
            c = conn.cursor()
            c.execute('SELECT * FROM users WHERE id = ?', (user_id,))
            user_data = c.fetchone()
            conn.close()
            
            if user_data:
                return User(
                    id=user_data[0],
                    username=user_data[1],
                    password_hash=user_data[2],
                    email=user_data[3],
                    is_admin=bool(user_data[4])
                )
            return None
        except Exception as e:
            logging.error(f"Failed to get user {user_id}: {str(e)}")
            return None

    @staticmethod
    def get_by_username(username):
        """Get user by username"""
        try:
            conn = sqlite3.connect('users.db')
            c = conn.cursor()
            c.execute('SELECT * FROM users WHERE username = ?', (username,))
            user_data = c.fetchone()
            conn.close()
            
            if user_data:
                return User(
                    id=user_data[0],
                    username=user_data[1],
                    password_hash=user_data[2],
                    email=user_data[3],
                    is_admin=bool(user_data[4])
                )
            return None
        except Exception as e:
            logging.error(f"Failed to get user {username}: {str(e)}")
            return None

    @staticmethod
    def get_all():
        """Get all users"""
        try:
            conn = sqlite3.connect('users.db')
            c = conn.cursor()
            c.execute('SELECT * FROM users')
            users = []
            for user_data in c.fetchall():
                users.append(User(
                    id=user_data[0],
                    username=user_data[1],
                    password_hash=user_data[2],
                    email=user_data[3],
                    is_admin=bool(user_data[4])
                ))
            conn.close()
            return users
        except Exception as e:
            logging.error(f"Failed to get all users: {str(e)}")
            return []

    @staticmethod
    def get_by_id(user_id):
        """Get user by ID (alias for get method)"""
        return User.get(user_id)

def init_db():
    """Initialize the database with required tables"""
    try:
        conn = sqlite3.connect('users.db')
        c = conn.cursor()
        
        # Users table
        c.execute('''CREATE TABLE IF NOT EXISTS users
                    (id INTEGER PRIMARY KEY AUTOINCREMENT,
                     username TEXT UNIQUE NOT NULL,
                     password_hash TEXT NOT NULL,
                     email TEXT,
                     is_admin BOOLEAN DEFAULT 0,
                     created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP)''')
        
        # User settings table with backup columns
        c.execute('''CREATE TABLE IF NOT EXISTS user_settings
                    (user_id INTEGER PRIMARY KEY,
                     wordpress_url TEXT,
                     wordpress_username TEXT,
                     wordpress_password TEXT,
                     tool_prompt TEXT,
                     general_prompt TEXT,
                     guide_prompt TEXT,
                     auto_sync BOOLEAN DEFAULT 0,
                     scheduled_sync BOOLEAN DEFAULT 0,
                     sync_interval INTEGER DEFAULT 6,
                     auto_cleanup BOOLEAN DEFAULT 0,
                     enable_backup BOOLEAN DEFAULT 0,
                     encrypt_backup BOOLEAN DEFAULT 0,
                     email_after_backup BOOLEAN DEFAULT 0,
                     openai_api_key TEXT DEFAULT '',
                     FOREIGN KEY (user_id) REFERENCES users(id))''')
        
        # User data tables
        c.execute('''CREATE TABLE IF NOT EXISTS user_posts
                    (id INTEGER PRIMARY KEY AUTOINCREMENT,
                     user_id INTEGER,
                     title TEXT NOT NULL,
                     content TEXT NOT NULL,
                     published_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                     FOREIGN KEY (user_id) REFERENCES users(id))''')
        
        c.execute('''CREATE TABLE IF NOT EXISTS user_topics
                    (id INTEGER PRIMARY KEY AUTOINCREMENT,
                     user_id INTEGER,
                     topic TEXT NOT NULL,
                     created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                     FOREIGN KEY (user_id) REFERENCES users(id))''')
        
        # Create admin user if not exists
        c.execute('SELECT * FROM users WHERE username = ?', ('admin',))
        if not c.fetchone():
            admin_password = generate_password_hash('admin123')  # Change this in production!
            c.execute('INSERT INTO users (username, password_hash, is_admin) VALUES (?, ?, ?)',
                     ('admin', admin_password, True))
        
        conn.commit()
        conn.close()
        logging.info("Database initialized successfully")
    except Exception as e:
        logging.error(f"Failed to initialize database: {str(e)}")
        raise 