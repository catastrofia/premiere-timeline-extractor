from .helpers import tc_from_seconds, tc_to_seconds
from collections import defaultdict

def process_data_for_visualizer(per_instance_data_raw, grouped_data_raw):
    """
    Takes raw data and prepares it for the timeline visualizer.
    - Synthesizes nested sequences into single blocks.
    - Calculates track placement for all clips.
    - Determines the total duration of the sequence.
    - Returns data ready for rendering.
    """
    print("[DEBUG] Starting: process_data_for_visualizer")
    per_instance_headers, raw_per_instance_data = per_instance_data_raw['headers'], per_instance_data_raw['rows']
    grouped_headers, grouped_rows_list = grouped_data_raw['headers'], grouped_data_raw['rows']

    # --- Create a map of original clip_name -> instance_count for the timeline tooltip ---
    instance_counts = {row[0]: row[1] for row in grouped_rows_list}

    # --- Synthesize nested blocks for the visualizer ---
    # Start with all individual clips.
    visualizer_items_raw = list(raw_per_instance_data)
    nested_sequence_names = {row[4] for row in raw_per_instance_data if len(row) > 4 and row[4]}

    # For each unique nested sequence, find its boundaries and add it as a single block
    for nest_name in nested_sequence_names:
        child_clips = [row for row in raw_per_instance_data if len(row) > 4 and row[4] == nest_name]
        if not child_clips: continue

        min_start_s = min(tc_to_seconds(row[1]) for row in child_clips if row[1])
        max_end_s = max(tc_to_seconds(row[2]) for row in child_clips if row[2])
        
        # This is a synthesized container block for the visualizer
        visualizer_items_raw.append([
            nest_name, 
            tc_from_seconds(min_start_s), 
            tc_from_seconds(max_end_s),
            'Nested sequence', # This type is key for the frontend
            None # It has no parent sequence itself
        ])

    # --- Calculate timeline duration and prepare items for rendering ---
    max_end_time = 0
    for row in visualizer_items_raw:
        end_s = tc_to_seconds(row[2]) if row[2] else 0
        if end_s > max_end_time:
            max_end_time = end_s
    
    # Set duration to the exact end time plus a small padding for visuals
    timeline_duration = max(10, max_end_time + 1)

    # --- Hierarchical Track Calculation ---
    timeline_items = []
    
    # 1. Separate items into top-level and nested children
    top_level_items_raw = [row for row in visualizer_items_raw if (len(row) <= 4 or not row[4])]
    nested_child_items_raw = [row for row in visualizer_items_raw if len(row) > 4 and row[4]]

    # 2. Calculate tracks for top-level items (regular clips and nested containers)
    top_level_tracks = {} # To store the base track for each container
    non_audio_lanes = []
    audio_lanes = []

    for row in top_level_items_raw:
        start_s = tc_to_seconds(row[1]) if row[1] else 0
        end_s = tc_to_seconds(row[2]) if row[2] else start_s + 1

        is_audio = row[3] == 'Audio'
        lanes = audio_lanes if is_audio else non_audio_lanes
        
        track_index = -1
        for i in range(len(lanes)):
            if lanes[i] <= start_s:
                track_index = i
                lanes[i] = end_s
                break
        if track_index == -1:
            track_index = len(lanes)
            lanes.append(end_s)
        
        # Store the calculated track for this top-level item
        top_level_tracks[row[0]] = track_index

        timeline_items.append({ 'row': row, 'track': track_index, 'is_audio': is_audio })

    # 3. Group nested children and calculate their tracks relative to their parent
    children_by_nest = defaultdict(list)
    for row in nested_child_items_raw:
        children_by_nest[row[4]].append(row)

    for nest_name, children in children_by_nest.items():
        base_track = top_level_tracks.get(nest_name, 0)
        is_audio = any(child[3] == 'Audio' for child in children) # Assume mixed nests are video-side

        child_lanes = []
        for row in children:
            start_s = tc_to_seconds(row[1]) if row[1] else 0
            end_s = tc_to_seconds(row[2]) if row[2] else start_s + 1

            internal_track_index = -1
            for i in range(len(child_lanes)):
                if child_lanes[i] <= start_s:
                    internal_track_index = i
                    child_lanes[i] = end_s
                    break
            if internal_track_index == -1:
                internal_track_index = len(child_lanes)
                child_lanes.append(end_s)
            
            # The final track is the container's base track + the internal track
            timeline_items.append({ 'row': row, 'track': base_track + internal_track_index, 'is_audio': is_audio })

    # 4. Final processing for rendering
    final_timeline_items = []
    for item_data in timeline_items:
        row = item_data['row']
        track = item_data['track']
        is_audio = item_data['is_audio']

        start_s = tc_to_seconds(row[1]) if row[1] else 0
        end_s = tc_to_seconds(row[2]) if row[2] else 0
        end_tc = row[2]

        if end_s - start_s < 1 and start_s < 359990:
            end_s = start_s + 1
            end_tc = tc_from_seconds(end_s)

        final_timeline_items.append({
            'name': row[0],
            'start_tc': row[1],
            'end_tc': end_tc,
            'type': row[3],
            'start_percent': (start_s / timeline_duration) * 100,
            'width_percent': ((end_s - start_s) / timeline_duration) * 100,
            'track': track,
            'is_audio': is_audio,
            'instance_count': instance_counts.get(row[0], 1),
            'source_sequence': row[4] if len(row) > 4 else None
        })

    total_non_audio_tracks = len(non_audio_lanes)

    print(f"[DEBUG] Finished: process_data_for_visualizer. Found {len(final_timeline_items)} items for a duration of {timeline_duration}s.")
    return final_timeline_items, total_non_audio_tracks, timeline_duration