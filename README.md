# Auto Blog Post Generator and Manager

> [!IMPORTANT]
> **NOTICE: This repository is no longer actively updated or maintained.**

A comprehensive Flask application for automating blog post generation, management, and WordPress integration with advanced backup capabilities and AI-powered content creation.

## 🌟 Features

### Post Generation and Management
- 🤖 AI-powered blog post generation using OpenAI GPT
- 📝 Multiple post types support (IT Tool Review, General, Guide)
- 📋 Title management with copy and delete functionality
- 🔄 WordPress synchronization
- 📊 Post categorization and tagging
- 📅 Post scheduling and auto-publishing
- 🔍 Duplicate post detection using embeddings
- 📝 Post preview before publishing

### WordPress Integration
- 🔗 Automatic post publishing to WordPress
- 🔄 Two-way synchronization with WordPress blog
- 📑 Category-based organization
- 🏷️ Automatic tag generation and management
- 🔍 Duplicate post detection
- ⏰ Scheduled auto-sync functionality

### Topic Management
- 📚 Topic suggestion and generation
- 🔍 Similarity checking using embeddings
- 📊 Topic analytics and statistics
- 🗑️ Topic cleanup and maintenance
- 📋 All blog topics view
- 📝 Title management interface

### Backup System
- 💾 Automated backup system
- 🔐 Encryption for secure backups
- 📧 Email notifications after backups
- 📁 User-specific backup folders
- ⚙️ Configurable backup settings
- 📥 Backup download and restore functionality

### Admin Features
- 👥 User management dashboard
- 🔐 Admin authentication
- 👤 User impersonation (for support)
- 🗑️ User deletion capabilities

### Security Features
- 🔒 User authentication and authorization
- 🔑 Encrypted storage of sensitive data
- 🚫 Rate limiting for API endpoints
- 🔐 Secure credential management
- 📝 Comprehensive logging

## 🚀 Getting Started

### Prerequisites
- Python 3.8 or higher
- Docker and Docker Compose (optional)
- WordPress site with REST API access
- OpenAI API key

### Installation

1. **Clone the repository**
   ```bash
   git clone [repository-url]
   cd Auto_post
   ```

2. **Set up environment variables**
   
   Create a `blog_config.env` file in the root directory:
   ```env
   MAIL_SERVER=smtp.gmail.com
   MAIL_PORT=587
   MAIL_USE_TLS=True
   MAIL_USERNAME=your_email@gmail.com
   MAIL_PASSWORD=your_app_password
   MAIL_DEFAULT_SENDER=your_email@gmail.com
   ```

3. **Install dependencies**
   ```bash
   pip install -r requirements.txt
   ```

4. **Initialize the database**
   ```bash
   python app.py
   ```
   The database will be automatically initialized on first run.

5. **Run the application**
   ```bash
   python app.py
   ```
   The application will run on `http://0.0.0.0:5001`

### Docker Installation (Optional)

1. **Build and run with Docker Compose**
   ```bash
   docker-compose up -d
   ```

2. **View logs**
   ```bash
   docker-compose logs -f
   ```

## 📁 Project Structure

```
Auto_post/
├── app.py                 # Main application file
├── models.py             # Database models and user management
├── services.py           # Business logic and WordPress/OpenAI services
├── utils.py              # Utility functions and helpers
├── embeddings.py         # Embedding generation and similarity checking
├── ensure_dirs.py        # Directory initialization
├── blog_config.env       # Environment configuration
├── requirements.txt      # Python dependencies
├── Dockerfile            # Docker configuration
├── docker-compose.yml    # Docker Compose configuration
│
├── auth_routes.py        # Authentication routes (login, register, logout)
├── generate_routes.py    # Post generation routes
├── settings_routes.py    # User settings and backup routes
├── topic_routes.py       # Topic management routes
├── admin_routes.py       # Admin dashboard routes
│
├── templates/            # HTML templates
│   ├── base.html
│   ├── index.html
│   ├── login.html
│   ├── register.html
│   ├── generate.html
│   ├── settings.html
│   ├── topics.html
│   ├── all_blog_topics.html
│   ├── all_titles.html
│   ├── posts.html
│   ├── preview.html
│   ├── admin.html
│   └── user_settings.html
│
├── static/               # Static files
│   └── css/
│       └── style.css
│
├── generated/            # Generated files (created at runtime)
│   ├── backups/         # Backup storage
│   └── logs/            # Application logs
│
├── user_data/            # User-specific data (created at runtime)
│   └── user_{id}/       # Per-user directories
│
├── instance/             # Flask instance folder
└── topic_embeddings.json # Topic embeddings cache
```

## 🔧 Configuration

### Environment Variables

The application uses `blog_config.env` for configuration:

- `MAIL_SERVER`: SMTP server address
- `MAIL_PORT`: SMTP port (default: 587)
- `MAIL_USE_TLS`: Use TLS (True/False)
- `MAIL_USERNAME`: Email username
- `MAIL_PASSWORD`: Email password/app password
- `MAIL_DEFAULT_SENDER`: Default sender email

### User Settings (Configured in App)

Each user can configure:
- WordPress URL, username, and password
- OpenAI API key
- Custom prompts (tool, general, guide)
- Auto-sync settings
- Backup preferences (encryption, email notifications)
- Sync interval and scheduling

