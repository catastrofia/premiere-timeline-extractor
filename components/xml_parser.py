"""
XML parsing utilities for Premiere Pro project files.
Handles parsing XML content and building object maps.
"""
import defusedxml.ElementTree as ET
from xml.etree.ElementTree import Element
from dataclasses import dataclass
from typing import Dict, List, Optional, Tuple, Any
import gzip
import os
from components.logger import get_logger

logger = get_logger()

@dataclass
class ParsedProject:
    """Container for parsed Premiere Pro project data."""
    root: Element
    objectid_map: Dict[str, Element]
    objectuid_map: Dict[str, Element]
    sequence_name_map: Dict[str, Element]

def load_project_file(path: str) -> str:
    """
    Reads a .prproj (gzipped) or unzipped XML file and returns its content as a string.
    
    Args:
        path: Path to the project file
        
    Returns:
        XML content as string
    """
    logger.info(f"Loading project file: {path}")
    
    with open(path, "rb") as f:
        data = f.read()
        
    try:
        # Try to decompress, assuming it's a gzipped .prproj
        xml_data = gzip.decompress(data)
        logger.debug("Successfully decompressed gzipped project file")
    except (gzip.BadGzipFile, OSError):
        # If it fails, it's likely already unzipped XML
        xml_data = data
        logger.debug("File appears to be uncompressed XML")
        
    return xml_data.decode('utf-8', errors='replace')

def ln(tag: str) -> str:
    """
    Extract local name from namespaced XML tag.
    
    Args:
        tag: XML tag, potentially with namespace
        
    Returns:
        Local tag name without namespace
    """
    return tag.split('}')[-1] if '}' in tag else tag

def int_or_none(s: Any) -> Optional[int]:
    """
    Safely convert a value to integer, returning None on failure.
    
    Args:
        s: Value to convert
        
    Returns:
        Integer value or None if conversion fails
    """
    try:
        return int(s)
    except (ValueError, TypeError):
        try:
            return int(float(s))
        except (ValueError, TypeError):
            return None

class XMLProjectParser:
    """Parser for Premiere Pro XML project files."""
    
    def parse(self, xml_content: str) -> ParsedProject:
        """
        Parse XML content and build object maps.
        
        Args:
            xml_content: XML content as string
            
        Returns:
            ParsedProject containing the parsed data
        """
        logger.info("Parsing XML content")
        root = ET.fromstring(xml_content)
        
        # Build maps
        objectid_map = {}
        objectuid_map = {}
        sequence_name_map = {}
        
        # Populate object maps
        for el in root.iter():
            # Map ObjectID attributes
            oid = el.get('ObjectID')
            if oid:
                objectid_map[oid] = el
                
            # Map ObjectUID attributes
            ouid = el.get('ObjectUID')
            if ouid:
                objectuid_map[ouid] = el
                
            # Map sequence names to sequence elements
            tag = ln(el.tag).lower()
            if tag == 'sequence':
                for c in el.iter():
                    if ln(c.tag).lower() == 'name' and c.text:
                        sequence_name_map[c.text.strip()] = el
                        break
        
        logger.debug(f"Parsed {len(objectid_map)} ObjectID elements, {len(objectuid_map)} ObjectUID elements, and {len(sequence_name_map)} sequences")
        
        return ParsedProject(
            root=root,
            objectid_map=objectid_map,
            objectuid_map=objectuid_map,
            sequence_name_map=sequence_name_map
        )
    
    def find_sequence_by_name(self, root: ET.Element, name: str) -> Optional[ET.Element]:
        """
        Find a sequence element by its name.
        
        Args:
            root: Root XML element
            name: Sequence name to find
            
        Returns:
            Sequence element or None if not found
        """
        for e in root.iter():
            if ln(e.tag).lower() == 'sequence':
                for c in e.iter():
                    if ln(c.tag).lower() == 'name' and c.text and c.text.strip() == name:
                        return e
        return None
    
    def find_frame_rate_for_sequence(self, seq_elem: ET.Element, objectid_map: Dict[str, ET.Element]) -> Optional[int]:
        """
        Find the frame rate value for a sequence.
        
        Args:
            seq_elem: Sequence element
            objectid_map: Map of ObjectID to elements
            
        Returns:
            Frame rate value or None if not found
        """
        # First look in the sequence's TrackGroup
        for tg in seq_elem.iter():
            if ln(tg.tag).lower() == 'trackgroup':
                for child in tg:
                    if ln(child.tag).lower() == 'second':
                        gid = child.get('ObjectRef') or (child.text.strip() if child.text else None)
                        if gid and gid in objectid_map:
                            group = objectid_map[gid]
                            for g in group.iter():
                                if ln(g.tag).lower() == 'framerate' and g.text:
                                    v = int_or_none(g.text.strip())
                                    if v:
                                        return v
        
        # If not found in sequence, look for any framerate element
        root = seq_elem.getroot()
        for e in root.iter():
            if ln(e.tag).lower() == 'framerate' and e.text:
                v = int_or_none(e.text.strip())
                if v:
                    return v
                    
        return None
    
    def list_named_sequences(self, root: ET.Element) -> List[str]:
        """
        List all named sequences in the project.
        
        Args:
            root: Root XML element
            
        Returns:
            List of sequence names
        """
        seqs = []
        for e in root.iter():
            if ln(e.tag).lower() == 'sequence':
                for c in e.iter():
                    if ln(c.tag).lower() == 'name' and c.text and c.text.strip():
                        seqs.append(c.text.strip())
                        break
        return seqs