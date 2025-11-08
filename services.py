import requests
import openai
import re
from datetime import datetime
import os
import logging
from logging.handlers import RotatingFileHandler
import json
import sqlite3
from cryptography.fernet import Fernet
import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from email.mime.application import MIMEApplication
from flask import current_app
from utils import get_user_data_dir, create_backup_filename, save_sync_log
import traceback
from embeddings import is_similar_to_existing, add_embedding

# === MONITORING ===
log_dir = os.path.abspath('generated/logs')
log_file = os.path.join(log_dir, 'post_log.txt')

try:
    os.makedirs(log_dir, exist_ok=True)
    handler = RotatingFileHandler(
        log_file,
        maxBytes=1024*1024,  # 1MB
        backupCount=3,
        encoding='utf-8'
    )
    handler.setFormatter(logging.Formatter('%(asctime)s - %(levelname)s - %(message)s'))
    logging.basicConfig(
        level=logging.WARNING,
        handlers=[handler],
        force=True
    )
except Exception as e:
    print(f"⚠️ Failed to set up file logging: {e}. Falling back to console logging.")
    logging.basicConfig(
        level=logging.WARNING,
        format='%(asctime)s - %(levelname)s - %(message)s',
        force=True
    )

def log(message):
    if "❌" in message or "⚠️" in message:
        print(message)
        logging.warning(message)

# === CATEGORIES ===
CATEGORIES = {
    "Cloud & Infrastructure": [
        "cloud", "infrastructure", "terraform", "openstack", "kubernetes",
        "docker", "containers", "virtualization", "iaas", "paas", "saas"
    ],
    "Network Tools & Monitoring": [
        "network", "monitoring", "prometheus", "observium", "scapy",
        "wireshark", "speedtest", "bandwidth", "latency", "packet"
    ],
    "Security & Privacy": [
        "security", "cybersecurity", "privacy", "vpn", "encryption",
        "authentication", "firewall", "ids", "ips", "suricata"
    ],
    "Configuration & Deployment": [
        "configuration", "deployment", "ansible", "puppet", "chef",
        "automation", "orchestration", "netbox", "napalm"
    ],
    "Server & System Setup": [
        "server", "system", "apache", "nginx", "mysql", "postgresql",
        "freeradius", "ssl", "certificates", "web server"
    ],
    "Tools & Utilities": [
        "tools", "utilities", "girocode", "immich", "ventoy", "iso",
        "backup", "restore", "migration", "conversion"
    ],
    "Performance Optimization": [
        "performance", "optimization", "grafana", "monitoring",
        "benchmarking", "tuning", "scaling", "load balancing"
    ],
    "Web & CMS": [
        "web", "cms", "wordpress", "drupal", "joomla", "content",
        "management", "website", "blog", "ecommerce"
    ]
}

# === CREATE POST ===
def create_wordpress_post(base_url, username, app_password, title, content, status="publish", tag_ids=None):
    log(f"📤 Creating post: {title}")
    payload = {
        "title": title,
        "content": content,
        "status": status
    }
    if tag_ids:
        payload["tags"] = tag_ids
    post_response = requests.post(
        f"{base_url.rstrip('/')}/wp-json/wp/v2/posts",
        auth=(username, app_password),
        json=payload
    )
    if post_response.status_code == 201:
        post_data = post_response.json()
        post_url = post_data['link']
        post_title = post_data['title']['rendered']
        log(f"✅ Post published at {post_url}")
        return post_url, post_title, post_data
    else:
        log(f"❌ Failed to publish post. Status: {post_response.status_code}")
        log(post_response.text)
        return None, None, None

# === FETCH THE /BLOG PAGE ===
def fetch_blog_page(base_url, username, app_password):
    log("📥 Fetching blog page...")
    page_response = requests.get(
        f"{base_url.rstrip('/')}/wp-json/wp/v2/pages?slug=blog&context=edit",
        auth=(username, app_password)
    )
    if page_response.status_code != 200 or not page_response.json():
        log("❌ Failed to fetch the /blog page.")
        return None, None, None
    blog_page = page_response.json()[0]
    page_id = blog_page['id']
    existing_content = blog_page['content']['raw']
    return page_id, existing_content, blog_page

# === BACKUP CURRENT BLOG PAGE ===
def backup_blog_page(existing_content):
    try:
        backup_dirs = [os.path.join('user_data', 'backups'), os.path.join('user_data', 'generated')]
        backup_file_name = f"blog_backup_{datetime.now().strftime('%Y%m%d_%H%M%S')}.html"
        for backup_dir in backup_dirs:
            os.makedirs(backup_dir, exist_ok=True)
            backup_file = os.path.join(backup_dir, backup_file_name)
            with open(backup_file, "w", encoding="utf-8") as backup:
                backup.write(existing_content)
            log(f"🧾 Blog content backed up to: {backup_file}")
        return os.path.join(backup_dirs[0], backup_file_name)
    except Exception as e:
        logging.error(f"Failed to backup blog page: {e}\n{traceback.format_exc()}")
        raise

