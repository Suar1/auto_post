# Auto Post Script

This script automates the process of generating and publishing blog posts using OpenAI's GPT model and a WordPress API. It also updates the `/blog` page with a link to the newly created post.

## Requirements

### Files Needed
The following files must be present in the same directory as `auto_post.py`:

1. **`api.key`**  
   Contains your OpenAI API key. The file should have the key as plain text.

2. **`blog_config.env`**  
   Contains configuration variables for the WordPress API. The file should have the following format:
   ```
   BASE_URL=https://your-wordpress-site.com/wp-json/wp/v2
   USERNAME=your-username
   APP_PASSWORD=your-app-password
   ```

3. **`used_titles.txt`**  
   A text file to store titles of previously generated posts to avoid duplicates. If the file does not exist, it will be created automatically.

4. **`excluded_tools.txt`**  
   A text file containing a list of tools to exclude from the generated blog posts. Each tool should be on a new line. If the file does not exist, it will be created automatically.

### Python Dependencies
Make sure you have the following Python libraries installed:
- `requests`
- `openai`
- `re`

You can install the required libraries using:
```bash
pip install requests openai
```

## How to Use
1. Place all the required files in the same directory as `auto_post.py`.
2. Run the script:
   ```bash
   python auto_post.py
   ```
3. The script will:
   - Generate a blog post using OpenAI's GPT model.
   - Publish the post to your WordPress site.
   - Update the `/blog` page with a link to the new post.

## Logs and Backups
- **Log File**: `post_log.txt`  
  Contains logs of the script's operations.
  
- **Backup File**: `blog_backup_<timestamp>.html`  
  A backup of the `/blog` page before it is updated.

## Notes
- Ensure your WordPress site has the REST API enabled and that the credentials in `blog_config.env` are correct.
- The script will automatically create `used_titles.txt` and `excluded_tools.txt` if they do not exist.