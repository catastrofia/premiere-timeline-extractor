import os
import time
import logging
from datetime import datetime, timedelta
from typing import List, Optional

# Default TTL for uploaded files (24 hours)
DEFAULT_TTL_HOURS = 24

def cleanup_uploads(upload_dir: str, ttl_hours: int = DEFAULT_TTL_HOURS) -> List[str]:
    """
    Clean up old files in the uploads directory based on TTL.
    
    Args:
        upload_dir: Path to the uploads directory
        ttl_hours: Time-to-live in hours (default: 24 hours)
        
    Returns:
        List of removed file paths
    """
    if not os.path.exists(upload_dir):
        logging.warning(f"Upload directory {upload_dir} does not exist")
        return []
    
    removed_files = []
    current_time = time.time()
    ttl_seconds = ttl_hours * 3600
    
    try:
        for filename in os.listdir(upload_dir):
            file_path = os.path.join(upload_dir, filename)
            
            # Skip directories
            if os.path.isdir(file_path):
                continue
                
            # Check file age
            file_modified_time = os.path.getmtime(file_path)
            if current_time - file_modified_time > ttl_seconds:
                try:
                    os.remove(file_path)
                    removed_files.append(file_path)
                    logging.info(f"Removed old upload: {file_path}")
                except Exception as e:
                    logging.error(f"Failed to remove {file_path}: {str(e)}")
    except Exception as e:
        logging.error(f"Error during upload cleanup: {str(e)}")
    
    return removed_files

def schedule_cleanup(upload_dir: str, ttl_hours: int = DEFAULT_TTL_HOURS) -> None:
    """
    Schedule cleanup to run on application startup.
    This is a simple implementation that runs once when called.
    For production, consider using a proper scheduler like APScheduler.
    
    Args:
        upload_dir: Path to the uploads directory
        ttl_hours: Time-to-live in hours (default: 24 hours)
    """
    logging.info(f"Running scheduled cleanup of uploads directory: {upload_dir}")
    removed = cleanup_uploads(upload_dir, ttl_hours)
    if removed:
        logging.info(f"Cleanup removed {len(removed)} files")
    else:
        logging.info("No files needed cleanup")