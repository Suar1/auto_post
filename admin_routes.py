from flask import Blueprint, render_template, request, redirect, url_for, flash, session
from flask_login import login_required, current_user
from models import User
from utils import admin_required

admin_bp = Blueprint('admin', __name__)

@admin_bp.route('/admin')
@login_required
@admin_required
def admin_dashboard():
    users = User.get_all()
    return render_template('admin.html', users=users)

@admin_bp.route('/admin/impersonate/<int:user_id>', methods=['POST'])
@login_required
@admin_required
def impersonate_user(user_id):
    user = User.get(user_id)
    if user:
        session['impersonated_user_id'] = user.id
        flash(f'Now impersonating user: {user.username}')
    return redirect(url_for('admin.admin_dashboard'))

@admin_bp.route('/admin/delete/<int:user_id>', methods=['POST'])
@login_required
@admin_required
def delete_user(user_id):
    user = User.get(user_id)
    if user and user.id != current_user.id:
        user.delete()
        flash(f'User {user.username} deleted successfully')
    else:
        flash('Cannot delete this user')
    return redirect(url_for('admin.admin_dashboard')) 