# === Insert new post inside 'Recent Posts' list ===
def insert_post_in_recent(existing_content, post_url, post_title):
    new_list_item = f'<li><a href="{post_url}">{post_title}</a></li>'
    if new_list_item in existing_content:
        log("⚠️ Post already exists in Recent Posts. Skipping update.")
        return None
    pattern = r'(<h2 class="wp-block-heading">Recent Posts<\/h2>.*?<ul class="wp-block-list">)(.*?)(</ul>)'
    match = re.search(pattern, existing_content, flags=re.DOTALL)
    if not match:
        log("❌ Could not locate the 'Recent Posts' section.")
        return None
    updated_content = match.group(1) + new_list_item + match.group(2) + match.group(3)
    return updated_content

# === UPDATE THE /BLOG PAGE ===
def update_blog_page(base_url, username, app_password, page_id, updated_content):
    update_response = requests.post(
        f"{base_url.rstrip('/')}/wp-json/wp/v2/pages/{page_id}",
        auth=(username, app_password),
        json={"content": updated_content}
    )
    if update_response.status_code == 200:
        log("✅ /blog page updated — latest post inserted into 'Recent Posts'.")
        return True
    else:
        log(f"❌ Failed to update /blog page. Status: {update_response.status_code}")
        log(update_response.text)
        return False

# === INTEGRATION: After publishing a post, update the /blog page ===
def publish_post_and_update_blog(post_id, user_id):
    try:
        # Get user settings and post content
        conn = sqlite3.connect('users.db')
        c = conn.cursor()
        c.execute('SELECT wordpress_url, wordpress_username, wordpress_password FROM user_settings WHERE user_id = ?', (user_id,))
        wordpress_url, wp_username, wp_password = c.fetchone()
        c.execute('SELECT title, content FROM user_posts WHERE id = ? AND user_id = ?', (post_id, user_id))
        title, content = c.fetchone()
        conn.close()
        # Create post
        post_url, post_title, post_data = create_wordpress_post(wordpress_url, wp_username, wp_password, title, content)
        if not post_url:
            return {'status': 'error', 'message': 'Failed to publish post.'}
        # Fetch blog page
        page_id, existing_content, _ = fetch_blog_page(wordpress_url, wp_username, wp_password)
        if not page_id:
            return {'status': 'error', 'message': 'Failed to fetch /blog page.'}
        # Backup blog page
        backup_file = backup_blog_page(existing_content)
        # Insert new post in Recent Posts
        updated_content = insert_post_in_recent(existing_content, post_url, post_title)
        if not updated_content:
            return {'status': 'error', 'message': 'Failed to update Recent Posts.'}
        # Update blog page
        if update_blog_page(wordpress_url, wp_username, wp_password, page_id, updated_content):
            return {'status': 'success', 'message': 'Post published and /blog updated.'}
        else:
            return {'status': 'error', 'message': 'Failed to update /blog page.'}
    except Exception as e:
        log(f"❌ Exception in publish_post_and_update_blog: {str(e)}")
        return {'status': 'error', 'message': str(e)}

def generate_and_review_post(prompt, user_id):
    """Generate and review a blog post based on the given prompt"""
    try:
        # Get user settings
        conn = sqlite3.connect('users.db')
        c = conn.cursor()
        c.execute('SELECT * FROM user_settings WHERE user_id = ?', (user_id,))
        settings = dict(zip([col[0] for col in c.description], c.fetchone()))
        conn.close()
        
        # Initialize OpenAI client with per-user key
        user_api_key = settings.get('openai_api_key')
        if not user_api_key:
            raise Exception('No OpenAI API key set for this user.')
        client = openai.OpenAI(api_key=user_api_key)
        
        # Generate post
        response = client.chat.completions.create(
            model="gpt-4",
            messages=[
                {"role": "system", "content": "You are a professional blog writer."},
                {"role": "user", "content": prompt}
            ]
        )
        content = response.choices[0].message.content
        # Extract title (Markdown H1)
        title_match = re.search(r'^#\s*(.+)$', content, re.MULTILINE)
        if title_match:
            title = title_match.group(1)
            content = re.sub(r'^#\s*.+$', '', content, flags=re.MULTILINE).strip()
        else:
            # Fallback: use first line as title
            lines = content.strip().split('\n', 1)
            title = lines[0].strip()
            content = lines[1].strip() if len(lines) > 1 else ''
        # Save to database
        conn = sqlite3.connect('users.db')
        c = conn.cursor()
        c.execute('''
            INSERT INTO user_posts (user_id, title, content, created_at)
            VALUES (?, ?, ?, ?)
        ''', (user_id, title, content, datetime.now().isoformat()))
        post_id = c.lastrowid
        conn.commit()
        conn.close()
        return {
            'status': 'success',
            'post_id': post_id,
            'title': title,
            'content': content
        }
    except Exception as e:
        error_message = f"Failed to generate post: {str(e)}"
        logging.error(error_message)
        save_sync_log(error_message)
        return {
            'status': 'error',
            'message': error_message
        }

