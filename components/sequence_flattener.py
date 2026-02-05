"""
Sequence flattening utilities for Premiere Pro timelines.
Handles recursive flattening of nested sequences into a linear timeline.
"""
from typing import Dict, List, Optional, Tuple, Any, Set
import defusedxml.ElementTree as ET
from xml.etree.ElementTree import Element
from dataclasses import dataclass, field
from components.logger import get_logger
from components.xml_parser import ln, int_or_none

logger = get_logger()

@dataclass
class TrackItem:
    """Represents a track item in a Premiere Pro sequence."""
    ti_obj: Element
    start: Optional[int] = None
    end: Optional[int] = None
    duration: Optional[int] = None
    sequence_ref: Optional[str] = None
    display_name: Optional[str] = None
    source_path: Optional[str] = None
    source_filename: Optional[str] = None

@dataclass
class FlattenedInstance:
    """Represents a flattened timeline instance."""
    name: Optional[str] = None
    start_raw: Optional[int] = None
    end_raw: Optional[int] = None
    source_sequence: Optional[str] = None
    source_path: Optional[str] = None
    source_filename: Optional[str] = None
    is_nested_container: bool = False

class SequenceFlattener:
    """Flattens nested sequences in Premiere Pro projects."""
    
    def __init__(self, objectid_map: Dict[str, Element], objectuid_map: Dict[str, Element],
                 sequence_name_map: Dict[str, Element]):
        """
        Initialize the sequence flattener.
        
        Args:
            objectid_map: Map of ObjectID to elements
            objectuid_map: Map of ObjectUID to elements
            sequence_name_map: Map of sequence names to sequence elements
        """
        self.objectid_map = objectid_map
        self.objectuid_map = objectuid_map
        self.sequence_name_map = sequence_name_map
    
    def track_uids_for_sequence(self, seq_elem: Element) -> List[str]:
        """
        Find track UIDs for a sequence element.
        
        Args:
            seq_elem: Sequence element
            
        Returns:
            List of track UIDs
        """
        refs = []
        # Find TrackGroup elements
        for tg in seq_elem.iter():
            if ln(tg.tag).lower() == 'trackgroup':
                for child in tg:
                    if ln(child.tag).lower() == 'second':
                        ref = child.get('ObjectRef') or (child.text.strip() if child.text else None)
                        if ref:
                            refs.append(ref)
        
        # Find track UIDs from the references
        uids = []
        for gid in refs:
            group = self.objectid_map.get(gid)
            if not group:
                continue
                
            for tracks in group.iter():
                if ln(tracks.tag).lower() == 'tracks':
                    for tr in tracks:
                        if ln(tr.tag).lower() == 'track':
                            ouref = tr.get('ObjectURef') or (tr.text.strip() if tr.text else None)
                            if ouref:
                                uids.append(ouref)
        
        # Deduplicate while preserving order
        return list(dict.fromkeys([u for u in uids if u]))
    
    def track_items_for_trackuid(self, tuid: str) -> List[TrackItem]:
        """
        Extract track items from a track UID.
        
        Args:
            tuid: Track UID
            
        Returns:
            List of TrackItem objects
        """
        items = []
        track_elem = self.objectuid_map.get(tuid)
        if not track_elem:
            return items
            
        for child in track_elem.iter():
            if ln(child.tag).lower() in ('clipitems', 'trackitems'):
                for ti_list in child.iter():
                    if ln(ti_list.tag).lower() in ('trackitems', 'clipitems'):
                        for ti in ti_list:
                            # Prefer ObjectRef attribute
                            ref = ti.get('ObjectRef') or (ti.text.strip() if ti.text else None)
                            if not ref and ti.get('ObjectRef'):
                                ref = ti.get('ObjectRef')
                                
                            if ref and ref in self.objectid_map:
                                ti_obj = self.objectid_map[ref]
                                
                                # Parse details
                                start = None
                                end = None
                                duration = None
                                seqref = None
                                subclip_ref = None
                                display_name = None
                                source_path = None
                                source_filename = None
                                
                                for d in ti_obj.iter():
                                    l = ln(d.tag).lower()
                                    
                                    # Extract name
                                    if l == 'name' and d.text:
                                        display_name = d.text.strip()
                                        
                                    # Extract file path or filename
                                    path_tags = ('pathurl', 'path', 'filepath', 'mediaurl', 'mediafile', 
                                               'fullpath', 'filename', 'url', 'title', 
                                               'actualmediafilepath', 'relativepath', 'filekey')
                                    if l in path_tags and d.text:
                                        txt = d.text.strip()
                                        if '/' in txt or '\\' in txt or '.' in txt:
                                            source_path = txt
                                            # Extract filename from path
                                            import os as _os
                                            try:
                                                source_filename = _os.path.basename(txt)
                                            except Exception:
                                                source_filename = txt
                                    
                                    # Extract timing information
                                    if l in ('start', 'in', 'inpoint') and d.text:
                                        v = int_or_none(d.text.strip())
                                        if v is not None:
                                            start = v
                                    if l in ('end', 'outpoint') and d.text:
                                        v = int_or_none(d.text.strip())
                                        if v is not None:
                                            end = v
                                    if l in ('duration', 'length') and d.text:
                                        v = int_or_none(d.text.strip())
                                        if v is not None:
                                            duration = v
                                    
                                    # Extract sequence references
                                    if l == 'subclip':
                                        r = d.get('ObjectRef') or (d.text.strip() if d.text else None)
                                        if r:
                                            subclip_ref = r
                                    if l == 'sequencesource':
                                        for s in d:
                                            if ln(s.tag).lower() == 'sequence' and s.get('ObjectURef'):
                                                seqref = s.get('ObjectURef')
                                    if l == 'sequence' and d.get('ObjectURef'):
                                        seqref = d.get('ObjectURef')
                                
                                # If display_name not on track item, try subclip/masterclip
                                if not display_name and subclip_ref and subclip_ref in self.objectid_map:
                                    sc = self.objectid_map[subclip_ref]
                                    
                                    # Try to find name in subclip
                                    for n in sc.iter():
                                        if ln(n.tag).lower() == 'name' and n.text:
                                            display_name = n.text.strip()
                                            break
                                        
                                        # Try to find path in subclip
                                        path_tags = ('pathurl', 'path', 'filepath', 'filename', 'url', 'title',
                                                   'actualmediafilepath', 'relativepath', 'filekey')
                                        if ln(n.tag).lower() in path_tags and n.text:
                                            txt = n.text.strip()
                                            if '/' in txt or '\\' in txt or '.' in txt:
                                                source_path = txt
                                                import os as _os
                                                try:
                                                    source_filename = _os.path.basename(txt)
                                                except Exception:
                                                    source_filename = txt
                                    
                                    # If still no display name, try masterclip
                                    if not display_name:
                                        mref = sc.get('ObjectURef')
                                        for ch in sc:
                                            if ln(ch.tag).lower() == 'masterclip' and ch.get('ObjectURef'):
                                                mref = ch.get('ObjectURef')
                                                
                                        if mref and mref in self.objectuid_map:
                                            mc = self.objectuid_map[mref]
                                            
                                            # Try to find name in masterclip
                                            for n in mc.iter():
                                                if ln(n.tag).lower() == 'name' and n.text:
                                                    display_name = n.text.strip()
                                                    break
                                                
                                                # Try to find path in masterclip
                                                path_tags = ('pathurl', 'path', 'filepath', 'filename', 'url', 'title',
                                                           'actualmediafilepath', 'relativepath', 'filekey')
                                                if ln(n.tag).lower() in path_tags and n.text:
                                                    txt = n.text.strip()
                                                    if '/' in txt or '\\' in txt or '.' in txt:
                                                        source_path = txt
                                                        import os as _os
                                                        try:
                                                            source_filename = _os.path.basename(txt)
                                                        except Exception:
                                                            source_filename = txt
                                
                                # Create TrackItem and add to list
                                items.append(TrackItem(
                                    ti_obj=ti_obj,
                                    start=start,
                                    end=end,
                                    duration=duration,
                                    sequence_ref=seqref,
                                    display_name=display_name,
                                    source_path=source_path,
                                    source_filename=source_filename
                                ))
        
        return items
    
    def flatten_sequence(self, seq_elem: Element, parent_offset_raw: int = 0,
                         parent_bound_raw: Optional[int] = None, 
                         source_sequence_name: Optional[str] = None) -> List[FlattenedInstance]:
        """
        Recursively flatten a sequence and its nested sequences.
        
        Args:
            seq_elem: Sequence element to flatten
            parent_offset_raw: Offset in raw ticks from parent sequence
            parent_bound_raw: Upper bound in raw ticks from parent sequence
            source_sequence_name: Name of the source sequence
            
        Returns:
            List of flattened instances
        """
        instances = []
        
        # Get track UIDs for this sequence
        tuids = self.track_uids_for_sequence(seq_elem)
        
        # Process each track
        for tu in tuids:
            # Get items for this track
            items = self.track_items_for_trackuid(tu)
            
            # Process each item
            for itm in items:
                start = itm.start
                end = itm.end
                duration = itm.duration
                
                # Skip structural entries without start time
                if start is None:
                    continue
                    
                # Calculate end time if not provided
                if end is None and duration is not None:
                    end = start + duration
                    
                # Skip if we still don't have an end time
                if end is None:
                    continue
                    
                # Calculate absolute start/end times
                abs_start = parent_offset_raw + start
                abs_end = parent_offset_raw + end
                
                # If this item references another sequence, expand recursively
                if itm.sequence_ref:
                    seq_uid = itm.sequence_ref
                    nested_seq = None
                    
                    # Sequence refs may be ObjectUIDs or ObjectIDs depending on file
                    if seq_uid in self.objectuid_map:
                        nested_seq = self.objectuid_map[seq_uid]
                    elif seq_uid in self.objectid_map:
                        nested_seq = self.objectid_map[seq_uid]
                        
                    if nested_seq is not None and ln(nested_seq.tag).lower() == 'sequence':
                        # Find the nested sequence name
                        nested_seq_name = None
                        for c in nested_seq.iter():
                            if ln(c.tag).lower() == 'name' and c.text:
                                nested_seq_name = c.text.strip()
                                break
                                
                        # Add the nested sequence container to the instances
                        instances.append(FlattenedInstance(
                            name=nested_seq_name,
                            start_raw=abs_start,
                            end_raw=abs_end,
                            source_sequence=source_sequence_name,
                            is_nested_container=True
                        ))
                        
                        # Recursively flatten the nested sequence
                        nested_instances = self.flatten_sequence(
                            nested_seq, 
                            parent_offset_raw=abs_start, 
                            parent_bound_raw=abs_end, 
                            source_sequence_name=nested_seq_name
                        )
                        
                        # Add the nested instances to our list
                        instances.extend(nested_instances)
                else:
                    # If the track item name matches a known Sequence name, expand that sequence
                    name = itm.display_name
                    nested_seq = None
                    
                    if name and name in self.sequence_name_map:
                        nested_seq = self.sequence_name_map[name]
                        
                    if nested_seq is not None:
                        # Add the nested sequence container to the instances
                        instances.append(FlattenedInstance(
                            name=name,
                            start_raw=abs_start,
                            end_raw=abs_end,
                            source_sequence=source_sequence_name,
                            is_nested_container=True
                        ))
                        
                        # Recursively flatten the nested sequence
                        nested_instances = self.flatten_sequence(
                            nested_seq, 
                            parent_offset_raw=abs_start, 
                            parent_bound_raw=abs_end, 
                            source_sequence_name=name
                        )
                        
                        # Add the nested instances to our list
                        instances.extend(nested_instances)
                    else:
                        # If a parent bound is set, clamp the child's end and drop if completely outside
                        if parent_bound_raw is not None:
                            if abs_start >= parent_bound_raw:
                                # Starts at/after parent bound -> skip
                                continue
                                
                            if abs_end > parent_bound_raw:
                                abs_end = parent_bound_raw
                                
                            if abs_end <= abs_start:
                                continue
                                
                        # Add this item as a flattened instance
                        instances.append(FlattenedInstance(
                            name=name,
                            start_raw=abs_start,
                            end_raw=abs_end,
                            source_sequence=source_sequence_name,
                            source_path=itm.source_path,
                            source_filename=itm.source_filename
                        ))
        
        logger.debug(f"Flattened {len(instances)} instances from sequence '{source_sequence_name or 'Main'}'")
        return instances
    
    def filter_unnamed_clips(self, instances: List) -> List:
        """
        Filter out unnamed clips.
        
        Args:
            instances: List of flattened instances (FlattenedInstance or dict)
            
        Returns:
            Filtered list of instances
        """
        filtered = []
        for instance in instances:
            # Support both FlattenedInstance objects and dicts
            if isinstance(instance, dict):
                name = instance.get('name')
            else:
                name = instance.name
                
            if not name:
                continue
                
            if isinstance(name, str) and name.startswith('<unnamed-'):
                continue
                
            filtered.append(instance)
            
        return filtered
    
    def deduplicate_instances(self, instances: List) -> List:
        """
        Deduplicate instances with the same name, parent sequence, and timecodes.
        
        Args:
            instances: List of flattened instances (FlattenedInstance or dict)
            
        Returns:
            Deduplicated list of instances
        """
        seen = set()
        unique_instances = []
        
        for instance in instances:
            # Support both FlattenedInstance objects and dicts
            if isinstance(instance, dict):
                name = instance.get('name')
                parent = instance.get('source_sequence') or 'Main'
                start = instance.get('start_tc') or instance.get('start_sec')
                end = instance.get('end_tc') or instance.get('end_sec')
            else:
                name = instance.name
                parent = instance.source_sequence or 'Main'
                start = instance.start_raw
                end = instance.end_raw
            
            key = (name, parent, start, end)
            
            if key not in seen:
                seen.add(key)
                unique_instances.append(instance)
                
        return unique_instances