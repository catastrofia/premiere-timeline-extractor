import csv
import io
from components.helpers import tc_to_seconds, tc_from_seconds
from collections import defaultdict

def process_data_for_tables(grouped_data_raw, per_instance_data_raw):
    """
    Takes raw data from the CSV generator and prepares it for the frontend tables.
    This includes adding labels for nested clips and reordering columns.
    """
    print("[DEBUG] Starting: process_data_for_tables")
    # --- Grouped Data Processing ---
    grouped_headers_orig, grouped_rows_list = grouped_data_raw['headers'], grouped_data_raw['rows']
    
    # Manually set headers and reorder data for display
    cleaned_grouped_headers = ["Clip name", "Clip type", "Instances count", "Instances Start and End (Separated by \"|\")"]
    
    # --- Create a map of clip names to their nested sources ---
    per_instance_headers_orig, raw_per_instance_data_for_grouping = per_instance_data_raw['headers'], per_instance_data_raw['rows']
    clip_nest_sources = defaultdict(set)
    for row in raw_per_instance_data_for_grouping:
        clip_name = row[0]
        source_seq = row[4] if len(row) > 4 and row[4] else None
        if source_seq:
            clip_nest_sources[clip_name].add(source_seq)

    grouped_data = []
    for row in grouped_rows_list:
        # Original order: name, count, instances, type
        clip_name = row[0]
        display_name = clip_name
        if clip_name in clip_nest_sources:
            nest_names = ", ".join(f"<b>{name}</b>" for name in sorted(list(clip_nest_sources[clip_name])))
            display_name = f"{clip_name} (From nested sequence: {nest_names})"

        # Enforce 1-second minimum duration for display in grouped view instances
        instances_str = row[2]
        new_instances = []
        for part in instances_str.split(' | '):
            start_tc, end_tc = part.split('-')
            if tc_to_seconds(end_tc) - tc_to_seconds(start_tc) < 1 and tc_to_seconds(start_tc) < 359990: # Avoid huge timecodes
                end_tc = tc_from_seconds(tc_to_seconds(start_tc) + 1)
            new_instances.append(f"{start_tc}-{end_tc}")
        
        reordered_row = [display_name, row[3], row[1], " | ".join(new_instances)]
        grouped_data.append(reordered_row)

    # --- Per-Instance Data Processing ---
    per_instance_data_for_table = []
    for row in raw_per_instance_data_for_grouping:
        new_row = list(row)
        if len(row) > 4 and row[4]:
            new_row[0] = f"{row[0]} (From nested sequence: <b>{row[4]}</b>)"
        
        # Enforce 1-second minimum duration for display
        start_tc, end_tc = new_row[1], new_row[2]
        if tc_to_seconds(end_tc) - tc_to_seconds(start_tc) < 1 and tc_to_seconds(start_tc) < 359990:
            start_s = tc_to_seconds(start_tc)
            new_row[2] = tc_from_seconds(start_s + 1)

        per_instance_data_for_table.append(new_row)
    
    print("[DEBUG] Finished: process_data_for_tables")
    return cleaned_grouped_headers, grouped_data, per_instance_data_for_table