def insert_post_in_category(existing_content, post_url, post_title, category):
    """Insert a new post link into the correct category section, avoiding duplicates."""
    # Find the category section
    pattern = rf'(<h2[^>]*>{re.escape(category)}</h2>.*?<ul[^>]*>)(.*?)(</ul>)'
    match = re.search(pattern, existing_content, flags=re.DOTALL | re.IGNORECASE)
    new_list_item = f'<li><a href="{post_url}">{post_title}</a></li>'
    if match:
        # Only insert if not already present
        if new_list_item in match.group(2):
            return existing_content  # Already present, do nothing
        updated_content = match.group(1) + new_list_item + match.group(2) + match.group(3)
        return existing_content[:match.start()] + updated_content + existing_content[match.end():]
    else:
        # If category section does not exist, add it at the end
        category_block = f'<!-- wp:heading -->\n<h2>{category}</h2>\n<!-- /wp:heading -->\n\n<!-- wp:list -->\n<ul>\n{new_list_item}\n</ul>\n<!-- /wp:list -->\n'
        return existing_content + '\n' + category_block

def publish_post(post_id, user_id):
    """Publish a post to WordPress and update the /blog page under the correct category, with tags."""
    try:
        # Get user settings and post content
        conn = sqlite3.connect('users.db')
        c = conn.cursor()
        c.execute('SELECT wordpress_url, wordpress_username, wordpress_password FROM user_settings WHERE user_id = ?', (user_id,))
        wordpress_url, wp_username, wp_password = c.fetchone()
        c.execute('SELECT title, content FROM user_posts WHERE id = ? AND user_id = ?', (post_id, user_id))
        title, content = c.fetchone()
        conn.close()
        # Generate tags
        tags = generate_tags(content, user_id)
        tag_ids = process_tags(tags, wordpress_url, wp_username, wp_password, user_id)
        # Create post with tags
        post_url, post_title, post_data = create_wordpress_post(wordpress_url, wp_username, wp_password, title, content, tag_ids=tag_ids)
        if not post_url:
            return {'status': 'error', 'message': 'Failed to publish post.'}
        # Categorize post
        category = categorize_post(title, content, user_id)
        # Fetch blog page
        page_id, existing_content, _ = fetch_blog_page(wordpress_url, wp_username, wp_password)
        if not page_id:
            return {'status': 'error', 'message': 'Failed to fetch /blog page.'}
        # Backup blog page
        backup_file = backup_blog_page(existing_content)
        # Insert new post in the correct category section
        updated_content = insert_post_in_category(existing_content, post_url, post_title, category)
        if not updated_content:
            return {'status': 'error', 'message': f'Failed to update {category} section.'}
        # Update blog page
        if update_blog_page(wordpress_url, wp_username, wp_password, page_id, updated_content):
            return {'status': 'success', 'message': f'Post published and /blog updated under {category}.'}
        else:
            return {'status': 'error', 'message': 'Failed to update /blog page.'}
    except Exception as e:
        log(f"❌ Exception in publish_post: {str(e)}")
        return {'status': 'error', 'message': str(e)}

def encrypt_backup_data(data, key):
    """Encrypt backup data using Fernet"""
    f = Fernet(key)
    return f.encrypt(json.dumps(data).encode())

def send_backup_email(user_email, username, backup_file):
    """Send email notification after successful backup"""
    try:
        msg = MIMEMultipart()
        msg['From'] = current_app.config['MAIL_DEFAULT_SENDER']
        msg['To'] = user_email
        msg['Subject'] = f"Backup Created - {datetime.now().strftime('%Y-%m-%d %H:%M')}"
        
        body = f"""
        Hello {username},
        
        A new backup has been created successfully.
        
        Backup Details:
        - Time: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}
        - File: {backup_file}
        
        You can download this backup from your settings page.
        
        Best regards,
        Your Blog Post Generator
        """
        
        msg.attach(MIMEText(body, 'plain'))
        
        with smtplib.SMTP(current_app.config['MAIL_SERVER'], current_app.config['MAIL_PORT']) as server:
            if current_app.config['MAIL_USE_TLS']:
                server.starttls()
            if current_app.config['MAIL_USERNAME']:
                server.login(current_app.config['MAIL_USERNAME'], current_app.config['MAIL_PASSWORD'])
            server.send_message(msg)
        
        logging.info(f"📧 Backup notification email sent to {username}")
        return True
    except Exception as e:
        logging.error(f"❌ Failed to send backup email: {str(e)}")
        return False

