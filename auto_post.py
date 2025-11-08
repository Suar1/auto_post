import requests
import openai
import re
from datetime import datetime
import os
import time
import sys
sys.path.append('.')

# === CONFIG ===
def load_env(path):
    env = {}
    with open(path, "r", encoding="utf-8") as f:
        for line in f:
            if "=" in line:
                key, val = line.strip().split("=", 1)
                env[key] = val
    return env

config = load_env(os.path.join(os.path.dirname(__file__), "blog_config.env"))
BASE_URL = config["BASE_URL"]
USERNAME = config["USERNAME"]
APP_PASSWORD = config["APP_PASSWORD"]

script_dir = os.path.dirname(os.path.abspath(__file__))
API_KEY_PATH = os.path.join(script_dir, "api.key")
used_titles_path = os.path.join(script_dir, "used_titles.txt")
excluded_tools_path = os.path.join(script_dir, "excluded_tools.txt")

# === MONITORING ===
log_file = "post_log.txt"
backup_file = f"blog_backup_{datetime.now().strftime('%Y%m%d_%H%M%S')}.html"

def log(message):
    print(message)
    with open(log_file, "a", encoding="utf-8") as logf:
        logf.write(f"{datetime.now()} - {message}\n")

# === LOAD OPENAI KEY ===
try:
    with open(API_KEY_PATH, "r", encoding="utf-8") as keyfile:
        openai.api_key = keyfile.read().strip()
except Exception as e:
    log(f"❌ Failed to load OpenAI key: {e}")
    exit()

# === LOAD USED TITLES ===
if os.path.exists(used_titles_path):
    with open(used_titles_path, "r", encoding="utf-8") as f:
        used_titles = {line.strip().lower() for line in f if line.strip()}
else:
    used_titles = set()

# === LOAD EXCLUDED TOOLS ===
if os.path.exists(excluded_tools_path):
    with open(excluded_tools_path, "r", encoding="utf-8") as f:
        excluded_tools = [line.strip() for line in f if line.strip()]
else:
    excluded_tools = []

# === LOAD CATEGORIES ===
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

def fetch_all_posts():
    """Fetch all posts from WordPress"""
    log("🔍 Fetching all posts...")
    posts_response = requests.get(
        f"{BASE_URL}/posts",
        auth=(USERNAME, APP_PASSWORD),
        params={"per_page": 100, "orderby": "date", "order": "desc"}
    )
    
    if posts_response.status_code != 200 or not posts_response.json():
        log("❌ Failed to fetch posts or no posts found.")
        return None
        
    return posts_response.json()

def review_categorization(categorized_posts):
    """Review and optionally correct the categorization of posts"""
    while True:
        print("\n=== Categorization Review ===")
        # Show all categories and their posts
        for idx, (category, posts) in enumerate(categorized_posts.items(), 1):
            if posts:
                print(f"\n{idx}. 🔹 {category}")
                for i, post in enumerate(posts, 1):
                    print(f"   {i}. {post['title']['rendered']}")

        print("\nWhat would you like to do?")
        print("1. Move a post to a different category")
        print("2. Accept all categorizations")
        print("3. Cancel operation")

        choice = get_valid_input(
            "\nEnter your choice (1-3): ",
            "❌ Please enter a number between 1 and 3"
        )

        if choice == "1":
            # Select post to move
            print("\nFirst, select the current category of the post:")
            categories_with_posts = [(cat, posts) for cat, posts in categorized_posts.items() if posts]
            for idx, (category, _) in enumerate(categories_with_posts, 1):
                print(f"{idx}. {category}")
            
            try:
                cat_idx = int(get_valid_input("\nEnter category number: ")) - 1
                if 0 <= cat_idx < len(categories_with_posts):
                    current_category, posts = categories_with_posts[cat_idx]
                    
                    # Select post from category
                    print(f"\nSelect post from {current_category}:")
                    for idx, post in enumerate(posts, 1):
                        print(f"{idx}. {post['title']['rendered']}")
                    
                    post_idx = int(get_valid_input("\nEnter post number: ")) - 1
                    if 0 <= post_idx < len(posts):
                        # Select new category
                        print("\nSelect new category:")
                        all_categories = list(CATEGORIES.keys())
                        for idx, category in enumerate(all_categories, 1):
                            print(f"{idx}. {category}")
                        
                        new_cat_idx = int(get_valid_input("\nEnter new category number: ")) - 1
                        if 0 <= new_cat_idx < len(all_categories):
                            new_category = all_categories[new_cat_idx]
                            
                            # Move post to new category
                            post = posts.pop(post_idx)
                            if new_category not in categorized_posts:
                                categorized_posts[new_category] = []
                            categorized_posts[new_category].append(post)
                            log(f"✅ Moved post to {new_category}")
                            
                            # Remove empty categories
                            categorized_posts = {k: v for k, v in categorized_posts.items() if v}
                            continue
            except ValueError:
                print("❌ Invalid input")
                continue
                
        elif choice == "2":
            return categorized_posts
        else:  # choice == "3"
            return None
            
        print("❌ Invalid selection")

