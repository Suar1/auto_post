import os
import logging

def ensure_directories():
    """Ensure all required directories exist"""
    directories = [
        'user_data',
        'generated/logs',
        'generated/backups'
    ]
    
    for directory in directories:
        try:
            os.makedirs(directory, exist_ok=True)
            logging.info(f"✅ Directory created/verified: {directory}")
        except Exception as e:
            logging.error(f"❌ Failed to create directory {directory}: {str(e)}")

if __name__ == '__main__':
    # Configure logging
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - %(levelname)s - %(message)s'
    )
    
    ensure_directories() 