### WordPress Setup

1. Enable REST API in WordPress
2. Create an application password:
   - Go to Users → Profile
   - Scroll to Application Passwords
   - Create a new application password
3. Configure in the app's settings page:
   - WordPress URL
   - WordPress username
   - Application password

## 📖 Usage

### Creating Your First Post

1. **Register/Login**: Create an account or login
2. **Configure Settings**: 
   - Add your WordPress credentials
   - Add your OpenAI API key
   - Customize prompts if needed
3. **Generate Post**:
   - Go to Generate page
   - Choose post type (Tool Review, General, Guide)
   - Enter a topic or use topic suggestion
   - Generate and review the post
4. **Publish**: Preview and publish to WordPress

### Managing Topics

- View all topics at `/topics`
- Check topic similarity before creating posts
- Generate unique topics
- Clean up old embeddings

### Backup and Restore

- Enable automatic backups in settings
- Download latest backup
- Restore from backup file
- Configure encryption and email notifications

## 🛠️ Development

### Running in Development Mode

```bash
export FLASK_ENV=development
python app.py
```

### Database Migrations

The application automatically handles database migrations. The `migrate_db()` function in `app.py` ensures all required columns exist.

### Code Structure

- **Routes**: Organized in separate blueprint files
- **Services**: Business logic separated from routes
- **Models**: Database models and user management
- **Utils**: Helper functions and utilities

## 📝 API Endpoints

### Authentication
- `GET/POST /login` - User login
- `GET/POST /register` - User registration
- `GET /logout` - User logout

### Post Generation
- `GET /generate` - Generate post page
- `POST /generate/suggest-topic` - Suggest unique topic
- `POST /generate/post` - Generate blog post
- `GET /generate/preview/<post_id>` - Preview post
- `POST /generate/publish/<post_id>` - Publish to WordPress
- `POST /generate/sync` - Sync posts with WordPress

### Topics
- `GET /topics` - View all topics
- `POST /topics/check-similarity` - Check topic similarity
- `GET /all_blog_topics` - View all blog topics
- `GET /all_titles` - View all titles
- `POST /generate_post` - Generate post from topic
- `POST /sync_titles` - Sync titles with WordPress

### Settings
- `GET/POST /settings` - User settings page
- `GET /download-latest-backup` - Download backup
- `POST /restore-backup` - Restore from backup
- `POST /sync-posts` - Manual sync
- `GET /export-data` - Export user data
- `POST /import-data` - Import user data

### Admin
- `GET /admin` - Admin dashboard
- `POST /admin/impersonate/<user_id>` - Impersonate user
- `POST /admin/delete/<user_id>` - Delete user

## 🔍 Monitoring

### Logging

- Application logs: `generated/logs/app.log`
- Post logs: `generated/logs/post_log.txt`
- Rotating file handlers with size limits
- Logging level: WARNING (configurable)

## 🚀 Production Deployment

### Using Docker

```bash
docker-compose up -d
```

### Manual Deployment

1. Set up a production server
2. Configure environment variables
3. Use a production WSGI server (Gunicorn)
4. Set up Nginx reverse proxy
5. Enable SSL/TLS
6. Configure proper logging

### Security Considerations

- Use strong SECRET_KEY
- Enable HTTPS
- Configure proper CORS
- Set up rate limiting
- Regular backups
- Monitor logs

## 📝 License

This project is licensed under the MIT License - see the LICENSE file for details.

## 🤝 Contributing

1. Fork the repository
2. Create a feature branch
3. Commit your changes
4. Push to the branch
5. Create a Pull Request

See CONTRIBUTING.md for more details.

## 🐛 Known Issues

- Rate limiting may need adjustment for high-traffic sites
- Large backup files may need chunking
- Some WordPress themes may require custom formatting
- Embeddings cache may grow large over time (use cleanup feature)

## 🚀 Future Improvements

### Content Enhancement
- 🎯 AI-powered SEO optimization for posts
- 📊 Analytics integration for post performance tracking
- 🖼️ Automatic featured image generation
- 🔍 Advanced duplicate content detection
- 📱 Social media post auto-generation

### User Experience
- 🎨 Customizable themes and UI preferences
- 📱 Mobile-responsive improvements
- 🔔 Real-time notifications
- 📝 Rich text editor with markdown support
- 🏷️ Drag-and-drop interface

### Technical Enhancements
- 💽 Support for multiple database backends (PostgreSQL, MySQL)
- 🔍 Full-text search capabilities
- 🔄 WebSocket support for real-time updates
- 🚀 GraphQL API implementation
- 🔄 Background task queuing with Celery

### Backup and Security
- ☁️ Multi-cloud backup support (AWS S3, Google Cloud Storage)
- 🔐 Two-factor authentication
- 📊 Backup analytics and reporting
- 🔄 Point-in-time recovery
- 🛡️ Advanced rate limiting and DDoS protection

## 📞 Support

For support, please:
1. Check the documentation
2. Search existing issues
3. Create a new issue if needed

## 🔄 Recent Updates

- Added topic management with embeddings
- Improved WordPress synchronization
- Enhanced backup system with encryption
- Added admin dashboard
- Improved duplicate detection
- Added scheduled auto-sync
- Enhanced logging and monitoring