def backup_user_data(user_id):
    """Backup user's topics and posts to a JSON file"""
    try:
        backup_dirs = [os.path.join('user_data', 'backups'), os.path.join('user_data', 'generated')]
        for backup_dir in backup_dirs:
            os.makedirs(backup_dir, exist_ok=True)
        # Get user's topics and posts from database
        conn = sqlite3.connect('users.db')
        c = conn.cursor()
        c.execute('SELECT username, email FROM users WHERE id = ?', (user_id,))
        username, email = c.fetchone()
        c.execute('SELECT encrypt_backup, email_after_backup FROM user_settings WHERE user_id = ?', (user_id,))
        encrypt_backup, email_after_backup = c.fetchone()
        c.execute('SELECT topic, created_at FROM user_topics WHERE user_id = ?', (user_id,))
        topics = [{'topic': row[0], 'created_at': row[1]} for row in c.fetchall()]
        c.execute('SELECT title, content, published_at FROM user_posts WHERE user_id = ?', (user_id,))
        posts = [{'title': row[0], 'content': row[1], 'published_at': row[2]} for row in c.fetchall()]
        conn.close()
        backup_data = {
            'user_id': user_id,
            'username': username,
            'backup_time': datetime.now().isoformat(),
            'topics': topics,
            'posts': posts
        }
        backup_file_name = create_backup_filename()
        for backup_dir in backup_dirs:
            backup_file = os.path.join(backup_dir, backup_file_name)
            if encrypt_backup:
                key = current_app.config['BACKUP_ENCRYPTION_KEY']
                encrypted_data = encrypt_backup_data(backup_data, key)
                with open(backup_file, 'wb') as f:
                    f.write(encrypted_data)
                log_message = f"🔐 Encrypted backup created for user {username}: {backup_file}"
            else:
                with open(backup_file, 'w', encoding='utf-8') as f:
                    json.dump(backup_data, f, indent=2)
                log_message = f"🔄 Backup created for user {username}: {backup_file}"
            logging.info(log_message)
            save_sync_log(log_message)
        if email_after_backup and email:
            if send_backup_email(email, username, os.path.join(backup_dirs[0], backup_file_name)):
                logging.info(f"📧 Backup notification sent to {username}")
            else:
                logging.warning(f"⚠️ Failed to send backup notification to {username}")
        return True
    except Exception as e:
        logging.error(f"❌ Failed to create backup for user {user_id}: {e}\n{traceback.format_exc()}")
        save_sync_log(f"❌ Failed to create backup for user {user_id}: {e}")
        raise

def generate_tags(content, user_id):
    """Generate tags for a post using GPT-3.5"""
    # Clean HTML content
    clean_content = re.sub(r'<[^>]+>', '', content)
    prompt = f"""
Generate 8-12 relevant keyword tags for a technology blog post. Focus on IT, networking, cybersecurity, and infrastructure terms.
- DO NOT include hashtag symbols (#)
- Each tag should be a simple word or phrase
- Keep tags concise and relevant
- Separate each tag with a new line
- Use lowercase except for proper nouns
- No punctuation or special characters

Content to tag:
{clean_content}
"""
    try:
        # Get user settings and API key
        conn = sqlite3.connect('users.db')
        c = conn.cursor()
        c.execute('SELECT openai_api_key FROM user_settings WHERE user_id = ?', (user_id,))
        result = c.fetchone()
        user_api_key = str(result[0]) if result and result[0] is not None else ""
        conn.close()
        if not user_api_key:
            raise Exception('No OpenAI API key set for this user.')
        client = openai.OpenAI(api_key=user_api_key)
        response = client.chat.completions.create(
            model="gpt-3.5-turbo",
            messages=[{"role": "user", "content": prompt}],
            max_tokens=300,
            temperature=0.5
        )
        tags = response.choices[0].message.content.strip()
        # Format tags as list and clean them
        return [clean_tag(tag.strip('•- ')) for tag in tags.split('\n') if tag.strip()]
    except Exception as e:
        log(f"❌ Failed to generate tags: {e}")
        return None

def clean_tag(tag):
    """Clean a tag by removing hashtags, special characters, and extra spaces"""
    # Remove hashtags and special characters
    tag = tag.strip('#').strip()
    # Convert to lowercase unless it's a proper noun
    if not any(c.isupper() for c in tag[1:]):  # Keep first letter capitalization if rest is lowercase
        tag = tag.lower()
    # Remove any remaining special characters and extra spaces
    tag = re.sub(r'[^\w\s-]', '', tag)
    tag = re.sub(r'\s+', ' ', tag).strip()
    return tag

