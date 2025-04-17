import requests
import openai
import re
from datetime import datetime
import os

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
            "Based on this blog post content, generate a clear and concise title. "
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

        if is_default_prompt:
            # For default prompt, extract title from markdown
            first_line = content.splitlines()[0].strip()
            if first_line.startswith("#"):
                extracted_title = first_line.lstrip("#").strip()
                content = "\n".join(content.splitlines()[1:]).strip()
            else:
                extracted_title = f"Automated Post - {datetime.now().strftime('%Y-%m-%d')}"
        else:
            # For custom prompt, generate title separately
            generated_title = generate_title(content)
            if generated_title:
                extracted_title = generated_title
            else:
                extracted_title = f"Custom Post - {datetime.now().strftime('%Y-%m-%d')}"

        if extracted_title.lower() not in used_titles:
            break

        log(f"⚠️ Duplicate title detected: '{extracted_title}', generating a new one...")

    # Show preview and get confirmation
    print("\n=== Post Preview ===")
    print(f"Title: {extracted_title}")
    print("\nContent:")
    print("-------------------")
    print(content)
    print("-------------------")
    
    while True:
        choice = get_valid_input(
            "\nWhat would you like to do?\n1. Publish this post\n2. Generate a new version\n3. Cancel\nYour choice (1-3): ",
            "❌ Please enter a number between 1 and 3"
        )
        
        if choice in ["1", "2", "3"]:
            break
        print("❌ Invalid choice. Please enter 1, 2, or 3.")
    
    if choice == "1":
        return extracted_title, content
    elif choice == "2":
        log("🔄 Generating new version...")
        return generate_and_review_post(prompt, is_default_prompt)  # Recursive call instead of continue
    else:  # choice == "3"
        log("🛑 Post creation cancelled.")
        return None, None