def update_blog_page(categorized_posts):
    """Update the blog page with categorized sections"""
    log("📥 Fetching blog page...")
    page_response = requests.get(
        f"{BASE_URL}/pages?slug=blog&context=edit",
        auth=(USERNAME, APP_PASSWORD)
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
        f"{BASE_URL}/pages/{page_id}",
        auth=(USERNAME, APP_PASSWORD),
        json={"content": new_content}
    )

    if update_response.status_code == 200:
        log("✅ Blog page updated with categorized sections.")
        return True
    else:
        log(f"❌ Failed to update blog page. Status: {update_response.status_code}")
        log(update_response.text)
        return False

def get_valid_input(prompt_text, error_message="❌ Input cannot be empty. Please try again."):
    """Helper function to get valid non-empty input from user"""
    while True:
        user_input = input(prompt_text).strip()
        if user_input:
            return user_input
        print(error_message)

def list_and_delete_post():
    log("🔍 Fetching all posts...")
    posts_response = requests.get(
        f"{BASE_URL}/posts",
        auth=(USERNAME, APP_PASSWORD),
        params={"per_page": 100, "orderby": "date", "order": "desc"}
    )
    
    if posts_response.status_code != 200 or not posts_response.json():
        log("❌ Failed to fetch posts or no posts found.")
        return False
        
    posts = posts_response.json()
    
    print("\n=== Available Posts ===")
    for idx, post in enumerate(posts, 1):
        title = post['title']['rendered']
        date = post['date'].split('T')[0]
        print(f"{idx}. [{date}] {title}")
    
    while True:
        choice = get_valid_input("\nEnter the number of the post to delete (or '0' to cancel): ")
        if choice == '0':
            log("🛑 Deletion cancelled.")
            return False
        
        try:
            post_idx = int(choice) - 1
            if 0 <= post_idx < len(posts):
                break
            print("❌ Invalid number. Please enter a number between 1 and", len(posts))
        except ValueError:
            print("❌ Please enter a valid number.")
    
    selected_post = posts[post_idx]
    post_id = selected_post['id']
    post_title = selected_post['title']['rendered']
    post_url = selected_post['link']
    
    confirm = get_valid_input(
        f"\nAre you sure you want to delete the post: '{post_title}'? (yes/no): ",
        "❌ Please enter 'yes' or 'no'"
    ).lower()
    
    if confirm != 'yes':
        log("🛑 Deletion cancelled.")
        return False
    
    delete_response = requests.delete(
        f"{BASE_URL}/posts/{post_id}",
        auth=(USERNAME, APP_PASSWORD),
        params={"force": True}
    )
    
    if delete_response.status_code == 200:
        log(f"✅ Successfully deleted post: {post_title}")
        # Remove from used_titles.txt if present
        if os.path.exists(used_titles_path):
            with open(used_titles_path, 'r', encoding='utf-8') as f:
                titles = f.readlines()
            with open(used_titles_path, 'w', encoding='utf-8') as f:
                for title in titles:
                    if title.strip() != post_title:
                        f.write(title)
        
        # Update the blog page to remove the deleted post
        log("📥 Fetching blog page...")
        page_response = requests.get(
            f"{BASE_URL}/pages?slug=blog&context=edit",
            auth=(USERNAME, APP_PASSWORD)
        )

        if page_response.status_code != 200 or not page_response.json():
            log("❌ Failed to fetch the /blog page.")
            return True

        blog_page = page_response.json()[0]
        page_id = blog_page['id']
        existing_content = blog_page['content']['raw']

        # Create backup
        backup_file = f"blog_backup_{datetime.now().strftime('%Y%m%d_%H%M%S')}.html"
        with open(backup_file, "w", encoding="utf-8") as backup:
            backup.write(existing_content)
        log(f"🧾 Blog content backed up to: {backup_file}")

        # Remove the deleted post from the Recent Posts list
        pattern = r'(<h2 class="wp-block-heading">Recent Posts<\/h2>.*?<ul class="wp-block-list">)(.*?)(</ul>)'
        match = re.search(pattern, existing_content, flags=re.DOTALL)

        if match:
            existing_list_items = match.group(2).strip()
            # Split into lines and filter out the deleted post
            lines = existing_list_items.split("\n")
            updated_lines = []
            post_title_lower = post_title.lower()
            
            for line in lines:
                # Check both URL and title text to ensure we find the correct entry
                if post_url not in line and post_title_lower not in line.lower():
                    updated_lines.append(line)
            
            updated_list_items = "\n".join(updated_lines)
            
            # Update the content
            updated_recent_posts = match.group(1) + updated_list_items + match.group(3)
            updated_content = re.sub(pattern, updated_recent_posts, existing_content, flags=re.DOTALL)

            # Update the blog page
            update_response = requests.put(
                f"{BASE_URL}/pages/{page_id}",
                auth=(USERNAME, APP_PASSWORD),
                json={"content": updated_content}
            )

            if update_response.status_code == 200:
                log("✅ /blog page updated — deleted post removed from Recent Posts.")
            else:
                log(f"❌ Failed to update /blog page. Status: {update_response.status_code}")
                log(update_response.text)
        else:
            log("⚠️ Could not locate the 'Recent Posts' section in the blog page.")
        
        return True
    else:
        log(f"❌ Failed to delete post. Status: {delete_response.status_code}")
        return False