def create_or_get_tag(tag_name, base_url, username, app_password):
    """Create a new tag or get existing tag ID"""
    # First try to find if tag exists
    search_response = requests.get(
        f"{base_url}/wp-json/wp/v2/tags",
        auth=(username, app_password),
        params={"search": tag_name}
    )
    
    if search_response.status_code == 200:
        existing_tags = search_response.json()
        for tag in existing_tags:
            if tag["name"].lower() == tag_name.lower():
                return tag["id"]
    
    # If tag doesn't exist, create it
    create_response = requests.post(
        f"{base_url}/wp-json/wp/v2/tags",
        auth=(username, app_password),
        json={"name": tag_name}
    )
    
    if create_response.status_code == 201:
        return create_response.json()["id"]
    
    return None

def process_tags(tag_names, base_url, username, app_password, user_id=None):
    """Convert tag names to tag IDs"""
    if not tag_names:
        return []
    tag_ids = []
    for tag_name in tag_names:
        tag_id = create_or_get_tag(tag_name, base_url, username, app_password)
        if tag_id:
            tag_ids.append(tag_id)
    return tag_ids

def categorize_post(title, content, user_id):
    """Use GPT to categorize a post based on its title and content"""
    prompt = f"""
Based on the following blog post title and content, categorize it into one of these categories:
{', '.join(CATEGORIES.keys())}

Title: {title}
Content: {content[:500]}...  # First 500 characters for context

Return ONLY the category name that best fits this post. Do not include any explanation or additional text.
"""
    try:
        # Get user settings and API key
        conn = sqlite3.connect('users.db')
        c = conn.cursor()
        c.execute('SELECT openai_api_key FROM user_settings WHERE user_id = ?', (user_id,))
        result = c.fetchone()
        user_api_key = str(result[0]) if result and result[0] is not None else ""
        conn.close()
        if not user_api_key:
            raise Exception('No OpenAI API key set for this user.')
        client = openai.OpenAI(api_key=user_api_key)
        response = client.chat.completions.create(
            model="gpt-3.5-turbo",
            messages=[{"role": "user", "content": prompt}],
            temperature=0.3,
            max_tokens=50
        )
        category = response.choices[0].message.content.strip()
        return category if category in CATEGORIES else "Uncategorized"
    except Exception as e:
        log(f"❌ Failed to categorize post: {e}")
        return "Uncategorized"

def update_blog_categories(categorized_posts, base_url, username, app_password):
    """Update the blog page with categorized sections"""
    log("📥 Fetching blog page...")
    page_response = requests.get(
        f"{base_url}/wp-json/wp/v2/pages?slug=blog&context=edit",
        auth=(username, app_password)
    )

    if page_response.status_code != 200 or not page_response.json():
        log("❌ Failed to fetch the /blog page.")
        return False

    blog_page = page_response.json()[0]
    page_id = blog_page['id']
    existing_content = blog_page['content']['raw']

    # Create backup
    backup_file = f"blog_backup_{datetime.now().strftime('%Y%m%d_%H%M%S')}.html"
    with open(backup_file, "w", encoding="utf-8") as backup:
        backup.write(existing_content)
    log(f"🧾 Blog content backed up to: {backup_file}")

    # Split content into parts
    parts = existing_content.split("<!-- wp:heading -->")
    intro_content = parts[0]  # Keep the introduction part

    # Generate new content with categories
    new_content = intro_content
    
    # Add categorized sections
    for category, posts in categorized_posts.items():
        if posts:  # Only add categories that have posts
            new_content += f'<!-- wp:heading -->\n<h2 class="wp-block-heading">{category}</h2>\n<!-- /wp:heading -->\n\n'
            new_content += '<!-- wp:list {"className":"wp-block-list"} -->\n<ul class="wp-block-list">\n'
            for post in posts:
                new_content += f'  <li><a href="{post["link"]}">{post["title"]["rendered"]}</a></li>\n'
            new_content += '</ul>\n<!-- /wp:list -->\n\n'

    # Update the blog page
    update_response = requests.put(
        f"{base_url}/wp-json/wp/v2/pages/{page_id}",
        auth=(username, app_password),
        json={"content": new_content}
    )

    if update_response.status_code == 200:
        log("✅ Blog page updated with categorized sections.")
        return True
    else:
        log(f"❌ Failed to update blog page. Status: {update_response.status_code}")
        log(update_response.text)
        return False

