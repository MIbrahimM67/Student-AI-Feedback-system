import os
import logging
import shutil
from typing import Optional

logger = logging.getLogger(__name__)

# Base directory inside the Docker container
UPLOAD_DIR = "/app/uploads"

def init_storage():
    """Ensure the uploads directory exists."""
    os.makedirs(UPLOAD_DIR, exist_ok=True)

def save_file(content: bytes, blob_name: str) -> str:
    """
    Saves file bytes to the local upload directory.
    Creates necessary subdirectories based on blob_name (e.g., 'references/org_id/subject_id/file.pdf').
    Returns the relative HTTP path to access the file.
    """
    init_storage()
    
    # Clean the blob name to avoid absolute path issues
    clean_blob_name = blob_name.lstrip("/")
    
    # Construct absolute filesystem path
    file_path = os.path.join(UPLOAD_DIR, clean_blob_name)
    
    # Ensure parent directories exist
    os.makedirs(os.path.dirname(file_path), exist_ok=True)
    
    # Write the file
    with open(file_path, "wb") as f:
        f.write(content)
        
    logger.info(f"Saved file to local storage: {file_path}")
    
    # Return the URL path that FastAPI's StaticFiles will serve
    return f"/uploads/{clean_blob_name}"

def delete_file(blob_name: str) -> bool:
    """
    Deletes a file from the local upload directory if it exists.
    """
    clean_blob_name = blob_name.lstrip("/")
    file_path = os.path.join(UPLOAD_DIR, clean_blob_name)
    
    if os.path.exists(file_path):
        try:
            os.remove(file_path)
            logger.info(f"Deleted local file: {file_path}")
            return True
        except Exception as e:
            logger.error(f"Failed to delete local file {file_path}: {e}")
            return False
    return False

def get_local_path(file_url: str) -> Optional[str]:
    """
    Converts a /uploads/... URL to the absolute internal Docker path /app/uploads/...
    Returns None if the URL does not belong to local storage.
    """
    if file_url and file_url.startswith("/uploads/"):
        return f"/app{file_url}"
    return None