def generate_title(content):
    try:
        title_prompt = (
            "Based on this blog post content, generate a clear and SEO-friendly title. "
            "The title should:\n"
            "- Be descriptive and specific\n"
            "- Include the main topic and action (e.g. 'How to...', 'Complete Guide to...', etc.)\n"
            "- Be 50-60 characters long\n"
            "- Not include the date or words like 'automated' or 'post'\n"
            "Return only the title, without any markdown formatting or extra text:\n\n" + content
        )
        
        response = openai.ChatCompletion.create(
            model="gpt-3.5-turbo",
            messages=[{"role": "user", "content": title_prompt}],
            temperature=0.7,
            max_tokens=50
        )
        return response.choices[0].message.content.strip()
    except Exception as e:
        log(f"❌ Failed to generate title: {e}")
        return None

def generate_and_review_post(prompt, is_default_prompt=True):
    log("🧠 Generating content from ChatGPT...")
    
    while True:
        try:
            response = openai.ChatCompletion.create(
                model="gpt-3.5-turbo",
                messages=[{"role": "user", "content": prompt}],
                temperature=0.8,
                max_tokens=700
            )
            content = response.choices[0].message.content.strip()
        except Exception as e:
            log(f"❌ Failed to generate content: {e}")
            return None, None

        # Always try to generate a proper title, regardless of prompt type
        generated_title = None
        
        # First try to extract from markdown if it exists
        first_line = content.splitlines()[0].strip()
        if first_line.startswith("#"):
            generated_title = first_line.lstrip("#").strip()
            content = "\n".join(content.splitlines()[1:]).strip()
        
        # If no markdown title, generate one using GPT
        if not generated_title:
            generated_title = generate_title(content)
        
        # If both methods fail (very unlikely), create a descriptive title
        if not generated_title:
            # Extract first sentence or first 100 characters
            first_sentence = content.split('.')[0].strip()
            if len(first_sentence) > 60:
                first_sentence = first_sentence[:57] + "..."
            generated_title = first_sentence

        if generated_title.lower() not in used_titles:
            break

        log(f"⚠️ Duplicate title detected: '{generated_title}', generating a new one...")

    # Show preview and get confirmation
    print("\n=== Post Preview ===")
    print(f"Title: {generated_title}")
    print("\nContent:")
    print("-------------------")
    print(content)
    print("-------------------")
    
    while True:
        choice = get_valid_input(
            "\nWhat would you like to do?\n1. Publish this post\n2. Generate a new version\n3. Edit title\n4. Cancel\nYour choice (1-4): ",
            "❌ Please enter a number between 1 and 4"
        )
        
        if choice in ["1", "2", "3", "4"]:
            break
        print("❌ Invalid choice. Please enter 1, 2, 3, or 4.")
    
    if choice == "1":
        return generated_title, content
    elif choice == "2":
        log("🔄 Generating new version...")
        return generate_and_review_post(prompt, is_default_prompt)
    elif choice == "3":
        new_title = input("Enter new title: ").strip()
        if new_title:
            return new_title, content
        return generate_and_review_post(prompt, is_default_prompt)
    else:  # choice == "4"
        log("🛑 Post creation cancelled.")
        return None, None