def sync_wordpress_posts(user_id):
    """Fetch all published posts from WordPress and sync them to user_posts with a 'synced' flag."""
    try:
        conn = sqlite3.connect('users.db')
        c = conn.cursor()
        c.execute('SELECT wordpress_url, wordpress_username, wordpress_password FROM user_settings WHERE user_id = ?', (user_id,))
        wordpress_url, wp_username, wp_password = c.fetchone()
        # Fetch all posts
        response = requests.get(
            f"{wordpress_url.rstrip('/')}/wp-json/wp/v2/posts?per_page=100",
            auth=(wp_username, wp_password)
        )
        if response.status_code != 200:
            log(f"❌ Failed to fetch posts from WordPress: {response.text}")
            return False
        posts = response.json()
        for post in posts:
            title = post['title']['rendered']
            content = post['content']['rendered']
            wp_post_id = str(post['id'])
            published_at = post['date_gmt']
            # Insert or update in user_posts
            c.execute('SELECT id FROM user_posts WHERE wp_post_id = ? AND user_id = ?', (wp_post_id, user_id))
            exists = c.fetchone()
            if exists:
                c.execute('''UPDATE user_posts SET title=?, content=?, published_at=?, synced=1 WHERE id=?''',
                          (title, content, published_at, exists[0]))
            else:
                c.execute('''INSERT INTO user_posts (user_id, title, content, published_at, wp_post_id, synced) VALUES (?, ?, ?, ?, ?, 1)''',
                          (user_id, title, content, published_at, wp_post_id))
        conn.commit()
        conn.close()
        log(f"✅ Synced {len(posts)} posts from WordPress for user {user_id}")
        return True
    except Exception as e:
        log(f"❌ Exception in sync_wordpress_posts: {e}")
        return False

def normalize_title(title):
    """Normalize a title for comparison, handling various formats and prefixes."""
    if not isinstance(title, str):
        title = str(title) if title is not None else ""
    
    # Remove markdown heading markers
    title = re.sub(r'^#+\s+', '', title)
    
    # Remove "Title:" prefix
    title = re.sub(r'^title:\s*', '', title, flags=re.IGNORECASE)
    
    # Normalize whitespace
    title = re.sub(r'\s+', ' ', title).strip().lower()
    
    return title

def is_exact_title_exists(user_id, title):
    """Check if an exact title match exists in the database, with improved normalization."""
    norm_title = normalize_title(title)
    
    # Don't check if the title is empty or too short (likely a formatting error)
    if not norm_title or len(norm_title) < 5:
        logging.warning(f"Title '{title}' is too short or empty after normalization")
        return False, None
    
    conn = sqlite3.connect('users.db')
    c = conn.cursor()
    c.execute('SELECT title FROM user_posts WHERE user_id = ?', (user_id,))
    
    for row in c.fetchall():
        title_from_db = str(row[0]) if row[0] is not None else ""
        db_norm_title = normalize_title(title_from_db)
        
        # Debug logging to understand the comparison
        logging.info(f"Comparing normalized: '{norm_title}' vs '{db_norm_title}'")
        
        if db_norm_title == norm_title:
            logging.warning(f"Exact normalized title match found: '{title_from_db}' == '{title}'")
            conn.close()
            return True, title_from_db
    
    conn.close()
    return False, None

# For preview: Suggest a unique topic but do not generate the post yet
def suggest_unique_topic(prompt_type, user_id):
    try:
        conn = sqlite3.connect('users.db')
        c = conn.cursor()
        c.execute('SELECT title FROM user_posts WHERE user_id = ?', (user_id,))
        existing_titles = [row[0] for row in c.fetchall()]
        conn.close()
        titles_list = '\n'.join(f'- {title}' for title in existing_titles)
        if prompt_type == 'default':
            base = "Suggest ONE useful IT tool for a blog post that is NOT in this list. Only return the tool name."
        elif prompt_type == 'tech':
            base = "Suggest ONE technology or IT topic for a blog post that is NOT in this list. Only return the topic name."
        elif prompt_type == 'guide':
            base = "Suggest ONE IT-related task or guide topic for a blog post that is NOT in this list. Only return the topic name."
        else:
            base = "Suggest ONE relevant topic for a blog post that is NOT in this list. Only return the topic name."
        topic_prompt = f"I have already written about the following topics:\n{titles_list}\n{base}"
        conn = sqlite3.connect('users.db')
        c = conn.cursor()
        c.execute('SELECT openai_api_key FROM user_settings WHERE user_id = ?', (user_id,))
        result = c.fetchone()
        user_api_key = str(result[0]) if result and result[0] is not None else ""
        conn.close()
        if not user_api_key:
            logging.error(f"No OpenAI API key set for user {user_id}")
            return {'status': 'error', 'message': 'No OpenAI API key set for this user.'}
        client = openai.OpenAI(api_key=user_api_key)
        try:
            topic_response = client.chat.completions.create(
                model="gpt-4",
                messages=[
                    {"role": "system", "content": "You are a professional blog topic generator."},
                    {"role": "user", "content": topic_prompt}
                ],
                max_tokens=30,
                temperature=0.7
            )
            topic = topic_response.choices[0].message.content.strip().split('\n')[0]
        except Exception as e:
            logging.error(f"OpenAI topic suggestion failed for user {user_id}: {e}")
            return {'status': 'error', 'message': f'OpenAI topic suggestion failed: {e}'}
        return {'status': 'success', 'topic': topic}
    except Exception as e:
        logging.error(f"Unexpected error in suggest_unique_topic for user {user_id}: {e}")
        return {'status': 'error', 'message': f'Unexpected error: {e}'}

