from flask import Blueprint, render_template, request, jsonify, flash, redirect, url_for
from flask_login import login_required, current_user
import openai
from services import (
    generate_and_review_post, publish_post, generate_tags,
    process_tags, categorize_post, update_blog_categories,
    is_similar_post_exists, sync_wordpress_posts, get_uncovered_topics, generate_unique_topic_and_post, suggest_unique_topic
)
from datetime import datetime
import sqlite3
from models import User
import logging
import threading

generate_bp = Blueprint('generate', __name__)

@generate_bp.route('/generate', methods=['GET'])
@login_required
def generate():
    # Get user's most recent posts to display on the page
    conn = sqlite3.connect('users.db')
    c = conn.cursor()
    
    # Get top 10 most recent posts
    c.execute('''
        SELECT title, id, created_at 
        FROM user_posts 
        WHERE user_id = ? 
        ORDER BY created_at DESC
        LIMIT 10
    ''', (current_user.id,))
    recent_posts = [{'title': row[0], 'id': row[1], 'created_at': row[2]} for row in c.fetchall()]
    
    # Get all synced posts (posts with wp_post_id)
    c.execute('''
        SELECT title, wp_post_id, published_at 
        FROM user_posts 
        WHERE user_id = ? AND wp_post_id IS NOT NULL
        ORDER BY published_at DESC
        LIMIT 20
    ''', (current_user.id,))
    synced_posts = [{'title': row[0], 'wp_post_id': row[1], 'published_at': row[2]} for row in c.fetchall()]
    
    conn.close()
    
    return render_template('generate.html', 
                          recent_posts=recent_posts, 
                          synced_posts=synced_posts,
                          total_posts_count=len(recent_posts) + len(synced_posts))

@generate_bp.route('/generate/suggest-topic', methods=['POST'])
@login_required
def suggest_topic():
    prompt_type = request.form.get('prompt_type')
    result = suggest_unique_topic(prompt_type, current_user.id)
    return jsonify(result)

@generate_bp.route('/generate/post', methods=['POST'])
@login_required
def generate_post():
    try:
        prompt_type = request.form.get('prompt_type')
        approved_topic = request.form.get('approved_topic')
        if approved_topic:
            # User approved a topic, generate post about it
            result = generate_unique_topic_and_post(prompt_type, current_user.id)
        else:
            # Preview step: suggest topic first
            result = suggest_unique_topic(prompt_type, current_user.id)
            if result['status'] == 'success':
                return jsonify({'status': 'preview', 'topic': result['topic']})
            else:
                logging.error(f"[generate_post] Error in suggest_unique_topic: {result.get('message')}")
                return jsonify({'status': 'error', 'message': result['message']}), 500
                
        logging.warning(f"[generate_post] generate_unique_topic_and_post result: {result.get('title', '')}")
        
        if result['status'] == 'success':
            # Get title from result
            title = result['title']
            
            # Generate tags and publish immediately
            tags = generate_tags(result['content'], current_user.id)
            post_id = result['post_id']
            logging.warning(f"[generate_post] Calling publish_post for post_id={post_id}")
            publish_result = publish_post(post_id, current_user.id)
            logging.warning(f"[generate_post] publish_post result: {publish_result}")
            if publish_result['status'] == 'success':
                flash('Post generated and published successfully!', 'success')
            else:
                flash(f"Post generated but failed to publish: {publish_result['message']}", 'warning')
            return jsonify({
                'status': 'success',
                'message': 'Post generated successfully',
                'post_id': post_id,
                'title': title,
                'content': result['content']
            })
        else:
            error_message = result.get('message', 'Unknown error in post generation')
            logging.error(f"[generate_post] Error in generate_unique_topic_and_post: {error_message}")
            return jsonify({
                'status': 'error',
                'message': error_message
            }), 409  # Use 409 Conflict for duplicate titles
    except Exception as e:
        logging.error(f"[generate_post] Exception: {str(e)}")
        return jsonify({
            'status': 'error',
            'message': str(e)
        }), 500

@generate_bp.route('/generate/preview/<int:post_id>', methods=['GET'])
@login_required
def preview_post(post_id):
    # Fetch post from SQLite
    conn = sqlite3.connect('users.db')
    c = conn.cursor()
    c.execute('SELECT id, title, content FROM user_posts WHERE id = ? AND user_id = ?', (post_id, current_user.id))
    row = c.fetchone()
    conn.close()
    if not row:
        flash('Post not found.', 'danger')
        return redirect(url_for('generate.generate'))
    post = {'id': row[0], 'title': row[1], 'content': row[2], 'tags': [], 'category': ''}
    return render_template('preview.html', post=post)

@generate_bp.route('/generate/publish/<int:post_id>', methods=['POST'])
@login_required
def publish_post_route(post_id):
    try:
        result = publish_post(post_id, current_user.id)
        if result['status'] == 'success':
            flash('Post published successfully!', 'success')
            return jsonify({'status': 'success'})
        else:
            return jsonify({
                'status': 'error',
                'message': result['message']
            }), 500
    except Exception as e:
        return jsonify({
            'status': 'error',
            'message': str(e)
        }), 500

@generate_bp.route('/generate/sync', methods=['POST'])
@login_required
def manual_sync():
    # Manual sync endpoint
    success = sync_wordpress_posts(current_user.id)
    if success:
        flash('WordPress posts synced successfully!', 'success')
    else:
        flash('Failed to sync WordPress posts.', 'danger')
    return redirect(url_for('settings.settings'))

# TODO: Add auto-sync logic with scheduler (to be implemented in app.py or a background thread) 