def generate_tags(post_content):
    """Generate tags for a post using GPT-3.5"""
    # Clean HTML content
    clean_content = re.sub(r'<[^>]+>', '', post_content)
    
    prompt = f"""
Generate 8-12 relevant keyword tags for a technology blog post. Focus on IT, networking, cybersecurity, and infrastructure terms.
- DO NOT include hashtag symbols (#)
- Each tag should be a simple word or phrase
- Keep tags concise and relevant
- Separate each tag with a new line
- Use lowercase except for proper nouns
- No punctuation or special characters

Content to tag:
\"\"\"{clean_content}\"\"\"
"""
    try:
        response = openai.ChatCompletion.create(
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

def format_tags_html(tags_list):
    """Convert tags list to HTML format"""
    if not tags_list:
        return ''
    return '<h3>Related Topics</h3>\n<ul class="post-tags">\n' + '\n'.join(f'<li>{tag}</li>' for tag in tags_list) + '\n</ul>'

def update_post_with_tags(post, tags_list):
    """Update a post with the given tags"""
    if not tags_list:
        return
        
    post_id = post["id"]
    
    # Update WordPress native tags
    tag_ids = process_tags(tags_list)
    if tag_ids:
        tag_update = requests.post(
            f"{BASE_URL}/posts/{post_id}",
            auth=(USERNAME, APP_PASSWORD),
            json={"tags": tag_ids}
        )
        
        if tag_update.status_code != 200:
            log(f"❌ Failed to update WordPress tags for post ID {post_id}")
            return

    # Remove any existing HTML tags section from content
    content = post["content"]["rendered"]
    if '<h3>Related Topics</h3>' in content or '<ul class="post-tags">' in content:
        # Remove existing tags section
        content = re.sub(r'<h3>Related Topics</h3>\s*<ul class="post-tags">.*?</ul>', '', content, flags=re.DOTALL)
        
        # Update the content without the HTML tags section
        content_update = requests.post(
            f"{BASE_URL}/posts/{post_id}",
            auth=(USERNAME, APP_PASSWORD),
            json={"content": content}
        )
        
        if content_update.status_code == 200:
            log(f"✅ Removed HTML tags section from post ID {post_id}")
        else:
            log(f"❌ Failed to remove HTML tags section: {content_update.text}")

def manual_tagging():
    """Handle manual tagging of posts"""
    log("🔄 Fetching posts...")
    response = requests.get(
        f"{BASE_URL}/posts",
        params={"per_page": 100},
        auth=(USERNAME, APP_PASSWORD)
    )
    
    if response.status_code != 200:
        log(f"❌ Failed to fetch posts: {response.text}")
        return
    
    posts = response.json()
    
    # Display posts
    print("\n=== Available Posts ===")
    available_posts = []
    for idx, post in enumerate(posts, 1):
        title = post["title"]["rendered"]
        print(f"{idx}. {title}")
        available_posts.append(post)
    
    if not available_posts:
        log("❌ No posts found!")
        return
    
    while True:
        choice = get_valid_input(
            "\nEnter the number of the post to tag (or '0' to exit): ",
            "❌ Please enter a valid number"
        )
        
        if choice == '0':
            return
            
        try:
            post_idx = int(choice) - 1
            if 0 <= post_idx < len(available_posts):
                break
            print(f"❌ Please enter a number between 1 and {len(available_posts)}")
        except ValueError:
            print("❌ Please enter a valid number")
    
    selected_post = available_posts[post_idx]
    title = selected_post["title"]["rendered"]
    
    print(f"\n📝 Enter tags for: {title}")
    print("Enter one tag per line. Press Enter twice when done.")
    
    tags_list = []
    while True:
        tag = input().strip()
        if not tag:
            break
        tags_list.append(tag)
    
    if not tags_list:
        log("❌ No tags entered. Operation cancelled.")
        return
    
    return selected_post, tags_list

def automatic_tagging(start_from=None):
    """Handle automatic tagging of posts"""
    log("🔄 Fetching posts...")
    response = requests.get(
        f"{BASE_URL}/posts",
        params={"per_page": 100},
        auth=(USERNAME, APP_PASSWORD)
    )
    
    if response.status_code != 200:
        log(f"❌ Failed to fetch posts: {response.text}")
        return
    
    posts = response.json()
    total_posts = len(posts)
    
    for idx, post in enumerate(posts, 1):
        post_id = post["id"]
        
        # Skip posts before start_from if specified
        if start_from and post_id < start_from:
            continue
            
        title = post["title"]["rendered"]
        content = post["content"]["rendered"]
            
        print(f"\n[{idx}/{total_posts}] 🔍 Processing: {title}")
        
        tags_list = generate_tags(content)
        if not tags_list:
            continue
        
        # Preview tags and get confirmation
        print("\n=== Generated Tags Preview ===")
        print(f"Post: {title}")
        print("\nTags:")
        for tag in tags_list:
            print(f"• {tag}")
        
        confirm = get_valid_input(
            "\nDo you want to apply these tags? (yes/no): ",
            "❌ Please enter 'yes' or 'no'"
        ).lower()
        
        if confirm != 'yes':
            print("⏭️ Skipping this post...")
            continue
        
        update_post_with_tags(post, tags_list)
        time.sleep(1.5)  # polite delay between requests

def check_recent_posts_section():
    """Check if the Recent Posts section exists in the blog page"""
    log("🔍 Checking for 'Recent Posts' section...")
    page_response = requests.get(
        f"{BASE_URL}/pages?slug=blog&context=edit",
        auth=(USERNAME, APP_PASSWORD)
    )

    if page_response.status_code != 200 or not page_response.json():
        log("❌ Failed to fetch the /blog page.")
        return False

    blog_page = page_response.json()[0]
    existing_content = blog_page['content']['raw']

    # Check for Recent Posts section
    pattern = r'(<h2[^>]*>Recent Posts<\/h2>)(.*?)(<ul class="wp-block-list">.*?</ul>)'
    match = re.search(pattern, existing_content, flags=re.DOTALL)

    if not match:
        log("❌ Could not locate the 'Recent Posts' section in the blog page.")
        return False
    
    log("✅ 'Recent Posts' section found.")
    return True

def create_or_get_tag(tag_name):
    """Create a new tag or get existing tag ID"""
    # First try to find if tag exists
    search_response = requests.get(
        f"{BASE_URL}/tags",
        auth=(USERNAME, APP_PASSWORD),
        params={"search": tag_name}
    )
    
    if search_response.status_code == 200:
        existing_tags = search_response.json()
        for tag in existing_tags:
            if tag["name"].lower() == tag_name.lower():
                return tag["id"]
    
    # If tag doesn't exist, create it
    create_response = requests.post(
        f"{BASE_URL}/tags",
        auth=(USERNAME, APP_PASSWORD),
        json={"name": tag_name}
    )
    
    if create_response.status_code == 201:
        return create_response.json()["id"]
    
    return None

def process_tags(tag_names):
    """Convert tag names to tag IDs"""
    if not tag_names:
        return []
    
    tag_ids = []
    for tag_name in tag_names:
        tag_id = create_or_get_tag(tag_name)
        if tag_id:
            tag_ids.append(tag_id)
    
    return tag_ids

def publish_post(title, content, tags=None):
    """Publish a post to WordPress and return the post ID"""
    log("📝 Publishing post...")
    
    post_data = {
        "title": title,
        "content": content,
        "status": "publish"
    }
    
    if tags:
        # Convert tag names to tag IDs - only use WordPress native tags
        tag_ids = process_tags(tags)
        if tag_ids:
            post_data["tags"] = tag_ids

    try:
        response = requests.post(
            f"{BASE_URL}/posts",
            auth=(USERNAME, APP_PASSWORD),
            json=post_data
        )
        
        if response.status_code == 201:
            post_id = response.json()["id"]
            log(f"✅ Post published successfully! ID: {post_id}")
            
            # Automatically categorize the new post
            log("🔄 Categorizing the new post...")
            
            # Initialize categorized_posts dictionary
            categorized_posts = {category: [] for category in CATEGORIES}
            categorized_posts["Uncategorized"] = []
            
            # Get all existing posts
            all_posts_response = requests.get(
                f"{BASE_URL}/posts",
                auth=(USERNAME, APP_PASSWORD),
                params={"per_page": 100, "orderby": "date", "order": "desc"}
            )
            
            if all_posts_response.status_code == 200:
                all_posts = all_posts_response.json()
                
                # Categorize all posts including the new one
                for post in all_posts:
                    post_title = post["title"]["rendered"]
                    post_content = post["content"]["rendered"]
                    category = categorize_post(post_title, post_content)
                    categorized_posts[category].append(post)
                    
                # Update the blog page with new categorization
                update_success = update_blog_page(categorized_posts)
                if update_success:
                    log("✅ Blog page updated with new categorization")
                else:
                    log("❌ Failed to update blog page categorization")
            
            return post_id
        else:
            log(f"❌ Failed to publish post. Status: {response.status_code}")
            log(response.text)
            return None
            
    except Exception as e:
        log(f"❌ Error publishing post: {e}")
        return None

def generate_post(prompt):
    """Generate a blog post using ChatGPT"""
    try:
        response = openai.ChatCompletion.create(
            model="gpt-3.5-turbo",
            messages=[
                {"role": "system", "content": "You are a professional IT blogger who writes detailed, informative posts about technology topics."},
                {"role": "user", "content": prompt}
            ],
            temperature=0.7,
            max_tokens=2500
        )
        
        content = response.choices[0].message.content.strip()
        
        # Extract title from the first line
        title = content.split('\n')[0].strip('#').strip()
        
        # Remove title from content and clean up
        content = '\n'.join(content.split('\n')[1:]).strip()
        
        # Format content for WordPress
        formatted_content = f"<!-- wp:paragraph -->\n"
        formatted_content += '\n\n<!-- /wp:paragraph -->\n<!-- wp:paragraph -->\n'.join(
            f"<p>{paragraph}</p>" for paragraph in content.split('\n\n')
        )
        formatted_content += "\n<!-- /wp:paragraph -->"
        
        return title, formatted_content
    except Exception as e:
        log(f"❌ Error generating post: {e}")
        return None, None

def categorize_post(title, content):
    """Use GPT to categorize a post based on its title and content"""
    prompt = f"""
Based on the following blog post title and content, categorize it into one of these categories:
{', '.join(CATEGORIES.keys())}

Title: {title}
Content: {content[:500]}...  # First 500 characters for context

Return ONLY the category name that best fits this post. Do not include any explanation or additional text.
"""
    
    try:
        response = openai.ChatCompletion.create(
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

def update_blog_categories(post_data):
    """Update the blog page with the new post in its category"""
    log("📥 Fetching blog page...")
    page_response = requests.get(
        f"{BASE_URL}/pages?slug=blog&context=edit",
        auth=(USERNAME, APP_PASSWORD)
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
    
    # Categorize the new post
    category = categorize_post(post_data['title']['rendered'], post_data['content']['rendered'])
    log(f"📝 Categorized post as: {category}")

    # Generate new content
    new_content = intro_content
    
    # Add categorized sections
    for cat in CATEGORIES.keys():
        if cat == category:
            # Add the new post to its category
            new_content += f'<!-- wp:heading -->\n<h2 class="wp-block-heading">{cat}</h2>\n<!-- /wp:heading -->\n\n'
            new_content += '<!-- wp:list {"className":"wp-block-list"} -->\n<ul class="wp-block-list">\n'
            new_content += f'  <li><a href="{post_data["link"]}">{post_data["title"]["rendered"]}</a></li>\n'
            new_content += '</ul>\n<!-- /wp:list -->\n\n'

    # Update the blog page
    update_response = requests.put(
        f"{BASE_URL}/pages/{page_id}",
        auth=(USERNAME, APP_PASSWORD),
        json={"content": new_content}
    )

    if update_response.status_code == 200:
        log("✅ Blog page updated with new post in its category.")
        return True
    else:
        log(f"❌ Failed to update blog page. Status: {update_response.status_code}")
        log(update_response.text)
        return False

def convert_to_native_tags(post):
    """Convert post's HTML tags to WordPress native tags"""
    content = post["content"]["rendered"]
    post_id = post["id"]
    title = post["title"]["rendered"]
    
    # Extract existing tags from content
    tag_pattern = r'<ul class="post-tags">(.*?)</ul>'
    match = re.search(tag_pattern, content, re.DOTALL)
    
    if not match:
        return False
        
    # Extract tags from HTML
    tags_html = match.group(1)
    tags = [clean_tag(tag) for tag in re.findall(r'<li>(.*?)</li>', tags_html)]
    
    if not tags:
        return False
    
    # Convert tags to WordPress native tags
    tag_ids = process_tags(tags)
    
    if not tag_ids:
        return False
    
    # Update post with native tags
    update = requests.post(
        f"{BASE_URL}/posts/{post_id}",
        auth=(USERNAME, APP_PASSWORD),
        json={"tags": tag_ids}
    )
    
    if update.status_code == 200:
        # Remove tags section from content
        new_content = re.sub(r'<h3>Related Topics</h3>\s*<ul class="post-tags">.*?</ul>', '', content, flags=re.DOTALL)
        
        # Update post content without tags section
        content_update = requests.post(
            f"{BASE_URL}/posts/{post_id}",
            auth=(USERNAME, APP_PASSWORD),
            json={"content": new_content}
        )
        
        if content_update.status_code == 200:
            log(f"✅ Converted tags to native format for: {title}")
            return True
    
    log(f"❌ Failed to convert tags for: {title}")
    return False

def convert_all_tags_to_native():
    """Convert all posts' HTML tags to WordPress native tags and remove HTML tag sections"""
    log("🔍 Fetching all posts...")
    response = requests.get(
        f"{BASE_URL}/posts",
        params={"per_page": 100},
        auth=(USERNAME, APP_PASSWORD)
    )
    
    if response.status_code != 200:
        log("❌ Failed to fetch posts")
        return
    
    posts = response.json()
    total_posts = len(posts)
    converted_count = 0
    
    for idx, post in enumerate(posts, 1):
        title = post["title"]["rendered"]
        content = post["content"]["rendered"]
        post_id = post["id"]
        log(f"\n[{idx}/{total_posts}] Processing: {title}")
        
        # Extract existing tags from content if present
        tags = []
        tag_pattern = r'<ul class="post-tags">(.*?)</ul>'
        match = re.search(tag_pattern, content, re.DOTALL)
        
        if match:
            tags_html = match.group(1)
            tags = [clean_tag(tag) for tag in re.findall(r'<li>(.*?)</li>', tags_html)]
        
        # Convert to WordPress native tags
        if tags:
            tag_ids = process_tags(tags)
            if tag_ids:
                update = requests.post(
                    f"{BASE_URL}/posts/{post_id}",
                    auth=(USERNAME, APP_PASSWORD),
                    json={"tags": tag_ids}
                )
                
                if update.status_code == 200:
                    converted_count += 1
                    
        # Remove HTML tags section regardless of whether we found tags
        if '<h3>Related Topics</h3>' in content or '<ul class="post-tags">' in content:
            new_content = re.sub(r'<h3>Related Topics</h3>\s*<ul class="post-tags">.*?</ul>', '', content, flags=re.DOTALL)
            
            content_update = requests.post(
                f"{BASE_URL}/posts/{post_id}",
                auth=(USERNAME, APP_PASSWORD),
                json={"content": new_content}
            )
            
            if content_update.status_code == 200:
                log(f"✅ Removed HTML tags section from: {title}")
            else:
                log(f"❌ Failed to remove HTML tags section from: {title}")
        
        time.sleep(1)  # Polite delay between requests
    
    log(f"\n✅ Conversion complete. Converted {converted_count} posts to native tags.")

def check_posts_without_tags():
    """Check for posts that don't have any tags and allow adding tags to them"""
    log("🔍 Checking for posts without tags...")
    response = requests.get(
        f"{BASE_URL}/posts",
        params={"per_page": 100},
        auth=(USERNAME, APP_PASSWORD)
    )
    
    if response.status_code != 200:
        log("❌ Failed to fetch posts")
        return
    
    posts = response.json()
    posts_without_tags = []
    
    for post in posts:
        # Check if post has any tags
        if not post.get('tags'):
            posts_without_tags.append(post)
    
    if not posts_without_tags:
        print("\n✅ All posts have tags!")
        return
    
    print(f"\n⚠️ Found {len(posts_without_tags)} posts without tags:")
    for idx, post in enumerate(posts_without_tags, 1):
        title = post["title"]["rendered"]
        date = post["date"].split('T')[0]
        print(f"{idx}. [{date}] {title}")
    
    while True:
        choice = get_valid_input(
            "\nWhat would you like to do?\n"
            "1. Add tags automatically to all posts without tags\n"
            "2. Add tags manually to a specific post\n"
            "3. Back to tag menu\n"
            "Your choice (1-3): ",
            "❌ Please enter a number between 1 and 3"
        )
        
        if choice == "1":
            for post in posts_without_tags:
                title = post["title"]["rendered"]
                content = post["content"]["rendered"]
                print(f"\n🔄 Processing: {title}")
                
                tags_list = generate_tags(content)
                if not tags_list:
                    print("❌ Failed to generate tags, skipping...")
                    continue
                
                # Preview tags
                print("\n=== Generated Tags Preview ===")
                print(f"Post: {title}")
                print("\nTags:")
                for tag in tags_list:
                    print(f"• {tag}")
                
                confirm = get_valid_input(
                    "\nDo you want to apply these tags? (yes/no): ",
                    "❌ Please enter 'yes' or 'no'"
                ).lower()
                
                if confirm == 'yes':
                    update_post_with_tags(post, tags_list)
                else:
                    print("⏭️ Skipping this post...")
                
                time.sleep(1)  # Polite delay between requests
            break
            
        elif choice == "2":
            while True:
                post_choice = get_valid_input(
                    "\nEnter the number of the post to tag (or '0' to cancel): ",
                    "❌ Please enter a valid number"
                )
                
                if post_choice == '0':
                    break
                    
                try:
                    post_idx = int(post_choice) - 1
                    if 0 <= post_idx < len(posts_without_tags):
                        selected_post = posts_without_tags[post_idx]
                        title = selected_post["title"]["rendered"]
                        content = selected_post["content"]["rendered"]
                        
                        print(f"\n📝 Adding tags for: {title}")
                        print("\nChoose tagging method:")
                        print("1. Generate tags automatically")
                        print("2. Enter tags manually")
                        
                        method = get_valid_input(
                            "Your choice (1-2): ",
                            "❌ Please enter 1 or 2"
                        )
                        
                        if method == "1":
                            tags_list = generate_tags(content)
                            if tags_list:
                                print("\n=== Generated Tags Preview ===")
                                print("Tags:")
                                for tag in tags_list:
                                    print(f"• {tag}")
                                
                                confirm = get_valid_input(
                                    "\nDo you want to apply these tags? (yes/no): ",
                                    "❌ Please enter 'yes' or 'no'"
                                ).lower()
                                
                                if confirm == 'yes':
                                    update_post_with_tags(selected_post, tags_list)
                            else:
                                print("❌ Failed to generate tags")
                        else:  # method == "2"
                            print("\nEnter tags one per line. Press Enter twice when done.")
                            tags_list = []
                            while True:
                                tag = input().strip()
                                if not tag:
                                    break
                                tags_list.append(clean_tag(tag))
                            
                            if tags_list:
                                update_post_with_tags(selected_post, tags_list)
                            else:
                                print("❌ No tags entered")
                        break
                    else:
                        print(f"❌ Please enter a number between 1 and {len(posts_without_tags)}")
                except ValueError:
                    print("❌ Please enter a valid number")
            break
            
        elif choice == "3":
            break
        else:
            print("❌ Invalid choice. Please enter 1, 2, or 3.")

def main_menu():
    """Display the main menu and handle user input"""
    while True:
        print("\n=== WordPress Blog Post Manager ===")
        print("1. Generate post with default prompt (IT tools)")
        print("2. Generate post about general tech/IT topics")
        print("3. Generate step-by-step guide")
        print("4. Generate post with custom prompt")
        print("5. Delete a post")
        print("6. Manage tags")
        print("7. Manage post categories")
        print("8. Exit")
        
        choice = input("\nEnter your choice (1-8): ").strip()
        
        if choice == "1":
            prompt = "Write a blog post about a useful IT tool. Focus on its practical applications, benefits, and how to get started with it. Include code examples or configuration steps where relevant. use a human tone, no dashes, and smoother transitions."
            title, content = generate_and_review_post(prompt)
            if title and content:
                # Generate tags
                tags = generate_tags(title + "\n" + content)
                
                # Publish post with tags
                post_id = publish_post(title, content, tags)
                
                if post_id:
                    print(f"\n✨ Post '{title}' published successfully!")
                    print(f"🔗 Post URL: {BASE_URL}/posts/{post_id}")
                else:
                    print("❌ Failed to publish post")
        elif choice == "2":
            prompt = "Write a blog post about a general technology or IT topic. Focus on explaining complex concepts in simple terms, providing real-world examples, and offering practical insights. use a human tone, no dashes, and smoother transitions."
            title, content = generate_and_review_post(prompt)
            if title and content:
                # Generate tags
                tags = generate_tags(title + "\n" + content)
                
                # Publish post with tags
                post_id = publish_post(title, content, tags)
                
                if post_id:
                    print(f"\n✨ Post '{title}' published successfully!")
                    print(f"🔗 Post URL: {BASE_URL}/posts/{post_id}")
                else:
                    print("❌ Failed to publish post")
        elif choice == "3":
            prompt = "Write a step-by-step guide for an IT-related task. Include clear instructions, code snippets or commands where needed, and explain each step thoroughly. use a human tone, no dashes, and smoother transitions."
            title, content = generate_and_review_post(prompt)
            if title and content:
                # Generate tags
                tags = generate_tags(title + "\n" + content)
                
                # Publish post with tags
                post_id = publish_post(title, content, tags)
                
                if post_id:
                    print(f"\n✨ Post '{title}' published successfully!")
                    print(f"🔗 Post URL: {BASE_URL}/posts/{post_id}")
                else:
                    print("❌ Failed to publish post")
        elif choice == "4":
            custom_prompt = get_valid_input("Enter your custom prompt: ")
            title, content = generate_and_review_post(custom_prompt, is_default_prompt=False)
            if title and content:
                # Generate tags
                tags = generate_tags(title + "\n" + content)
                
                # Publish post with tags
                post_id = publish_post(title, content, tags)
                
                if post_id:
                    print(f"\n✨ Post '{title}' published successfully!")
                    print(f"🔗 Post URL: {BASE_URL}/posts/{post_id}")
                else:
                    print("❌ Failed to publish post")
        elif choice == "5":
            list_and_delete_post()
        elif choice == "6":
            print("\n=== Tag Management ===")
            print("1. Add tags automatically")
            print("2. Add tags manually")
            print("3. Convert HTML tags to WordPress native tags")
            print("4. Check for posts without tags")
            print("5. Back to main menu")
            
            tag_choice = input("\nEnter your choice (1-5): ").strip()
            if tag_choice == "1":
                automatic_tagging()
            elif tag_choice == "2":
                manual_tagging()
            elif tag_choice == "3":
                confirm = get_valid_input(
                    "\nThis will convert all HTML tags to WordPress native tags. Continue? (yes/no): ",
                    "❌ Please enter 'yes' or 'no'"
                ).lower()
                
                if confirm == 'yes':
                    convert_all_tags_to_native()
            elif tag_choice == "4":
                check_posts_without_tags()
        elif choice == "7":
            print("\n=== Category Management ===")
            print("1. Review and update post categories")
            print("2. Back to main menu")
            
            cat_choice = input("\nEnter your choice (1-2): ").strip()
            if cat_choice == "1":
                posts = fetch_all_posts()
                if posts:
                    # Create initial categorization
                    categorized_posts = {}
                    for post in posts:
                        category = categorize_post(post['title']['rendered'], post['content']['rendered'])
                        if category not in categorized_posts:
                            categorized_posts[category] = []
                        categorized_posts[category].append(post)
                    
                    # Review and update categorization
                    final_categories = review_categorization(categorized_posts)
                    if final_categories:
                        update_blog_page(final_categories)
        elif choice == "8":
            print("👋 Goodbye!")
            break
        else:
            print("❌ Invalid choice. Please try again.")

if __name__ == "__main__":
    main_menu()