POSSIBLE_TOPICS = [
    "Ansible", "Terraform", "Docker", "Kubernetes", "Prometheus", "Grafana", "OpenStack", "Wireshark", "NetBox", "Suricata", "Apache", "Nginx", "MySQL", "PostgreSQL", "FreeRADIUS", "Ventoy", "Immich", "Speedtest-cli", "PingPlotter", "OpenNMS", "Scapy", "Bro IDS", "RustDesk", "WordPress", "Certbot", "Passbolt", "NAPALM", "Observium", "Cloud Security", "VPN Setup", "Multi-Factor Authentication", "Blockchain", "AI in Cybersecurity"
]

def get_uncovered_topics(user_id):
    """Return a list of topics from POSSIBLE_TOPICS not yet covered in any post title/content."""
    conn = sqlite3.connect('users.db')
    c = conn.cursor()
    c.execute('SELECT title, content FROM user_posts WHERE user_id = ?', (user_id,))
    posts = c.fetchall()
    conn.close()
    covered = set()
    for topic in POSSIBLE_TOPICS:
        for title, content in posts:
            if topic.lower() in title.lower() or topic.lower() in content.lower():
                covered.add(topic)
                break
    return [t for t in POSSIBLE_TOPICS if t not in covered]

def generate_unique_topic_and_post(prompt_type, user_id):
    """Two-step: (1) get a unique topic, (2) generate a post about it."""
    try:
        # Step 1: Get all existing titles
        conn = sqlite3.connect('users.db')
        c = conn.cursor()
        c.execute('SELECT title FROM user_posts WHERE user_id = ?', (user_id,))
        existing_titles = [row[0] for row in c.fetchall()]
        conn.close()
        titles_list = '\n'.join(f'- {title}' for title in existing_titles)
        # Step 1: Ask OpenAI for a new topic
        if prompt_type == 'default':
            base = "Suggest ONE useful IT tool for a blog post that is NOT in this list. Only return the tool name."
        elif prompt_type == 'tech':
            base = "Suggest ONE technology or IT topic for a blog post that is NOT in this list. Only return the topic name."
        elif prompt_type == 'guide':
            base = "Suggest ONE IT-related task or guide topic for a blog post that is NOT in this list. Only return the topic name."
        else:
            base = "Suggest ONE relevant topic for a blog post that is NOT in this list. Only return the topic name."
        topic_prompt = f"I have already written about the following topics:\n{titles_list}\n{base}"
        # Get user OpenAI key
        conn = sqlite3.connect('users.db')
        c = conn.cursor()
        c.execute('SELECT openai_api_key FROM user_settings WHERE user_id = ?', (user_id,))
        result = c.fetchone()
        user_api_key = str(result[0]) if result and result[0] is not None else ""
        conn.close()
        if not user_api_key:
            logging.error(f"No OpenAI API key set for user {user_id}")
            return {'status': 'error', 'message': 'No OpenAI API key set for this user.'}
        client = openai.OpenAI(api_key=user_api_key)
        try:
            topic_response = client.chat.completions.create(
                model="gpt-4",
                messages=[
                    {"role": "system", "content": "You are a professional blog topic generator."},
                    {"role": "user", "content": topic_prompt}
                ],
                max_tokens=30,
                temperature=0.7
            )
            topic = topic_response.choices[0].message.content.strip().split('\n')[0]
        except Exception as e:
            logging.error(f"OpenAI topic suggestion failed for user {user_id}: {e}")
            return {'status': 'error', 'message': f'OpenAI topic suggestion failed: {e}'}
        # Step 2: Generate the post about this topic
        if prompt_type == 'default':
            post_base = f"Write a blog post about {topic}. Focus on its practical applications, benefits, and how to get started with it. Include code examples or configuration steps where relevant. Use a human tone, no dashes, and smoother transitions."
        elif prompt_type == 'tech':
            post_base = f"Write a blog post about {topic}. Focus on explaining complex concepts in simple terms, providing real-world examples, and offering practical insights. Use a human tone, no dashes, and smoother transitions."
        elif prompt_type == 'guide':
            post_base = f"Write a step-by-step guide for {topic}. Include clear instructions, code snippets or commands where needed, and explain each step thoroughly. Use a human tone, no dashes, and smoother transitions."
        else:
            post_base = f"Write a blog post about {topic}."
        try:
            post_response = client.chat.completions.create(
                model="gpt-4",
                messages=[
                    {"role": "system", "content": "You are a professional blog writer."},
                    {"role": "user", "content": post_base}
                ]
            )
            content = post_response.choices[0].message.content
        except Exception as e:
            logging.error(f"OpenAI post generation failed for user {user_id}, topic '{topic}': {e}")
            return {'status': 'error', 'message': f'OpenAI post generation failed: {e}'}
        # Extract title (Markdown H1) and clean it
        import re
        title_match = re.search(r'^#\s*(.+)$', content, re.MULTILINE)
        if title_match:
            title = title_match.group(1)
            content = re.sub(r'^#\s*.+$', '', content, flags=re.MULTILINE).strip()
        else:
            lines = content.strip().split('\n', 1)
            title = lines[0].strip()
            content = lines[1].strip() if len(lines) > 1 else ''
            
        # Use our comprehensive normalize_title function to clean the title
        original_title = title
        title = normalize_title(title)
        
        # Don't allow titles that are too short after normalization
        if len(title) < 10:
            logging.error(f"Title '{original_title}' is too short after normalization: '{title}'")
            return {'status': 'error', 'message': 'Generated title is too short or invalid. Please try again.'}
            
        # Capitalize the first letter of each word for proper formatting
        title = ' '.join(word.capitalize() if word.islower() else word for word in title.split())
        
        logging.info(f"Final cleaned title: '{title}' (original: '{original_title}')")
            
        # Check if title exists in the database using our efficient cache
        if title_exists_in_db(user_id, title):
            logging.error(f"Title already exists in database: '{title}'")
            return {'status': 'error', 'message': 'A post with this title already exists. Please try a different topic.'}
            
        # Save to database only if title is unique
        try:
            conn = sqlite3.connect('users.db')
            c = conn.cursor()
            c.execute('''INSERT INTO user_posts (user_id, title, content, created_at) VALUES (?, ?, ?, ?)''',
                      (user_id, title, content, datetime.now().isoformat()))
            post_id = c.lastrowid
            conn.commit()
            conn.close()
            
            # Update the title cache to include this new title
            if user_id in _title_cache:
                _title_cache[user_id]['original'].append(title)
                _title_cache[user_id]['normalized'].append(normalize_title(title))
                
        except Exception as e:
            logging.error(f"Failed to save generated post for user {user_id}, title '{title}': {e}")
            return {'status': 'error', 'message': f'Failed to save generated post: {e}'}
        return {
            'status': 'success',
            'post_id': post_id,
            'title': title,
            'content': content
        }
    except Exception as e:
        logging.error(f"Unexpected error in generate_unique_topic_and_post for user {user_id}: {e}")
        return {'status': 'error', 'message': f'Unexpected error: {e}'}

