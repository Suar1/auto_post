from flask import Blueprint, render_template, request, jsonify, send_file, current_app, flash, redirect, url_for
from flask_login import login_required, current_user
from utils import config_manager, rate_limit, get_user_data_dir
import json
import os
import shutil
from datetime import datetime
import sqlite3
import io
from werkzeug.utils import secure_filename
from cryptography.fernet import Fernet
import logging

settings_bp = Blueprint('settings', __name__)

def get_latest_backup(user_id):
    """Get the latest backup file for a user"""
    backup_dir = os.path.join('user_data', f'user_{user_id}')
    if not os.path.exists(backup_dir):
        return None
    
    backup_files = [f for f in os.listdir(backup_dir) if f.startswith('backup_') and f.endswith('.json')]
    if not backup_files:
        return None
    
    return max(backup_files, key=lambda x: os.path.getctime(os.path.join(backup_dir, x)))

def decrypt_backup(encrypted_data, key):
    """Decrypt backup data using Fernet"""
    f = Fernet(key)
    return f.decrypt(encrypted_data)

@settings_bp.route('/download-latest-backup')
@login_required
@rate_limit(limit=5, per=60)
def download_latest_backup():
    """Download the latest backup file for the current user"""
    try:
        latest_backup = get_latest_backup(current_user.id)
        if not latest_backup:
            flash('❌ No backups found', 'error')
            logging.warning(f"⚠️ No backups found for user {current_user.username}")
            return redirect(url_for('settings.settings'))
        
        backup_path = os.path.join('user_data', f'user_{current_user.id}', latest_backup)
        
        # Check if backup is encrypted
        with open(backup_path, 'rb') as f:
            data = f.read()
        
        if current_user.settings.get('encrypt_backup'):
            try:
                key = current_app.config['BACKUP_ENCRYPTION_KEY']
                data = decrypt_backup(data, key)
                logging.info(f"🔐 Decrypted backup for user {current_user.username}")
            except Exception as e:
                logging.error(f"❌ Failed to decrypt backup: {str(e)}")
                flash('❌ Failed to decrypt backup', 'error')
                return redirect(url_for('settings.settings'))
        
        logging.info(f"📤 Downloaded backup for user {current_user.username}: {latest_backup}")
        return send_file(
            io.BytesIO(data),
            mimetype='application/json',
            as_attachment=True,
            download_name=latest_backup.replace('.json', '_decrypted.json')
        )
    
    except Exception as e:
        logging.error(f"❌ Failed to download backup: {str(e)}")
        flash('❌ Failed to download backup', 'error')
        return redirect(url_for('settings.settings'))

@settings_bp.route('/restore-backup', methods=['POST'])
@login_required
@rate_limit(limit=5, per=60)
def restore_backup():
    """Restore user data from a backup file"""
    if 'backup_file' not in request.files:
        flash('❌ No file uploaded', 'error')
        return redirect(url_for('settings.settings'))
    
    backup_file = request.files['backup_file']
    if not backup_file.filename:
        flash('❌ No file selected', 'error')
        return redirect(url_for('settings.settings'))
    
    if not backup_file.filename.endswith('.json'):
        flash('❌ Invalid file format. Please upload a JSON backup file', 'error')
        return redirect(url_for('settings.settings'))
    
    try:
        # Read and parse backup file
        data = backup_file.read()
        
        # Check if file is encrypted
        if current_user.settings.get('encrypt_backup'):
            try:
                key = current_app.config['BACKUP_ENCRYPTION_KEY']
                data = decrypt_backup(data, key)
                logging.info(f"🔐 Decrypted backup for restore by user {current_user.username}")
            except Exception as e:
                logging.error(f"❌ Failed to decrypt backup: {str(e)}")
                flash('❌ Failed to decrypt backup', 'error')
                return redirect(url_for('settings.settings'))
        
        backup_data = json.loads(data)
        
        # Validate backup data
        if backup_data.get('user_id') != current_user.id:
            flash('❌ Invalid backup file: user ID mismatch', 'error')
            logging.error(f"❌ Invalid backup file for user {current_user.username}: user ID mismatch")
            return redirect(url_for('settings.settings'))
        
        # Restore topics
        conn = sqlite3.connect('users.db')
        c = conn.cursor()
        
        # Clear existing topics
        c.execute('DELETE FROM user_topics WHERE user_id = ?', (current_user.id,))
        
        # Insert topics from backup
        for topic in backup_data.get('topics', []):
            c.execute('INSERT INTO user_topics (user_id, topic, created_at) VALUES (?, ?, ?)',
                     (current_user.id, topic['topic'], topic['created_at']))
        
        # Clear existing posts
        c.execute('DELETE FROM user_posts WHERE user_id = ?', (current_user.id,))
        
        # Insert posts from backup
        for post in backup_data.get('posts', []):
            c.execute('INSERT INTO user_posts (user_id, title, content, published_at) VALUES (?, ?, ?, ?)',
                     (current_user.id, post['title'], post['content'], post['published_at']))
        
        conn.commit()
        conn.close()
        
        flash('✅ Backup restored successfully', 'success')
        logging.info(f"✅ Backup restored for user {current_user.username}")
        
    except Exception as e:
        logging.error(f"❌ Failed to restore backup: {str(e)}")
        flash('❌ Failed to restore backup', 'error')
    
    return redirect(url_for('settings.settings'))

