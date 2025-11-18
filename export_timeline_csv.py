#!/usr/bin/env python3
import csv
import sys
import os
import argparse
import io
import gzip
import math
from xml.etree import ElementTree as ET
"""
Core logic for exporting a Premiere Pro timeline to CSV.
"""

# This is a circular import if not handled carefully.
# I created a separate helpers file to avoid this.
from components.helpers import tc_from_seconds, tc_to_seconds

def ln(t):
    return t.split('}')[-1] if '}' in t else t

def int_or_none(s):
    try:
        return int(s)
    except Exception:
        try:
            return int(float(s))
        except Exception:
            return None

def seconds_aligned_from_raw(raw, ticks_per_frame, fps_override):
    # Premiere stores TrackItem Start/End in integer 'ticks'. The TrackGroup/FrameRate
    # element in the sequence appears to hold the number of ticks per frame (not ticks/sec).
    # So: frames = raw / ticks_per_frame; seconds = frames / fps_override
    if raw is None or ticks_per_frame is None or fps_override is None:
        return None
    frames = float(raw) / float(ticks_per_frame)
    # frames should be integral (or very close); align to nearest frame
    frames_rounded = round(frames)
    seconds = frames_rounded / float(fps_override)
    return seconds

def generate_timeline_data(xml_content, main_seq_name, fps_override=23.976, cap=None, debug=False, debug_log_path=None):
    """
    Processes XML content from a .prproj file.
    Returns two dictionaries, one for grouped data and one for per-instance data.
    Each dictionary contains 'headers' and 'rows'.
    """
    DEBUG = debug
    def log(msg):
        print(msg)
        if debug_fh:
            try:
                debug_fh.write(str(msg)+"\n")
            except Exception:
                pass

    debug_fh = None
    if debug_log_path:
        try:
            debug_fh = open(debug_log_path,'w',encoding='utf-8')
        except Exception as e:
            print('Warning: could not open debug log for writing:', e)

    root = ET.fromstring(xml_content)

    # build maps
    objectid_map = {}
    objectuid_map = {}
    for e in root.iter():
        oid = e.get('ObjectID')
        ouid = e.get('ObjectUID')
        if oid:
            objectid_map[oid]=e
        if ouid:
            objectuid_map[ouid]=e

    # helper to find sequence element by name
    def find_sequence_by_name(name):
        for e in root.iter():
            if ln(e.tag).lower()=='sequence':
                for c in e.iter():
                    if ln(c.tag).lower()=='name' and c.text and c.text.strip()==name:
                        return e
        return None

    main = find_sequence_by_name(main_seq_name)
    log(f"Found main sequence element for '{main_seq_name}'.")
    if not main:
        raise ValueError(f'Main sequence not found: {main_seq_name}')

    # build map of sequence name -> sequence element to help expand nested sequences
    sequence_name_map = {}
    for e in root.iter():
        if ln(e.tag).lower()=='sequence':
            nm = None
            for c in e.iter():
                if ln(c.tag).lower()=='name' and c.text:
                    nm = c.text.strip(); break
            if nm:
                sequence_name_map[nm]=e

    # find frame_rate raw value similarly to the flattener
    def find_frame_rate_for_sequence(seq_elem):
        for tg in seq_elem.iter():
            if ln(tg.tag).lower()=='trackgroup':
                for child in tg:
                    if ln(child.tag).lower()=='second':
                        gid = child.get('ObjectRef') or (child.text.strip() if child.text else None)
                        if gid and gid in objectid_map:
                            group = objectid_map[gid]
                            for g in group.iter():
                                if ln(g.tag).lower()=='framerate' and g.text:
                                    v=int_or_none(g.text.strip())
                                    if v:
                                        return v
        for e in root.iter():
            if ln(e.tag).lower()=='framerate' and e.text:
                v=int_or_none(e.text.strip())
                if v:
                    return v
        return None

    frame_rate_value = find_frame_rate_for_sequence(main)
    if not frame_rate_value:
        log(f'[DEBUG] FrameRate for sequence "{main_seq_name}" was NOT found. Time conversion may be incorrect.')
        log(f'Warning: Could not find FrameRate for sequence "{main_seq_name}". Time conversion may be incorrect.')
        log('Warning: could not find raw frame-rate; time conversion may be incorrect')
        print('Warning: could not find raw frame-rate; time conversion may be incorrect')
    else:
        # Map raw value to common FPS
        fps_map = {
            10594584: 23.976, 10160640: 25, 8475667: 29.97, 8408400: 30,
            5080320: 50, 4237833: 59.94, 4204200: 60
        }
        familiar_fps = fps_map.get(frame_rate_value)

        # Handle cases where the value from XML is scaled (e.g., by 1000)
        if not familiar_fps:
            temp_val = frame_rate_value
            while temp_val > 1000000: # A reasonable lower bound for these tick values
                if temp_val in fps_map:
                    familiar_fps = fps_map[temp_val]
                    break
                temp_val //= 10 # Scale down and try again

        if familiar_fps:
            log(f'[DEBUG] Successfully found FrameRate for sequence "{main_seq_name}": {frame_rate_value} (Interpreted as {familiar_fps} FPS).')
        else:
            log(f'[DEBUG] Successfully found FrameRate for sequence "{main_seq_name}": {frame_rate_value} (Uncommon value).')


    # helper to find track UIDs for a sequence element
    def track_uids_for_sequence(seq_elem):
        refs = []
        for tg in seq_elem.iter():
            if ln(tg.tag).lower()=='trackgroup':
                for child in tg:
                    if ln(child.tag).lower()=='second':
                        ref = child.get('ObjectRef') or (child.text.strip() if child.text else None)
                        if ref:
                            refs.append(ref)
        uids = []
        for gid in refs:
            group = objectid_map.get(gid)
            if not group: continue
            for tracks in group.iter():
                if ln(tracks.tag).lower()=='tracks':
                    for tr in tracks:
                        if ln(tr.tag).lower()=='track':
                            ouref = tr.get('ObjectURef') or (tr.text.strip() if tr.text else None)
                            if ouref:
                                uids.append(ouref)
        # dedupe
        return list(dict.fromkeys([u for u in uids if u]))

    # helper to extract track items from a track UID
    def track_items_for_trackuid(tuid):
        items = []
        track_elem = objectuid_map.get(tuid)
        if not track_elem:
            return items
        for child in track_elem.iter():
            if ln(child.tag).lower() in ('clipitems','trackitems'):
                for ti_list in child.iter():
                    if ln(ti_list.tag).lower() in ('trackitems','clipitems'):
                        for ti in ti_list:
                            # prefer ObjectRef attribute
                            ref = ti.get('ObjectRef') or (ti.text.strip() if ti.text else None)
                            if not ref and ti.get('ObjectRef'):
                                ref = ti.get('ObjectRef')
                            if ref and ref in objectid_map:
                                ti_obj = objectid_map[ref]
                                # parse details
                                start=None; end=None; duration=None; seqref=None; subclip_ref=None; display_name=None
                                # try to capture a source path/filename in addition to display name
                                source_path = None
                                source_filename = None
                                for d in ti_obj.iter():
                                    l = ln(d.tag).lower()
                                    if l=='name' and d.text:
                                        display_name = d.text.strip()
                                    # common tags that may carry file path or filename
                                    if l in ('pathurl','path','filepath','mediaurl','mediafile','fullpath','filename','url','title','actualmediafilepath','relativepath','filekey') and d.text:
                                        txt = d.text.strip()
                                        if '/' in txt or '\\' in txt or '.' in txt:
                                            source_path = txt
                                            # try to extract filename
                                            import os as _os
                                            try:
                                                source_filename = _os.path.basename(txt)
                                            except Exception:
                                                source_filename = txt
                                    if l in ('start','in','inpoint') and d.text:
                                        v = int_or_none(d.text.strip());
                                        if v is not None: start=v
                                    if l in ('end','outpoint') and d.text:
                                        v = int_or_none(d.text.strip());
                                        if v is not None: end=v
                                    if l in ('duration','length') and d.text:
                                        v = int_or_none(d.text.strip());
                                        if v is not None: duration=v
                                    if l=='subclip':
                                        r = d.get('ObjectRef') or (d.text.strip() if d.text else None)
                                        if r: subclip_ref = r
                                    if l=='sequencesource':
                                        for s in d:
                                            if ln(s.tag).lower()=='sequence' and s.get('ObjectURef'):
                                                seqref = s.get('ObjectURef')
                                    if l=='sequence' and d.get('ObjectURef'):
                                        seqref = d.get('ObjectURef')
                                # if display_name not on track item, try subclip/masterclip
                                if not display_name and subclip_ref and subclip_ref in objectid_map:
                                    sc = objectid_map[subclip_ref]
                                    for n in sc.iter():
                                        if ln(n.tag).lower()=='name' and n.text:
                                            display_name = n.text.strip(); break
                                        if ln(n.tag).lower() in ('pathurl','path','filepath','filename','url','title','actualmediafilepath','relativepath','filekey') and n.text:
                                            txt = n.text.strip()
                                            if '/' in txt or '\\' in txt or '.' in txt:
                                                source_path = txt
                                                import os as _os
                                                try:
                                                    source_filename = _os.path.basename(txt)
                                                except Exception:
                                                    source_filename = txt
                                    if not display_name:
                                        mref = sc.get('ObjectURef')
                                        for ch in sc:
                                            if ln(ch.tag).lower()=='masterclip' and ch.get('ObjectURef'):
                                                mref = ch.get('ObjectURef')
                                        if mref and mref in objectuid_map:
                                            mc = objectuid_map[mref]
                                            for n in mc.iter():
                                                if ln(n.tag).lower()=='name' and n.text:
                                                    display_name = n.text.strip(); break
                                                if ln(n.tag).lower() in ('pathurl','path','filepath','filename','url','title','actualmediafilepath','relativepath','filekey') and n.text:
                                                    txt = n.text.strip()
                                                    if '/' in txt or '\\' in txt or '.' in txt:
                                                        source_path = txt
                                                        import os as _os
                                                        try:
                                                            source_filename = _os.path.basename(txt)
                                                        except Exception:
                                                            source_filename = txt

                                items.append({'ti_obj':ti_obj,'start':start,'end':end,'duration':duration,'sequence_ref':seqref,'display_name':display_name,'source_path':source_path,'source_filename':source_filename})
        return items

    # recursive flatten: returns instances with absolute raw starts/ends
    def flatten_sequence(seq_elem, parent_offset_raw=0, parent_bound_raw=None, source_sequence_name=None):
        instances = []
        tuids = track_uids_for_sequence(seq_elem)
        for tu in tuids:
            items = track_items_for_trackuid(tu)
            for itm in items:
                start = itm['start']
                end = itm['end']
                duration = itm['duration']
                if start is None:
                    # skip structural entries
                    continue
                if end is None and duration is not None:
                    end = start + duration
                if end is None:
                    # still unknown end — skip
                    continue
                abs_start = parent_offset_raw + start
                abs_end = parent_offset_raw + end
                # if this item references another sequence -> expand recursively using abs_start as offset
                if itm.get('sequence_ref'):
                    seq_uid = itm['sequence_ref']
                    nested_seq = None
                    # sequence refs may be ObjectUIDs or ObjectIDs depending on file
                    if seq_uid in objectuid_map:
                        nested_seq = objectuid_map[seq_uid]
                    elif seq_uid in objectid_map:
                        nested_seq = objectid_map[seq_uid]
                    if nested_seq is not None and ln(nested_seq.tag).lower()=='sequence':
                        # pass the parent bound (abs_end) so child instances are clamped to the parent's allocation
                        # Then recurse to get child clips for the table data
                        for c in nested_seq.iter():
                            if ln(c.tag).lower()=='name' and c.text:
                                nested_seq_name = c.text.strip(); break
                        nested_instances = flatten_sequence(nested_seq, parent_offset_raw=abs_start, parent_bound_raw=abs_end, source_sequence_name=nested_seq_name)
                        instances.extend(nested_instances)
                    else:
                        # unknown or non-sequence ref: skip expanding
                        pass
                else:
                    # If the track item name matches a known Sequence name, expand that sequence
                    name = itm.get('display_name')
                    nested_seq = None
                    if name and name in sequence_name_map:
                        nested_seq = sequence_name_map[name]
                    if nested_seq is not None:
                        nested_instances = flatten_sequence(nested_seq, parent_offset_raw=abs_start, parent_bound_raw=abs_end, source_sequence_name=name)
                        instances.extend(nested_instances)
                    else:
                        # Only include items that have an explicit display name; unnamed items will be filtered later
                        # If a parent bound is set, clamp the child's end and drop if completely outside
                        if parent_bound_raw is not None:
                            if abs_start >= parent_bound_raw:
                                # starts at/after parent bound -> skip
                                continue
                            if abs_end > parent_bound_raw:
                                abs_end = parent_bound_raw
                            if abs_end <= abs_start:
                                continue
                        instances.append({'name':name,'start_raw':abs_start,'end_raw':abs_end, 'source_sequence': source_sequence_name})
        log(f"Flattened {len(instances)} instances from sequence '{source_sequence_name or main_seq_name}'.")
        return instances

    all_instances = flatten_sequence(main, parent_offset_raw=0)
    log(f'Collected {len(all_instances)} raw instances from sequence "{main_seq_name}" before filtering.')

    # convert to seconds aligned and apply 40s cap
    processed = []
    for ins in all_instances:
        s_raw = ins['start_raw']; e_raw = ins['end_raw']
        if frame_rate_value is None:
            log(f"Skipping instance due to missing frame_rate_value: {ins.get('name')}")
        s_sec = seconds_aligned_from_raw(s_raw, frame_rate_value, fps_override)
        e_sec = seconds_aligned_from_raw(e_raw, frame_rate_value, fps_override)
        if s_sec is None or e_sec is None:
            continue
        # drop instances that start at or after cap
        if cap is not None and s_sec >= cap:
            continue
        if cap is not None and e_sec > cap:
            e_sec = cap
        if e_sec <= s_sec:
            # skip degenerate
            continue
        # carry through source info if available
        processed.append({'name':ins.get('name'),'start_sec':s_sec,'end_sec':e_sec,'start_tc':tc_from_seconds(s_sec),'end_tc':tc_from_seconds(e_sec),'source_path':ins.get('source_path'),'source_filename':ins.get('source_filename'), 'source_sequence': ins.get('source_sequence')})

    log(f'{len(processed)} instances remaining after time conversion and capping.')

    # filter out unnamed clips and remove duplicate instances (same start/end TC for same clip)
    filtered = []
    seen_by_name = {}
    for p in processed:
        name = p.get('name')
        # drop completely unnamed
        if not name:
            continue
        # drop <unnamed-...> placeholders
        if isinstance(name, str) and name.startswith('<unnamed-'):
            continue
        key = (p['start_tc'], p['end_tc'])
        s = seen_by_name.setdefault(name, set())
        if key in s:
            # duplicate instance for that clip name -> skip
            continue
        s.add(key)
        filtered.append(p)

    processed = filtered
    log(f'{len(processed)} instances remaining after filtering unnamed/duplicate clips.')

    # group by name
    groups = {}
    for p in processed:
        # Don't include the nested sequence containers in the grouped data for the table
        if p.get('is_nested_container'):
            continue
        key = p['name']
        groups.setdefault(key, []).append(p)

    # decide clip type from filename or source path and build rows
    def detect_clip_type(name, source_filename, source_path):
        # extension-based classification lists
        video_exts = {'.mp4','.mov','.mkv','.avi','.wmv','.mxf','.m2ts','.m2t','.mts','.mpeg','.mpg','.flv','.webm','.3gp','.ogv'}
        audio_exts = {'.wav','.mp3','.aac','.flac','.aiff','.m4a','.ogg','.wma','.alac'}
        image_exts = {'.jpg','.jpeg','.png','.tif','.tiff','.bmp','.gif','.svg','.heic','.webp','.psd','.raw','.exr'}
        # known Premiere/AE graphic/template/project extensions
        graphic_exts = {'.aegraphic','.mogrt','.aep','.aepx'}

        candidates = []
        if source_filename:
            candidates.append(source_filename.lower())
        if source_path:
            candidates.append(source_path.lower())
        if name and isinstance(name, str):
            candidates.append(name.lower())

        # try candidates first (source filename/path/name)
        for c in candidates:
            ext = find_extension_in_string(c)
            if ext:
                if ext in video_exts:
                    return ('Video', f'candidate:{c}')
                if ext in audio_exts:
                    return ('Audio', f'candidate:{c}')
                if ext in image_exts:
                    return ('Image', f'candidate:{c}')
                if ext in graphic_exts:
                    return ('Graphic', f'candidate:{c}')

        # heuristic fallbacks: name contains keywords
        if name and any(k in name.lower() for k in ('graphic','title','caption','overlay','lowerthird','grad')):
            return ('Graphic', 'heuristic:name')

        # if source path contains a graphics/templates folder name
        if source_path and any(k in source_path.lower() for k in ('graphics','templates','motion graphics','mogrt')):
            return ('Graphic', 'heuristic:source_path')

        # final fallback: unknown
        return ('Unknown', None)

    # project-wide search for an extension when local source info is missing
    import re
    def find_extension_in_string(s):
        if not s:
            return None
        import re as _re
        ss = _re.sub(r"\s+"," ", s.lower())
        m = _re.search(r"\.([a-z0-9]{2,20})(?:\b|$)", ss)
        if m:
            return '.' + m.group(1)
        return None

    def find_extension_in_project(name):
        if not name:
            return None
        lname = name.lower()
        # look for any element text that contains the clip name and a dot-extension
        for e in root.iter():
            txt = (e.text or '')
            if not txt:
                continue
            # normalize whitespace/newlines and lower-case for robust matching
            import re as _re
            ltxt = _re.sub(r"\s+"," ", txt.lower())
            if lname in ltxt and '.' in ltxt:
                ext = find_extension_in_string(ltxt)
                if ext:
                    return (ext, ln(e.tag), txt.strip())
        return None

    # build rows: each row per clip name, instances count, instances as "start-end" separated by |, earliest_start, clip_type
    output = io.StringIO()
    csv_writer = csv.writer(output)

    log('Generating "per-instance" CSV.')
    # build flat list of instances with resolved clip type, then sort chronologically
    per_instances = []
    for grp_name, instances in groups.items():
        insts_sorted = sorted(instances, key=lambda x: x['start_sec'])
        # detect type using first instance's source info (best-effort)
        first = insts_sorted[0]
        ctype, dbg_source = detect_clip_type(grp_name, first.get('source_filename'), first.get('source_path'))
        if ctype == 'Unknown':
            ext_info = find_extension_in_project(grp_name)
            if ext_info:
                ext, tag, txt = ext_info
                ext_l = ext.lower()
                if ext_l in {'.aegraphic','.mogrt','.aep','.aepx'}:
                    ctype = 'Graphic'
                elif ext_l in {'.wav','.mp3','.aac','.flac','.aiff','.m4a','.ogg','.wma','.alac'}:
                    ctype = 'Audio'
                elif ext_l in {'.jpg','.jpeg','.png','.tif','.tiff','.bmp','.gif','.svg','.heic','.webp','.psd','.raw','.exr'}:
                    ctype = 'Image'
                elif ext_l in {'.mp4','.mov','.mkv','.avi','.wmv','.mxf','.m2ts','.m2t','.mts','.mpeg','.mpg','.flv','.webm','.3gp','.ogv'}:
                    ctype = 'Video'
        for i in insts_sorted:
            # use rounded HH:MM:SS timecodes already computed in start_tc/end_tc
            per_instances.append({'name':grp_name,'start_sec':i['start_sec'],'end_sec':i['end_sec'],'start_tc':i['start_tc'],'end_tc':i['end_tc'],'clip_type':ctype, 'source_sequence': i.get('source_sequence')})

    # sort all instances chronologically by start_sec
    per_instances_sorted = sorted(per_instances, key=lambda x: x['start_sec'])

    # per-user request: only output HH:MM:SS timecodes, no floating-point seconds columns
    per_instance_headers = ['clip_name','startTC','endTC','clip_type', 'source_sequence']
    per_instance_rows = [[inst['name'], inst['start_tc'], inst['end_tc'], inst['clip_type'], inst.get('source_sequence')] for inst in per_instances_sorted]
    per_instance_data = {'headers': per_instance_headers, 'rows': per_instance_rows}

    log('Generating "grouped" CSV.')
    rows = []
    for name, instances in groups.items():
        insts_sorted = sorted(instances, key=lambda x: x['start_sec'])
        inst_strings = [f"{i['start_tc']}-{i['end_tc']}" for i in insts_sorted]
        earliest = insts_sorted[0]['start_sec']
        # detect type using first instance's source info (best-effort)
        first = insts_sorted[0]
        ctype, dbg_source = detect_clip_type(name, first.get('source_filename'), first.get('source_path'))
        # if still unknown, try project-wide search for an extension and record its element
        if ctype == 'Unknown':
            ext_info = find_extension_in_project(name)
            if ext_info:
                ext, tag, txt = ext_info
                ext_l = ext.lower()
                if ext_l in {'.aegraphic','.mogrt','.aep','.aepx'}:
                    ctype = 'Graphic'
                elif ext_l in {'.wav','.mp3','.aac','.flac','.aiff','.m4a','.ogg','.wma','.alac'}:
                    ctype = 'Audio'
                elif ext_l in {'.jpg','.jpeg','.png','.tif','.tiff','.bmp','.gif','.svg','.heic','.webp','.psd','.raw','.exr'}:
                    ctype = 'Image'
                elif ext_l in {'.mp4','.mov','.mkv','.avi','.wmv','.mxf','.m2ts','.m2t','.mts','.mpeg','.mpg','.flv','.webm','.3gp','.ogv'}:
                    ctype = 'Video'
                # update debug source to point to project element used
                dbg_source = f'project_element:{tag}:{txt[:180]}'
                if DEBUG:
                    print(f"[DEBUG] Clip '{name}' classified as {ctype} from extension {ext} found in <{tag}>: {txt[:240]}")
        else:
            if DEBUG and dbg_source:
                print(f"[DEBUG] Clip '{name}' classified as {ctype} from {dbg_source}")

        rows.append({'name':name,'instances_count':len(insts_sorted),'instances_str':' | '.join(inst_strings),'earliest_start':earliest,'clip_type':ctype})

    # sort rows chronologically by earliest instance
    rows_sorted = sorted(rows, key=lambda x: x['earliest_start'])

    grouped_headers = ['clip_name','instances_count','instances(start-end pipe-separated)','clip_type']
    grouped_rows = [[r['name'], r['instances_count'], r['instances_str'], r.get('clip_type','Unknown')] for r in rows_sorted]
    grouped_data = {'headers': grouped_headers, 'rows': grouped_rows}

    if debug_fh:
        try:
            debug_fh.close()
        except Exception:
            pass
    return grouped_data, per_instance_data