def is_similar_post_exists(user_id, title, content=None, threshold=0.95, check_content=False):
    """Check if a similar post exists using semantic similarity."""
    # First check for exact title match (case-insensitive)
    exact_match, matching_title = is_exact_title_exists(user_id, title)
    if exact_match:
        logging.warning(f"Exact title match found: '{matching_title}'")
        return True
        
    # Then check semantic similarity with a higher threshold (less strict)
    is_similar, most_similar = is_similar_to_existing(title, user_id)
    if is_similar:
        logging.warning(f"Semantically similar post found: '{most_similar}' for new title '{title}'")
        return True
        
    # If not similar, add the new title's embedding
    add_embedding(title, user_id)
    return False 

# Cache of normalized titles for quick checking
_title_cache = {}

def get_all_user_titles(user_id, force_refresh=False):
    """Get all titles for a user, using a cache for efficiency."""
    global _title_cache
    
    # Initialize cache for user if needed
    if user_id not in _title_cache or force_refresh:
        conn = sqlite3.connect('users.db')
        c = conn.cursor()
        c.execute('SELECT title FROM user_posts WHERE user_id = ?', (user_id,))
        titles = [str(row[0]) if row[0] is not None else "" for row in c.fetchall()]
        conn.close()
        
        # Store both original and normalized titles
        _title_cache[user_id] = {
            'original': titles,
            'normalized': [normalize_title(title) for title in titles],
            'last_updated': datetime.now().isoformat()
        }
        logging.info(f"Title cache refreshed for user {user_id} with {len(titles)} titles")
    
    return _title_cache[user_id]

def title_exists_in_db(user_id, title):
    """Check if a title already exists for this user using the cache."""
    normalized_title = normalize_title(title)
    
    # Skip very short titles
    if len(normalized_title) < 5:
        return False
    
    # Get titles from cache
    title_cache = get_all_user_titles(user_id)
    
    # First check for exact normalized match
    if normalized_title in title_cache['normalized']:
        idx = title_cache['normalized'].index(normalized_title)
        original_title = title_cache['original'][idx]
        logging.warning(f"Exact title match found: '{original_title}' == '{title}'")
        return True
    
    # No match found
    return False 