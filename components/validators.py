import os
from typing import Any, Optional, Set

ALLOWED_EXT: Set[str] = {'.prproj', '.xml'}
MAX_SIZE: int = 500 * 1024 * 1024  # 500 MB


def validate_upload(file: Any, content_length: Optional[int]) -> None:
    """
    Validate file upload based on extension and size.
    
    Args:
        file: The uploaded file object (werkzeug FileStorage)
        content_length: Content length from request headers
        
    Raises:
        ValueError: If validation fails with specific error message
    """
    if not file or not file.filename:
        raise ValueError('No file provided')
        
    ext = os.path.splitext(file.filename)[1].lower()
    if ext not in ALLOWED_EXT:
        raise ValueError(f'Invalid file type: {ext}. Allowed types: {", ".join(ALLOWED_EXT)}')
        
    if content_length and content_length > MAX_SIZE:
        raise ValueError(f'File too large. Maximum size: {MAX_SIZE / (1024 * 1024):.1f} MB')