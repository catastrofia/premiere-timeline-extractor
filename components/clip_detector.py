"""
Clip type detection for Premiere Pro timeline items.
Determines clip types (Video, Audio, Image, Graphic) based on file extensions and heuristics.
"""
import re
from typing import Dict, List, Optional, Set, Tuple, Any, Union
import defusedxml.ElementTree as ET
from xml.etree.ElementTree import Element
from config import config
from components.logger import get_logger
from components.xml_parser import ln

logger = get_logger()

class ClipTypeDetector:
    """Detects clip types based on file extensions and heuristics."""
    
    def __init__(self):
        """Initialize the clip type detector with extension sets from config."""
        self.video_exts = config.VIDEO_EXT
        self.audio_exts = config.AUDIO_EXT
        self.image_exts = config.IMAGE_EXT
        self.graphic_exts = config.GRAPHIC_EXT
    
    def find_extension_in_string(self, s: Optional[str]) -> Optional[str]:
        """
        Extract a file extension from a string.
        
        Args:
            s: String to search for extension
            
        Returns:
            File extension (with dot) or None if not found
        """
        if not s:
            return None
            
        # Normalize whitespace and lowercase
        ss = re.sub(r"\s+", " ", s.lower())
        
        # Look for a file extension pattern
        m = re.search(r"\.([a-z0-9]{2,20})(?:\b|$)", ss)
        if m:
            return '.' + m.group(1)
            
        return None
    
    def detect_clip_type(self, 
                         name: Optional[str], 
                         source_filename: Optional[str], 
                         source_path: Optional[str]) -> Tuple[str, Optional[str]]:
        """
        Determine clip type based on name, source filename, and path.
        
        Args:
            name: Clip name
            source_filename: Source file name
            source_path: Source file path
            
        Returns:
            Tuple of (clip_type, debug_source) where clip_type is one of:
            'Video', 'Audio', 'Image', 'Graphic', 'Unknown'
        """
        # Collect all candidate strings to check
        candidates = []
        if source_filename:
            candidates.append(source_filename.lower())
        if source_path:
            candidates.append(source_path.lower())
        if name and isinstance(name, str):
            candidates.append(name.lower())
        
        # Try to detect type based on file extension
        for c in candidates:
            ext = self.find_extension_in_string(c)
            if ext:
                if ext in self.video_exts:
                    return ('Video', f'candidate:{c}')
                if ext in self.audio_exts:
                    return ('Audio', f'candidate:{c}')
                if ext in self.image_exts:
                    return ('Image', f'candidate:{c}')
                if ext in self.graphic_exts:
                    return ('Graphic', f'candidate:{c}')
        
        # Heuristic fallbacks based on name keywords
        if name:
            name_lower = name.lower()
            graphic_keywords = ['graphic', 'title', 'caption', 'overlay', 'lowerthird', 'grad']
            if any(k in name_lower for k in graphic_keywords):
                return ('Graphic', 'heuristic:name')
        
        # Heuristic based on source path containing graphics/templates folder
        if source_path:
            path_lower = source_path.lower()
            graphic_folders = ['graphics', 'templates', 'motion graphics', 'mogrt']
            if any(k in path_lower for k in graphic_folders):
                return ('Graphic', 'heuristic:source_path')
        
        # Final fallback
        return ('Unknown', None)
    
    def find_extension_in_project(self, 
                                 name: Optional[str],
                                 root: Element) -> Optional[Tuple[str, str, str]]:
        """
        Search the entire project for an extension associated with the clip name.
        
        Args:
            name: Clip name to search for
            root: Root XML element of the project
            
        Returns:
            Tuple of (extension, tag_name, text) or None if not found
        """
        if not name:
            return None
            
        lname = name.lower()
        
        # Look for any element text that contains the clip name and a dot-extension
        for e in root.iter():
            txt = (e.text or '')
            if not txt:
                continue
                
            # Normalize whitespace and lowercase for robust matching
            ltxt = re.sub(r"\s+", " ", txt.lower())
            
            if lname in ltxt and '.' in ltxt:
                ext = self.find_extension_in_string(ltxt)
                if ext:
                    return (ext, ln(e.tag), txt.strip())
                    
        return None
    
    def detect_from_project_search(self, 
                                  name: str,
                                  root: Element) -> Tuple[str, Optional[str]]:
        """
        Detect clip type by searching the project for extension references.
        Used when initial detection returns 'Unknown'.
        
        Args:
            name: Clip name
            root: Root XML element of the project
            
        Returns:
            Tuple of (clip_type, debug_source)
        """
        ext_info = self.find_extension_in_project(name, root)
        if not ext_info:
            return ('Unknown', None)
            
        ext, tag, txt = ext_info
        ext_l = ext.lower()
        
        # Classify based on extension
        if ext_l in self.graphic_exts:
            ctype = 'Graphic'
        elif ext_l in self.audio_exts:
            ctype = 'Audio'
        elif ext_l in self.image_exts:
            ctype = 'Image'
        elif ext_l in self.video_exts:
            ctype = 'Video'
        else:
            return ('Unknown', None)
            
        # Update debug source to point to project element used
        dbg_source = f'project_element:{tag}:{txt[:180]}'
        logger.debug(f"Clip '{name}' classified as {ctype} from extension {ext} found in <{tag}>")
        
        return (ctype, dbg_source)