# === MAIN MENU ===
while True:
    print("\n=== Blog Post Manager ===")
    print("1. Generate post with default prompt (IT tools)")
    print("2. Generate post about general tech/IT topics")
    print("3. Generate step-by-step guide")
    print("4. Generate post with custom prompt")
    print("5. Delete a post")
    print("6. Exit")
    
    choice = get_valid_input(
        "\nEnter your choice (1-6): ",
        "❌ Please enter a number between 1 and 6"
    )
    
    if choice not in ["1", "2", "3", "4", "5", "6"]:
        print("❌ Invalid choice. Please enter a number between 1 and 6.")
        continue
    
    if choice == "6":
        print("Goodbye!")
        exit()
    
    elif choice == "5":
        list_and_delete_post()
        continue
    
    # === GENERATE BLOG POST ===
    log("🧠 Preparing to generate content from ChatGPT...")
    exclude_string = ", ".join(excluded_tools)
    
    if choice == "4":
        print("\nEnter your custom prompt.")
        print("Tips:")
        print("- Include desired word count")
        print("- Specify the content structure")
        print("- The title will be generated automatically based on the content")
        
        while True:
            custom_prompt = get_valid_input(
                "\nYour prompt: ",
                "❌ Prompt cannot be empty. Please enter your prompt."
            )
            
            # Additional validation for minimum prompt length if desired
            if len(custom_prompt) < 10:
                print("❌ Prompt is too short. Please provide more details.")
                continue
            break
            
        title, content = generate_and_review_post(custom_prompt, is_default_prompt=False)
    elif choice == "3":
        prompt = (
            "Write a step-by-step guide (300–400 words) on a useful topic related to networking, "
            "infrastructure, DevOps, or cybersecurity. Choose the topic yourself. The guide should "
            "include a clear title, practical instructions, and explain each step in simple language. "
            "Assume the reader has basic IT knowledge but isn't an expert. Use a markdown H1 title "
            "at the beginning."
        )
        title, content = generate_and_review_post(prompt, is_default_prompt=True)
    elif choice == "2":
        prompt = (
            "Write a blog post (300–400 words) about a useful or interesting topic in the field of "
            "technology or IT. Choose the subject yourself, and make sure it's relevant to professionals "
            "in networking, infrastructure, cybersecurity, DevOps, or cloud computing. You can write "
            "about a concept, a tool, a setup guide, or a real-world best practice. Use a helpful tone, "
            "include practical examples or explanations, and start the post with a markdown H1 title. "
            "Avoid repeating tools or topics already covered. The post should be easy to understand "
            "for both beginners and experienced professionals."
        )
        title, content = generate_and_review_post(prompt, is_default_prompt=True)
    else:  # choice == "1"
        prompt = (
            f"Write a short blog post (300–400 words) about a useful open-source tool "
            f"for IT professionals or network engineers. Avoid these tools: {exclude_string}. "
            "Start with a markdown H1 title. Include real examples and a helpful tone."
        )
        title, content = generate_and_review_post(prompt, is_default_prompt=True)

    if not title or not content:
        continue

    # === SAVE USED TITLE AND TOOL NAME ===
    with open(used_titles_path, "a", encoding="utf-8") as f:
        f.write(title.strip() + "\n")

    if choice == "1":  # Only track excluded tools for default prompt
        tool_candidate = title.split(":")[0].strip()
        if tool_candidate.lower() not in [t.lower() for t in excluded_tools]:
            with open(excluded_tools_path, "a", encoding="utf-8") as f:
                f.write(tool_candidate + "\n")

    # === CREATE POST ===
    status = "publish"
    log(f"📤 Creating post: {title}")

    post_response = requests.post(
        f"{BASE_URL}/posts",
        auth=(USERNAME, APP_PASSWORD),
        json={
            "title": title,
            "content": content,
            "status": status
        }
    )

    if post_response.status_code == 201:
        post_data = post_response.json()
        post_url = post_data['link']
        post_title = post_data['title']['rendered']
        log(f"✅ Post published at {post_url}")
    else:
        log(f"❌ Failed to publish post. Status: {post_response.status_code}")
        log(post_response.text)
        exit()

    # === FETCH /BLOG PAGE ===
    log("📥 Fetching blog page...")
    page_response = requests.get(
        f"{BASE_URL}/pages?slug=blog&context=edit",
        auth=(USERNAME, APP_PASSWORD)
    )

    if page_response.status_code != 200 or not page_response.json():
        log("❌ Failed to fetch the /blog page.")
        exit()

    blog_page = page_response.json()[0]
    page_id = blog_page['id']
    existing_content = blog_page['content']['raw']

    # === BACKUP EXISTING BLOG PAGE ===
    with open(backup_file, "w", encoding="utf-8") as backup:
        backup.write(existing_content)
    log(f"🧾 Blog content backed up to: {backup_file}")

    # === INSERT NEW LINK INTO RECENT POSTS LIST ===
    new_list_item = f'<li><a href="{post_url}">{post_title}</a></li>'

    # Matches the <h2>Recent Posts</h2> followed by the list block
    pattern = r'(<h2 class="wp-block-heading">Recent Posts<\/h2>.*?<ul class="wp-block-list">)(.*?)(</ul>)'
    match = re.search(pattern, existing_content, flags=re.DOTALL)

    # === Validate Pattern Match ===
    if not match:
        log("❌ Could not locate the 'Recent Posts' section. Aborting update.")
        exit()
    else:
        log("✅ Found 'Recent Posts' section. Inserting new post link...")

    # === Insert New Post Link ===
    existing_list_items = match.group(2).strip()
    updated_list = f"{new_list_item}\n{existing_list_items}".strip()

    # Replace inside the existing blog page HTML
    updated_recent_posts = match.group(1) + updated_list + match.group(3)
    updated_content = re.sub(pattern, updated_recent_posts, existing_content, flags=re.DOTALL)

    # === UPDATE /BLOG PAGE ===
    update_response = requests.put(
        f"{BASE_URL}/pages/{page_id}",
        auth=(USERNAME, APP_PASSWORD),
        json={"content": updated_content}
    )

    if update_response.status_code == 200:
        log("✅ /blog page updated — post link added to Recent Posts.")
    else:
        log(f"❌ Failed to update /blog page. Status: {update_response.status_code}")
        log(update_response.text)
