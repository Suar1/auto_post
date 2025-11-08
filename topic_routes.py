from flask import Blueprint, render_template, request, jsonify, flash, redirect, url_for
from flask_login import login_required, current_user
from utils import get_embedding_cached, load_topic_embeddings, save_topic_embeddings
from embeddings import (
    get_embedding_stats, get_similarity_stats,
    cleanup_embeddings, update_embeddings_from_db
)
import sqlite3
import requests
import logging

topic_bp = Blueprint('topic', __name__)

@topic_bp.route('/topics')
@login_required
def topics():
    """View all topics and their embeddings."""
    stats = get_embedding_stats()
    return render_template('topics.html', stats=stats)

@topic_bp.route('/topics/check-similarity', methods=['POST'])
@login_required
def check_similarity():
    """Check similarity of a text against existing topics."""
    text = request.form.get('text')
    if not text:
        return jsonify({'error': 'No text provided'}), 400
        
    similarities = get_similarity_stats(text, current_user.id)
    return jsonify(similarities)

@topic_bp.route('/topics/cleanup', methods=['POST'])
@login_required
def cleanup():
    """Clean up old embeddings."""
    if cleanup_embeddings(current_user.id):
        return jsonify({'status': 'success', 'message': 'Embeddings cleaned up successfully'})
    return jsonify({'status': 'error', 'message': 'Failed to cleanup embeddings'}), 500

@topic_bp.route('/topics/update', methods=['POST'])
@login_required
def update():
    """Update embeddings from database."""
    if update_embeddings_from_db(current_user.id):
        return jsonify({'status': 'success', 'message': 'Embeddings updated successfully'})
    return jsonify({'status': 'error', 'message': 'Failed to update embeddings'}), 500

@topic_bp.route('/all_blog_topics')
@login_required
def all_blog_topics():
    # Implementation of all_blog_topics function
    pass

@topic_bp.route('/generate_post', methods=['POST'])
@login_required
def generate_post():
    topic = request.form.get('topic')
    post_type = request.form.get('type')
    if not topic or not post_type:
        return jsonify({'error': 'Missing topic or post type'}), 400
    
    # Implementation of generate_post function
    pass 

@topic_bp.route('/all_titles')
@login_required
def all_titles():
    """View all post titles in the database for the current user."""
    conn = sqlite3.connect('users.db')
    c = conn.cursor()
    c.execute('SELECT title, id, created_at FROM user_posts WHERE user_id = ? ORDER BY created_at DESC', (current_user.id,))
    posts = [{'title': row[0], 'id': row[1], 'created_at': row[2]} for row in c.fetchall()]
    conn.close()
    
    # Group by month for better organization
    from collections import defaultdict
    import datetime
    
    grouped_posts = defaultdict(list)
    for post in posts:
        try:
            if post['created_at']:
                date = datetime.datetime.fromisoformat(post['created_at']).strftime('%B %Y')
            else:
                date = 'Unknown Date'
        except:
            date = 'Unknown Date'
        grouped_posts[date].append(post)
    
    return render_template('all_titles.html', grouped_posts=grouped_posts, total_count=len(posts)) 

@topic_bp.route('/remove_post/<int:post_id>', methods=['POST'])
@login_required
def delete_title(post_id):
    """Delete a post by its ID."""
    try:
        conn = sqlite3.connect('users.db')
        c = conn.cursor()
        
        # First verify this post belongs to the current user
        c.execute('SELECT user_id FROM user_posts WHERE id = ?', (post_id,))
        result = c.fetchone()
        
        if not result:
            conn.close()
            flash('Post not found.', 'danger')
            return redirect(url_for('topic.all_titles'))
            
        if result[0] != current_user.id:
            conn.close()
            flash('Unauthorized action.', 'danger')
            return redirect(url_for('topic.all_titles'))
        
        # Delete the post
        c.execute('DELETE FROM user_posts WHERE id = ?', (post_id,))
        conn.commit()
        conn.close()
        
        flash('Post successfully deleted.', 'success')
        return redirect(url_for('topic.all_titles'))
    except Exception as e:
        flash(f'Error deleting post: {str(e)}', 'danger')
        return redirect(url_for('topic.all_titles')) 

@topic_bp.route('/sync_titles', methods=['POST'])
@login_required
def sync_titles():
    """Sync local titles with WordPress blog by removing titles not present on the blog."""
    try:
        # Connect to the database
        conn = sqlite3.connect('users.db')
        c = conn.cursor()
        
        # Get WordPress credentials
        c.execute('SELECT wordpress_url, wordpress_username, wordpress_password FROM user_settings WHERE user_id = ?', 
                  (current_user.id,))
        result = c.fetchone()
        
        if not result:
            flash('WordPress credentials not found. Please configure your settings first.', 'danger')
            return redirect(url_for('topic.all_titles'))
            
        wordpress_url, wp_username, wp_password = result
        
        # Fetch all posts from WordPress
        try:
            response = requests.get(
                f"{wordpress_url.rstrip('/')}/wp-json/wp/v2/posts?per_page=100",
                auth=(wp_username, wp_password)
            )
            
            if response.status_code != 200:
                flash(f'Failed to fetch posts from WordPress: {response.text}', 'danger')
                return redirect(url_for('topic.all_titles'))
                
            wp_posts = response.json()
            wp_post_ids = [str(post['id']) for post in wp_posts]
            
            # Get all local posts with WordPress IDs
            c.execute('SELECT id, wp_post_id FROM user_posts WHERE user_id = ? AND wp_post_id IS NOT NULL', 
                     (current_user.id,))
            local_posts = c.fetchall()
            
            # Find posts to delete (those not in WordPress anymore)
            posts_to_delete = []
            for local_id, wp_id in local_posts:
                if wp_id not in wp_post_ids:
                    posts_to_delete.append(local_id)
            
            # Delete posts not found on WordPress
            if posts_to_delete:
                placeholders = ', '.join(['?'] * len(posts_to_delete))
                c.execute(f'DELETE FROM user_posts WHERE id IN ({placeholders})', posts_to_delete)
                conn.commit()
                flash(f'Successfully removed {len(posts_to_delete)} posts that are no longer on your blog.', 'success')
            else:
                flash('All local posts are in sync with your blog.', 'info')
                
            conn.close()
            return redirect(url_for('topic.all_titles'))
            
        except Exception as e:
            flash(f'Error syncing with WordPress: {str(e)}', 'danger')
            return redirect(url_for('topic.all_titles'))
            
    except Exception as e:
        flash(f'Error syncing titles: {str(e)}', 'danger')
        return redirect(url_for('topic.all_titles')) 