@settings_bp.route('/settings', methods=['GET', 'POST'])
@login_required
@rate_limit(limit=20, per=60)
def settings():
    """Settings page with backup management and prompt management"""
    if request.method == 'POST':
        try:
            # Get all form fields
            wordpress_url = request.form.get('wordpress_url', '').strip()
            wordpress_username = request.form.get('wordpress_username', '').strip()
            wordpress_password = request.form.get('wordpress_password', '').strip()
            openai_api_key = request.form.get('openai_api_key', '').strip()
            tool_prompt = request.form.get('tool_prompt', '').strip()
            general_prompt = request.form.get('general_prompt', '').strip()
            guide_prompt = request.form.get('guide_prompt', '').strip()
            # Other settings
            enable_backup = 'enable_backup' in request.form
            encrypt_backup = 'encrypt_backup' in request.form
            email_after_backup = 'email_after_backup' in request.form
            # Auto sync fields
            auto_sync_enabled = 1 if request.form.get('auto_sync_enabled') == 'on' else 0
            auto_sync_time = request.form.get('auto_sync_time', '02:00')
            scheduled_sync = 'scheduled_sync' in request.form
            sync_interval = int(request.form.get('sync_interval', 6))

            conn = sqlite3.connect('users.db')
            c = conn.cursor()
            c.execute('SELECT * FROM user_settings WHERE user_id = ?', (current_user.id,))
            current_settings = c.fetchone()
            
            if current_settings:
                # Update existing settings
                c.execute('''
                    UPDATE user_settings SET
                    wordpress_url = ?,
                    wordpress_username = ?,
                    wordpress_password = ?,
                    tool_prompt = ?,
                    general_prompt = ?,
                    guide_prompt = ?,
                    enable_backup = ?,
                    encrypt_backup = ?,
                    email_after_backup = ?,
                    auto_sync_enabled = ?,
                    auto_sync_time = ?,
                    scheduled_sync = ?,
                    sync_interval = ?,
                    openai_api_key = ?
                    WHERE user_id = ?
                ''', (
                    wordpress_url,
                    wordpress_username,
                    wordpress_password,
                    tool_prompt,
                    general_prompt,
                    guide_prompt,
                    enable_backup,
                    encrypt_backup,
                    email_after_backup,
                    auto_sync_enabled,
                    auto_sync_time,
                    scheduled_sync,
                    sync_interval,
                    openai_api_key,
                    current_user.id
                ))
            else:
                # Create new settings
                c.execute('''
                    INSERT INTO user_settings (
                        user_id, wordpress_url, wordpress_username, wordpress_password,
                        tool_prompt, general_prompt, guide_prompt,
                        enable_backup, encrypt_backup, email_after_backup,
                        auto_sync_enabled, auto_sync_time, scheduled_sync, sync_interval, openai_api_key
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ''', (
                    current_user.id,
                    wordpress_url,
                    wordpress_username,
                    wordpress_password,
                    tool_prompt,
                    general_prompt,
                    guide_prompt,
                    enable_backup,
                    encrypt_backup,
                    email_after_backup,
                    auto_sync_enabled,
                    auto_sync_time,
                    scheduled_sync,
                    sync_interval,
                    openai_api_key
                ))
            conn.commit()
            conn.close()
            current_user._load_settings()
            flash('✅ Settings updated successfully', 'success')
            return redirect(url_for('settings.settings'))
        except Exception as e:
            flash(f'❌ Error updating settings: {str(e)}', 'error')
            logging.error(f"Failed to update settings: {str(e)}")
    # Get latest backup info
    backup_dir = get_user_data_dir(current_user.id)
    latest_backup = None
    if os.path.exists(backup_dir):
        backups = [f for f in os.listdir(backup_dir) if f.endswith('.json') or f.endswith('.enc')]
        if backups:
            latest_backup = max(backups, key=lambda x: os.path.getctime(os.path.join(backup_dir, x)))
    return render_template('settings.html',
                          settings=current_user.settings,
                          latest_backup=latest_backup)

@settings_bp.route('/sync-posts', methods=['POST'])
@login_required
def sync_posts():
    # Implementation of sync_posts function
    pass

@settings_bp.route('/fix-embeddings', methods=['POST'])
@login_required
def fix_embeddings():
    # Implementation of fix_embeddings function
    pass

@settings_bp.route('/export-data')
@login_required
def export_data():
    # Implementation of export_data function
    pass

@settings_bp.route('/import-data', methods=['POST'])
@login_required
def import_data():
    # Implementation of import_data function
    pass

@settings_bp.route('/cleanup-embeddings', methods=['POST'])
@login_required
def cleanup_embeddings():
    # Implementation of cleanup_embeddings function
    pass 