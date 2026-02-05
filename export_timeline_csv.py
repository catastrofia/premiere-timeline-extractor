#!/usr/bin/env python3
"""
Core logic for exporting a Premiere Pro timeline to CSV.
"""
import csv
import sys
import os
import argparse
import io
import gzip
from typing import Dict, List, Optional, Tuple, Any, Set

# Import configuration and logging
from config import config
from components.logger import get_logger, DEBUG

# Import components
from components.xml_parser import XMLProjectParser, ln, int_or_none
from components.time_converter import (
    tc_from_seconds, tc_to_seconds, seconds_aligned_from_raw, 
    get_fps_from_raw_value, ensure_minimum_duration
)
from components.clip_detector import ClipTypeDetector
from components.sequence_flattener import SequenceFlattener
from components.source_resolver import SourceResolver

# Get logger
logger = get_logger()

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

def generate_timeline_data(
    xml_content: str, 
    main_seq_name: str, 
    fps_override: Optional[float] = None, 
    cap: Optional[float] = None, 
    debug: bool = False, 
    debug_log_path: Optional[str] = None
) -> Tuple[Dict, Dict, float, int]:
    """
    Processes XML content from a .prproj file.
    
    Args:
        xml_content: XML content from a .prproj file
        main_seq_name: Name of the main sequence to process
        fps_override: Optional FPS override value
        cap: Optional cap in seconds for the timeline
        debug: Enable debug logging
        debug_log_path: Optional path to write debug log
        
    Returns:
        Tuple of (grouped_data, per_instance_data, fps_to_use, frame_rate_value)
        Each data dictionary contains 'headers' and 'rows'.
    """
    # Set up debug logging if requested
    if debug:
        logger.setLevel(DEBUG)
    
    # Initialize components
    xml_parser = XMLProjectParser()
    clip_detector = ClipTypeDetector()
    resolver = SourceResolver()
    
    # Parse the XML content
    logger.info(f"Parsing XML content for sequence: {main_seq_name}")
    parsed_project = xml_parser.parse(xml_content)
    
    # Find the main sequence
    main_seq = xml_parser.find_sequence_by_name(parsed_project.root, main_seq_name)
    if not main_seq:
        error_msg = f"Main sequence not found: {main_seq_name}"
        logger.error(error_msg)
        raise ValueError(error_msg)
    
    logger.info(f"Found main sequence element for '{main_seq_name}'")
    
    # Find the frame rate for the sequence
    frame_rate_value = xml_parser.find_frame_rate_for_sequence(main_seq, parsed_project.objectid_map)
    if not frame_rate_value:
        logger.warning(f"FrameRate for sequence '{main_seq_name}' was NOT found. Time conversion may be incorrect.")
        fps_to_use = config.DEFAULT_FPS
    else:
        # Map raw value to common FPS
        familiar_fps, is_common = get_fps_from_raw_value(frame_rate_value)
        
        if is_common:
            logger.info(f"Successfully found FrameRate for sequence '{main_seq_name}': {frame_rate_value} (Interpreted as {familiar_fps} FPS)")
        else:
            logger.info(f"Successfully found FrameRate for sequence '{main_seq_name}': {frame_rate_value} (Uncommon value)")
        
        fps_to_use = fps_override if fps_override is not None else familiar_fps
    
    logger.info(f"Using FPS: {fps_to_use} (ticks_per_frame: {frame_rate_value})")
    
    # Initialize the sequence flattener
    flattener = SequenceFlattener(
        parsed_project.objectid_map,
        parsed_project.objectuid_map,
        parsed_project.sequence_name_map
    )
    
    # Flatten the sequence
    all_instances = flattener.flatten_sequence(main_seq, parent_offset_raw=0)
    logger.info(f"Collected {len(all_instances)} raw instances from sequence '{main_seq_name}' before filtering")
    
    # Convert to seconds aligned and apply cap
    processed = []
    for instance in all_instances:
        s_raw = instance.start_raw
        e_raw = instance.end_raw
        
        if frame_rate_value is None:
            logger.warning(f"Skipping instance due to missing frame_rate_value: {instance.name}")
            continue
            
        s_sec = seconds_aligned_from_raw(s_raw, frame_rate_value, fps_to_use)
        e_sec = seconds_aligned_from_raw(e_raw, frame_rate_value, fps_to_use)
        
        if s_sec is None or e_sec is None:
            continue
            
        # Drop instances that start at or after cap
        if cap is not None and s_sec >= cap:
            continue
            
        if cap is not None and e_sec > cap:
            e_sec = cap
            
        if e_sec <= s_sec:
            # Skip degenerate
            continue
            
        # Ensure minimum duration
        s_sec, e_sec = ensure_minimum_duration(s_sec, e_sec)
        
        # Carry through source info if available
        processed.append({
            'name': instance.name,
            'start_sec': s_sec,
            'end_sec': e_sec,
            'start_tc': tc_from_seconds(s_sec),
            'end_tc': tc_from_seconds(e_sec),
            'source_path': instance.source_path,
            'source_filename': instance.source_filename,
            'source_sequence': instance.source_sequence,
            'is_nested_container': instance.is_nested_container
        })
    
    logger.info(f"{len(processed)} instances remaining after time conversion and capping")
    
    # Filter out unnamed clips
    filtered = flattener.filter_unnamed_clips(processed)
    logger.info(f"{len(filtered)} instances remaining after filtering unnamed clips")
    
    # Deduplicate instances
    processed = flattener.deduplicate_instances(filtered)
    logger.info(f"{len(processed)} instances remaining after deduplication by (name, parent_sequence, start_tc, end_tc)")
    
    # Group by name
    groups = {}
    for p in processed:
        # Don't include the nested sequence containers in the grouped data for the table
        if p.get('is_nested_container'):
            continue
        key = p['name']
        groups.setdefault(key, []).append(p)
    
    # Build per-instance data
    per_instances = []
    for grp_name, instances in groups.items():
        source_match = resolver.resolve(grp_name)
        insts_sorted = sorted(instances, key=lambda x: x['start_sec'])
        
        # Detect type using first instance's source info
        first = insts_sorted[0]
        ctype, dbg_source = clip_detector.detect_clip_type(
            grp_name, 
            first.get('source_filename'), 
            first.get('source_path')
        )
        
        # If still unknown, try project-wide search
        if ctype == 'Unknown':
            ctype, dbg_source = clip_detector.detect_from_project_search(grp_name, parsed_project.root)
            
        for i in insts_sorted:
            # Use rounded HH:MM:SS timecodes already computed in start_tc/end_tc
            per_instances.append({
                'name': grp_name,
                'start_sec': i['start_sec'],
                'end_sec': i['end_sec'],
                'start_tc': i['start_tc'],
                'end_tc': i['end_tc'],
                'clip_type': ctype,
                'source_sequence': i.get('source_sequence'),
                'source': source_match.source,
                'media_id': source_match.media_id,
                'source_title': source_match.title
            })
    
    # Sort all instances chronologically by start_sec
    per_instances_sorted = sorted(per_instances, key=lambda x: x['start_sec'])
    
    # Per-user request: only output HH:MM:SS timecodes, no floating-point seconds columns
    per_instance_headers = ['clip_name', 'startTC', 'endTC', 'clip_type', 'source_sequence', 'source', 'media_id', 'source_title']
    per_instance_rows = [
        [inst['name'], inst['start_tc'], inst['end_tc'], inst['clip_type'], inst.get('source_sequence'), 
         inst.get('source'), inst.get('media_id'), inst.get('source_title')]
        for inst in per_instances_sorted
    ]
    per_instance_data = {'headers': per_instance_headers, 'rows': per_instance_rows}
    
    logger.info('Generating "grouped" CSV')
    rows = []
    for name, instances in groups.items():
        source_match = resolver.resolve(name)
        insts_sorted = sorted(instances, key=lambda x: x['start_sec'])
        
        # Merge overlapping intervals
        intervals = [(i['start_sec'], i['end_sec']) for i in insts_sorted]
        merged = []
        if intervals:
            current_start, current_end = intervals[0]
            for start, end in intervals[1:]:
                if start <= current_end:
                    current_end = max(current_end, end)
                else:
                    merged.append((current_start, current_end))
                    current_start, current_end = start, end
            merged.append((current_start, current_end))
            
        inst_strings = [f"{tc_from_seconds(s)}-{tc_from_seconds(e)}" for s, e in merged]
        earliest = insts_sorted[0]['start_sec']
        
        # Detect type using first instance's source info
        first = insts_sorted[0]
        ctype, dbg_source = clip_detector.detect_clip_type(
            name, 
            first.get('source_filename'), 
            first.get('source_path')
        )
        
        # If still unknown, try project-wide search
        if ctype == 'Unknown':
            ctype, dbg_source = clip_detector.detect_from_project_search(name, parsed_project.root)
        
        rows.append({
            'name': name,
            'instances_count': len(insts_sorted),
            'instances_str': ' | '.join(inst_strings),
            'earliest_start': earliest,
            'clip_type': ctype,
            'source': source_match.source,
            'media_id': source_match.media_id,
            'source_title': source_match.title
        })
    
    # Sort rows chronologically by earliest instance
    rows_sorted = sorted(rows, key=lambda x: x['earliest_start'])
    
    grouped_headers = ['clip_name', 'instances_count', 'instances(start-end pipe-separated)', 'clip_type', 'source', 'media_id', 'source_title']
    grouped_rows = [
        [r['name'], r['instances_count'], r['instances_str'], r.get('clip_type', 'Unknown'), 
         r.get('source'), r.get('media_id'), r.get('source_title')]
        for r in rows_sorted
    ]
    grouped_data = {'headers': grouped_headers, 'rows': grouped_rows}
    
    return grouped_data, per_instance_data, fps_to_use, frame_rate_value

