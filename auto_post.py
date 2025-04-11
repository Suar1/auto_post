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

import os

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

# === GENERATE BLOG POST WITH GPT ===
log("🧠 Generating content from ChatGPT...")

exclude_string = ", ".join(excluded_tools)
prompt = (
    f"Write a short blog post (300–400 words) about a useful open-source tool "
    f"for IT professionals or network engineers. Avoid these tools: {exclude_string}. "
    "Start with a markdown H1 title. Include real examples and a helpful tone."
)

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
        exit()

    first_line = content.splitlines()[0].strip()
    if first_line.startswith("#"):
        extracted_title = first_line.lstrip("#").strip()
        content = "\n".join(content.splitlines()[1:]).strip()
    else:
        extracted_title = f"Automated Post - {datetime.now().strftime('%Y-%m-%d')}"

    if extracted_title.lower() not in used_titles:
        break

    log(f"⚠️ Duplicate title detected: '{extracted_title}', generating a new one...")

title = extracted_title

# === SAVE USED TITLE AND TOOL NAME ===
with open(used_titles_path, "a", encoding="utf-8") as f:
    f.write(title.strip() + "\n")

# Try to extract the tool name from the title (assumes it's the first word or phrase)
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

# === INSERT NEW LINK INTO EXISTING LIST ===
new_list_item = f'<li><a href="{post_url}">{post_title}</a></li>'

pattern = r'(<h2 class="wp-block-heading">Recent Posts<\/h2>.*?<ul class="wp-block-list">)(.*?)(</ul>)'
match = re.search(pattern, existing_content, flags=re.DOTALL)

if not match:
    log("❌ Could not locate the 'Recent Posts' section.")
    exit()

existing_list_items = match.group(2).strip()
updated_list = f"{new_list_item}\n{existing_list_items}".strip()

updated_content = match.group(1) + updated_list + match.group(3)

# === UPDATE /BLOG PAGE ===
update_response = requests.post(
    f"{BASE_URL}/pages/{page_id}",
    auth=(USERNAME, APP_PASSWORD),
    json={"content": updated_content}
)

if update_response.status_code == 200:
    log("✅ /blog page updated — post link added to Recent Posts.")
else:
    log(f"❌ Failed to update /blog page. Status: {update_response.status_code}")
    log(update_response.text)
