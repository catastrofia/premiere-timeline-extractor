import re
from dataclasses import dataclass
from typing import Optional, Callable, List, Dict, Any

@dataclass
class SourceMatch:
    """A dataclass to hold the results of a source recognition match."""
    source: str
    media_id: Optional[str] = None
    title: Optional[str] = None

class SourceResolver:
    """
    Resolves clip names to source providers using a registry of regex patterns.
    """
    def __init__(self):
        self._registry: List[Dict[str, Any]] = [
            {
                "name": "Imago",
                "regex": re.compile(r"imago(\d+)(?:_([^.]+))?", re.IGNORECASE),
                "parser": lambda m: SourceMatch(
                    source="Imago",
                    media_id=m.group(1),
                    title=m.group(2).replace('_', ' ').strip() if m.group(2) else "[No Title]"
                )
            },
            {
                "name": "Colourbox",
                "regex": re.compile(r"COLOURBOX(\d+)(?:_([^.]+))?", re.IGNORECASE),
                "parser": lambda m: SourceMatch(
                    source="Colourbox",
                    media_id=m.group(1),
                    title=m.group(2).replace('_', ' ').strip() if m.group(2) else "[No Title]"
                )
            },
            {
                "name": "Artlist",
                # Captures everything between the ID and the By/From marker
                "regex": re.compile(r"(\d+)_(.*?)_(?:By|From)_.*_Artlist", re.IGNORECASE),
                "parser": lambda m: SourceMatch(
                    source="Artlist",
                    media_id=m.group(1),
                    title=m.group(2).replace('_', ' ').strip() if m.group(2) else "[No Title]"
                )
            }
        ]
        self.default_match = SourceMatch(source="Unknown")

    def resolve(self, clip_name: str) -> SourceMatch:
        """
        Iterates through the registry to find a matching source for the given clip name.

        Args:
            clip_name: The name of the clip to analyze.

        Returns:
            A SourceMatch object with the parsed data, or a default 'Unknown' match.
        """
        if not clip_name:
            return self.default_match

        for entry in self._registry:
            match = entry["regex"].search(clip_name)
            if match:
                return entry["parser"](match)
        
        return self.default_match