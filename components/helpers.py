import html
import re
from typing import Any, Dict, List, Match, Optional


def sanitize_html(content: Any) -> str:
    """
    Sanitize HTML content to prevent XSS attacks.
    
    Args:
        content: The content to sanitize
        
    Returns:
        Sanitized content safe for HTML rendering
    """
    if content is None:
        return ""
    
    # Convert to string if not already
    if not isinstance(content, str):
        content = str(content)
    
    # Escape HTML special characters
    escaped = html.escape(content)
    
    # Allow only a very limited set of HTML tags if needed
    # This is an example of a whitelist approach - only allow specific tags
    allowed_tags: Dict[str, List[str]] = {
        'b': [], 'i': [], 'u': [], 'br': [], 'p': [],
        'span': ['class', 'style'], 'a': ['href', 'target']
    }
    
    # Function to replace allowed tags back
    def replace_tag(match: Match[str]) -> str:
        tag = match.group(1).lower()
        if tag not in allowed_tags:
            return match.group(0)  # Keep escaped
        
        attrs = match.group(2)
        if attrs:
            # Filter attributes
            allowed_attrs = allowed_tags[tag]
            if allowed_attrs:
                # Parse attributes
                attr_matches = re.finditer(r'(\w+)=["\'](.*?)["\']', attrs)
                filtered_attrs = []
                for attr_match in attr_matches:
                    attr_name = attr_match.group(1).lower()
                    if attr_name in allowed_attrs:
                        attr_value = html.escape(attr_match.group(2))
                        filtered_attrs.append(f'{attr_name}="{attr_value}"')
                
                attrs = ' ' + ' '.join(filtered_attrs) if filtered_attrs else ''
            else:
                attrs = ''
        
        return f"<{tag}{attrs}>"
    
    # Replace opening tags
    escaped = re.sub(r'&lt;(\w+)(.*?)&gt;', replace_tag, escaped)
    
    # Replace closing tags
    escaped = re.sub(r'&lt;/(\w+)&gt;', lambda m: f"</{m.group(1).lower()}>" if m.group(1).lower() in allowed_tags else m.group(0), escaped)
    
    return escaped

def tc_to_seconds(tc: Optional[str]) -> int:
    """
    Converts HH:MM:SS timecode string to seconds.
    
    Args:
        tc: Timecode string in HH:MM:SS format
        
    Returns:
        Equivalent time in seconds as integer
    """
    if not tc:
        return 0
    parts = tc.split(':')
    if len(parts) != 3:
        return 0
    try:
        h, m, s = map(int, parts)
        return h * 3600 + m * 60 + s
    except (ValueError, TypeError):
        return 0


def tc_from_seconds(s: int) -> str:
    """
    Converts seconds to HH:MM:SS timecode string.
    
    Args:
        s: Time in seconds
        
    Returns:
        Formatted timecode string
    """
    s_round = int(round(s))
    if s_round < 0:
        sign = '-'
        s_abs = -s_round
    else:
        sign = ''
        s_abs = s_round
    hh = s_abs // 3600
    mm = (s_abs % 3600) // 60
    ss = s_abs % 60
    return f"{sign}{hh:02d}:{mm:02d}:{ss:02d}"