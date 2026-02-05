"""
Configuration settings for the Premiere Pro timeline extractor.
Centralizes all constants and configuration values.
"""
from dataclasses import dataclass, field
from typing import Dict, Set
import os

@dataclass
class Config:
    # Application settings
    SECRET_KEY: str = field(default_factory=lambda: os.environ.get('FLASK_SECRET_KEY', ''))
    UPLOAD_FOLDER: str = 'uploads'
    MAX_UPLOAD_SIZE: int = 500 * 1024 * 1024  # 500 MB
    
    # Timeline settings
    DEFAULT_FPS: float = 23.976
    MIN_CLIP_DURATION: float = 1.0
    DEFAULT_TIMELINE_CAP: float = 40.0  # Default cap in seconds
    
    # Mapping of raw frame rate values to common FPS values
    FPS_MAP: Dict[int, float] = field(default_factory=lambda: {
        10594584: 23.976,  # 23.976 fps
        10160640: 25,      # 25 fps
        8475667: 29.97,    # 29.97 fps
        8408400: 30,       # 30 fps
        5080320: 50,       # 50 fps
        4237833: 59.94,    # 59.94 fps
        4204200: 60        # 60 fps
    })
    
    # File extension sets for clip type detection
    VIDEO_EXT: Set[str] = field(default_factory=lambda: {
        '.mp4', '.mov', '.mkv', '.avi', '.wmv', '.mxf', '.m2ts', '.m2t', 
        '.mts', '.mpeg', '.mpg', '.flv', '.webm', '.3gp', '.ogv'
    })
    
    AUDIO_EXT: Set[str] = field(default_factory=lambda: {
        '.wav', '.mp3', '.aac', '.flac', '.aiff', '.m4a', '.ogg', '.wma', '.alac'
    })
    
    IMAGE_EXT: Set[str] = field(default_factory=lambda: {
        '.jpg', '.jpeg', '.png', '.tif', '.tiff', '.bmp', '.gif', '.svg', 
        '.heic', '.webp', '.psd', '.raw', '.exr'
    })
    
    GRAPHIC_EXT: Set[str] = field(default_factory=lambda: {
        '.aegraphic', '.mogrt', '.aep', '.aepx'
    })
    
    # Upload validation
    ALLOWED_EXT: Set[str] = field(default_factory=lambda: {'.prproj', '.xml'})

# Create a singleton instance
config = Config()