def list_named_sequences_from_content(xml_content: str) -> List[str]:
    """
    Parses XML content and returns a list of named sequences.
    
    Args:
        xml_content: XML content from a .prproj file
        
    Returns:
        List of sequence names
    """
    xml_parser = XMLProjectParser()
    parsed_project = xml_parser.parse(xml_content)
    return list(parsed_project.sequence_name_map.keys())

def generate_timeline_csv_string(data_dict: Dict) -> str:
    """
    Helper to convert the data dictionary to a CSV string for file download.
    
    Args:
        data_dict: Data dictionary with 'headers' and 'rows'
        
    Returns:
        CSV content as string
    """
    output = io.StringIO()
    writer = csv.writer(output)
    if 'headers' in data_dict:
        writer.writerow(data_dict['headers'])
    if 'rows' in data_dict:
        writer.writerows(data_dict['rows'])
    return output.getvalue()

if __name__=='__main__':
    parser = argparse.ArgumentParser(description='Export flattened Premiere .prproj timeline to CSV')
    parser.add_argument('--input','-i',required=False,help='path to unzipped .prproj XML file')
    parser.add_argument('--sequence','-s',required=False,help='sequence name to process (defaults to first named sequence)')
    parser.add_argument('--fps',type=float,required=False,help='override FPS (e.g. 23.976)')
    parser.add_argument('--cap',type=float,default=config.DEFAULT_TIMELINE_CAP,help=f'sequence length cap in seconds (default {config.DEFAULT_TIMELINE_CAP})')
    parser.add_argument('--debug',action='store_true',help='enable debug audit prints')
    parser.add_argument('--list-sequences',action='store_true',help='list named sequences and exit')
    parser.add_argument('--debug-log',required=False,help='path to write debug log (optional)')
    parser.add_argument('--out','-o',required=False,help='output CSV file path (optional). If omitted a descriptive name project__sequence_timeline.csv will be used in the input file directory')
    parser.add_argument('--per-instance',action='store_true',help='write one CSV row per clip instance instead of grouping by clip name')
    args = parser.parse_args()

    # Configure logging
    if args.debug:
        logger.setLevel(logger.DEBUG)
    if args.debug_log:
        from components.logger import setup_logging
        setup_logging(level=logger.DEBUG, log_file=args.debug_log)

    # Choose input
    # For privacy, do not hardcode any project file path. Require --input or exit.
    if not args.input:
        logger.error('Error: --input is required. Please provide the path to an unzipped .prproj XML file.')
        sys.exit(2)
    
    path = args.input
    xml_content_main = load_project_file(path)

    # List sequences if requested
    if args.list_sequences:
        seqs = list_named_sequences_from_content(xml_content_main)
        logger.info('Found sequences:')
        for s in seqs:
            logger.info(f' - {s}')
        sys.exit(0)

    main_seq_name = args.sequence
    # Choose main sequence: provided name or prompt user to pick from detected sequences
    if not main_seq_name:
        seqs = list_named_sequences_from_content(xml_content_main)
        if not seqs:
            logger.error('No named sequences found in project; aborting')
            sys.exit(1)
        # If running non-interactively (no TTY), default to the first named sequence
        try:
            interactive = sys.stdin.isatty()
        except Exception:
            interactive = False
        if not interactive:
            main_seq_name = seqs[0]
            if args.debug:
                logger.debug(f"No sequence provided and not interactive; defaulting to first named sequence: {main_seq_name}")
        else:
            # Prompt the user to choose
            logger.info('Found named sequences:')
            for idx, s in enumerate(seqs, start=1):
                logger.info(f" {idx}) {s}")
            while True:
                choice = input(f"Enter sequence number or full name to process (default 1), or Q to quit: ").strip()
                if not choice:
                    main_seq_name = seqs[0]
                    break
                if choice.lower() == 'q':
                    logger.info('Quitting.')
                    sys.exit(0)
                # Numeric choice
                if choice.isdigit():
                    n = int(choice)
                    if 1 <= n <= len(seqs):
                        main_seq_name = seqs[n-1]
                        break
                # Exact case-insensitive match
                matches = [s for s in seqs if s.lower() == choice.lower()]
                if len(matches) == 1:
                    main_seq_name = matches[0]
                    break
                # Single partial match
                matches = [s for s in seqs if choice.lower() in s.lower()]
                if len(matches) == 1:
                    main_seq_name = matches[0]
                    break
                if len(matches) > 1:
                    logger.info('Multiple matches: ' + ', '.join(matches[:10]))
                    continue
                logger.info('Invalid choice, try again.')

    grouped_data, per_instance_data, _, _ = generate_timeline_data(
        xml_content=xml_content_main,
        main_seq_name=main_seq_name,
        fps_override=args.fps,
        cap=args.cap,
        debug=args.debug,
        debug_log_path=args.debug_log)

    final_data = per_instance_data if args.per_instance else grouped_data

    # Determine output path: use --out if provided, otherwise construct descriptive name from input file and sequence
    if args.out:
        out_path = args.out
    else:
        input_base = os.path.splitext(os.path.basename(path))[0]
        # Sanitize sequence name for filename
        def sanitize(s):
            if not s: return 'sequence'
            safe = ''.join(ch if (ch.isalnum() or ch in '-._') else '_' for ch in s)
            return safe[:120]
        seq_safe = sanitize(main_seq_name)
        out_filename = f"{input_base}__{seq_safe}_timeline.csv"
        # Place output file in the same directory as the input file
        input_dir = os.path.dirname(os.path.abspath(path)) or os.getcwd()
        out_path = os.path.join(input_dir, out_filename)

    with open(out_path, 'w', encoding='utf-8') as f:
        f.write(generate_timeline_csv_string(final_data))

    logger.info(f'Wrote CSV to {out_path}')
