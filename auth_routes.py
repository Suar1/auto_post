from flask import Blueprint, render_template, request, redirect, url_for, flash
from flask_login import login_user, logout_user, login_required, current_user
from werkzeug.security import generate_password_hash, check_password_hash
from models import User, init_db

auth_bp = Blueprint('auth', __name__)

@auth_bp.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        username = request.form.get('username')
        password = request.form.get('password')
        
        user = User.get_by_username(username)
        if user and check_password_hash(user.password_hash, password):
            login_user(user)
            flash('✅ Login successful!', 'success')
            return redirect(url_for('settings.settings'))
        
        flash('❌ Invalid username or password', 'error')
    return render_template('login.html')

@auth_bp.route('/register', methods=['GET', 'POST'])
def register():
    if request.method == 'POST':
        username = request.form.get('username')
        password = request.form.get('password')
        email = request.form.get('email')
        
        if User.get_by_username(username):
            flash('❌ Username already exists', 'error')
            return render_template('register.html')
        
        user = User(None, username, generate_password_hash(password), email=email)
        if user.save():
            flash('✅ Registration successful! Please login.', 'success')
            return redirect(url_for('auth.login'))
        
        flash('❌ Registration failed', 'error')
    return render_template('register.html')

@auth_bp.route('/logout')
@login_required
def logout():
    logout_user()
    flash('👋 Logged out successfully', 'success')
    return redirect(url_for('auth.login')) 