def list_named_sequences_from_content(xml_content):
    """Parses XML content and returns a list of named sequences."""
    root = ET.fromstring(xml_content)
    seqs = []
    for e in root.iter():
        if ln(e.tag).lower()=='sequence':
            for c in e.iter():
                if ln(c.tag).lower()=='name' and c.text and c.text.strip():
                    seqs.append(c.text.strip())
                    break
    return seqs

def generate_timeline_csv_string(data_dict):
    """Helper to convert the data dictionary to a CSV string for file download."""
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
    parser.add_argument('--cap',type=float,default=40.0,help='sequence length cap in seconds (default 40.0)')
    parser.add_argument('--debug',action='store_true',help='enable debug audit prints')
    parser.add_argument('--list-sequences',action='store_true',help='list named sequences and exit')
    parser.add_argument('--debug-log',required=False,help='path to write debug log (optional)')
    parser.add_argument('--out','-o',required=False,help='output CSV file path (optional). If omitted a descriptive name project__sequence_timeline.csv will be used in the input file directory')
    parser.add_argument('--per-instance',action='store_true',help='write one CSV row per clip instance instead of grouping by clip name')
    args = parser.parse_args()

    # choose input
    # For privacy, do not hardcode any project file path. Require --input or exit.
    if not args.input:
        print('Error: --input is required. Please provide the path to an unzipped .prproj XML file.'); sys.exit(2)
    
    path = args.input
    xml_content_main = load_project_file(path)

    # list sequences if requested
    if args.list_sequences:
        seqs = list_named_sequences_from_content(xml_content_main)
        print('Found sequences:')
        for s in seqs:
            print(' -',s)
        sys.exit(0)

    main_seq_name = args.sequence
    # choose main sequence: provided name or prompt user to pick from detected sequences
    if not main_seq_name:
        seqs = list_named_sequences_from_content(xml_content_main)
        if not seqs:
            print('No named sequences found in project; aborting'); sys.exit(1)
        # If running non-interactively (no TTY), default to the first named sequence
        try:
            interactive = sys.stdin.isatty()
        except Exception:
            interactive = False
        if not interactive:
            main_seq_name = seqs[0]
            if args.debug:
                print(f"No sequence provided and not interactive; defaulting to first named sequence: {main_seq_name}")
        else:
            # prompt the user to choose
            print('Found named sequences:')
            for idx, s in enumerate(seqs, start=1):
                print(f" {idx}) {s}")
            while True:
                choice = input(f"Enter sequence number or full name to process (default 1), or Q to quit: ").strip()
                if not choice:
                    main_seq_name = seqs[0]
                    break
                if choice.lower() == 'q':
                    print('Quitting.'); sys.exit(0)
                # numeric choice
                if choice.isdigit():
                    n = int(choice)
                    if 1 <= n <= len(seqs):
                        main_seq_name = seqs[n-1]
                        break
                # exact case-insensitive match
                matches = [s for s in seqs if s.lower() == choice.lower()]
                if len(matches) == 1:
                    main_seq_name = matches[0]
                    break
                # single partial match
                matches = [s for s in seqs if choice.lower() in s.lower()]
                if len(matches) == 1:
                    main_seq_name = matches[0]
                    break
                if len(matches) > 1:
                    print('Multiple matches:', ', '.join(matches[:10]))
                    continue
                print('Invalid choice, try again.')

    def load_project_file(path):
        """Reads a .prproj (gzipped) or unzipped XML file and returns its content as a string."""
        with open(path, "rb") as f:
            data = f.read()
        try:
            # Try to decompress, assuming it's a gzipped .prproj
            xml_data = gzip.decompress(data)
        except (gzip.BadGzipFile, OSError):
            # If it fails, it's likely already unzipped XML
            xml_data = data
        return xml_data.decode('utf-8', errors='replace')

    grouped_data, per_instance_data = generate_timeline_data(
        xml_content=xml_content_main,
        main_seq_name=main_seq_name,
        # If fps is not provided, default to 23.976
        fps_override=args.fps if args.fps is not None else 23.976,
        cap=args.cap,
        debug=args.debug, 
        debug_log_path=args.debug_log)
    
    final_data = per_instance_data if args.per_instance else grouped_data

    rows = []

    # determine output path: use --out if provided, otherwise construct descriptive name from input file and sequence
    if args.out:
        out_path = args.out
    else:
        input_base = os.path.splitext(os.path.basename(path))[0]
        # sanitize sequence name for filename
        def sanitize(s):
            if not s: return 'sequence'
            safe = ''.join(ch if (ch.isalnum() or ch in '-._') else '_' for ch in s)
            return safe[:120]
        seq_safe = sanitize(main_seq_name)
        out_filename = f"{input_base}__{seq_safe}_timeline.csv"
        # place output file in the same directory as the input file
        input_dir = os.path.dirname(os.path.abspath(path)) or os.getcwd()
        out_path = os.path.join(input_dir, out_filename)

    with open(out_path, 'w', encoding='utf-8') as f:
        f.write(generate_timeline_csv_string(final_data))

    print(f'Wrote CSV to {out_path}')

