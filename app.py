from flask import Flask, render_template, request, make_response, flash, redirect, url_for
import os
import uuid
import gzip
import io
import csv
from contextlib import redirect_stdout
from collections import defaultdict
from werkzeug.utils import secure_filename

# Import the refactored functions from your script
from export_timeline_csv import generate_timeline_data, list_named_sequences_from_content
from components.table_processor import process_data_for_tables
from components.visualizer_processor import process_data_for_visualizer

app = Flask(__name__)
app.secret_key = 'supersecretkey' # Needed for flashing messages

UPLOAD_FOLDER = 'uploads'
app.config['UPLOAD_FOLDER'] = UPLOAD_FOLDER

# Create upload folder if it doesn't exist. This needs to be at the top level.
if not os.path.exists(UPLOAD_FOLDER):
    os.makedirs(UPLOAD_FOLDER)

@app.route('/', methods=['GET'])
def index():
    """Render the main upload page."""
    return render_template('index.html')

@app.route('/upload', methods=['POST'])
def upload_file():
    """Handle file upload and processing."""
    # If the form is submitted with a temp_file_id, it's the second step (generation).
    if 'temp_file_id' in request.form:
        temp_file_id = request.form['temp_file_id']
        main_seq_name = request.form.get('sequence')

        temp_file_path = os.path.join(app.config['UPLOAD_FOLDER'], temp_file_id)

        if not os.path.exists(temp_file_path) or not main_seq_name:
            flash('Temporary file not found or sequence not selected. Please upload again.')
            return redirect(url_for('index'))

        with open(temp_file_path, 'rb') as f:
            file_bytes = f.read()

        # The rest of the logic is similar to before, but reads from the saved file.
        try:
            xml_content = gzip.decompress(file_bytes).decode('utf-8', errors='replace')
        except (gzip.BadGzipFile, OSError):
            xml_content = file_bytes.decode('utf-8', errors='replace')

        try:
            log_stream = io.StringIO()
            with redirect_stdout(log_stream):
                # Step 1: Generate raw data from the project file.
                # We only need to run the main generator once.
                grouped_data_raw, per_instance_data_raw = generate_timeline_data(
                    xml_content=xml_content,
                    main_seq_name=main_seq_name,
                    debug=True # Enable debug logging
                )

            debug_logs = log_stream.getvalue().splitlines()

            os.remove(temp_file_path) # Clean up the temporary file

            # Step 2: Process raw data for the tables.
            cleaned_grouped_headers, grouped_data, per_instance_data_for_table = process_data_for_tables(
                grouped_data_raw, per_instance_data_raw
            )

            # Step 3: Process raw data for the visualizer.
            timeline_items, total_non_audio_tracks, timeline_duration = process_data_for_visualizer(
                per_instance_data_raw, grouped_data_raw
            )

            # Step 4: Prepare CSV content for download buttons
            def to_csv_string(data_dict):
                output = io.StringIO()
                writer = csv.writer(output)
                writer.writerow(data_dict['headers'])
                writer.writerows(data_dict['rows'])
                return output.getvalue()

            grouped_csv_string = to_csv_string(grouped_data_raw)
            per_instance_csv_string = to_csv_string(per_instance_data_raw)

            return render_template('results.html', 
                                   grouped_csv=grouped_csv_string,
                                   grouped_headers=cleaned_grouped_headers, 
                                   grouped_data=grouped_data,
                                   per_instance_csv=per_instance_csv_string,
                                   per_instance_headers=per_instance_data_raw['headers'],
                                   per_instance_data=per_instance_data_for_table,
                                   timeline_items=timeline_items,
                                   total_non_audio_tracks=total_non_audio_tracks,
                                   timeline_duration=timeline_duration,
                                   debug_logs=debug_logs)

        except Exception as e:
            if os.path.exists(temp_file_path):
                os.remove(temp_file_path)
            flash(f'An error occurred during CSV generation: {e}')
            return redirect(url_for('index'))


    # This is the first step: file upload and analysis.
    if 'file' not in request.files:
        flash('No file part')
        return redirect(request.url)
    
    file = request.files['file']
    if file.filename == '':
        flash('No selected file')
        return redirect(request.url)
    original_filename = secure_filename(file.filename)

    if file:
        # Generate a unique ID for the temporary file
        temp_file_id = str(uuid.uuid4())
        temp_file_path = os.path.join(app.config['UPLOAD_FOLDER'], temp_file_id)
        
        # Save the file to the uploads directory
        file.save(temp_file_path)

        with open(temp_file_path, 'rb') as f:
            file_bytes = f.read()

        try:
            # Try to decompress, assuming it's a gzipped .prproj file
            xml_content = gzip.decompress(file_bytes).decode('utf-8', errors='replace')
        except (gzip.BadGzipFile, OSError):
            # If decompression fails, it's likely already unzipped XML
            xml_content = file_bytes.decode('utf-8', errors='replace')
        
        try:
            # Step 1: Get the list of sequences to populate the dropdown
            sequences = list_named_sequences_from_content(xml_content)
            if not sequences:
                flash('No named sequences found in the project file.')
                return render_template('index.html')

            # If this is the first time (before user selects a sequence)
            # just show the page with the sequence list.
            return render_template('index.html', sequences=sequences, temp_file_id=temp_file_id, filename=original_filename)

        except Exception as e:
            # Catch errors during parsing or processing
            flash(f'An error occurred: {e}')
            return render_template('index.html')

    return redirect(url_for('index'))


if __name__ == '__main__':
    # Create a 'templates' directory for the HTML file if it doesn't exist
    if not os.path.exists('components'):
        os.makedirs('components')
        with open('components/__init__.py', 'w') as f:
            pass # Create empty __init__.py
    if not os.path.exists(UPLOAD_FOLDER):
        os.makedirs(UPLOAD_FOLDER)

    if not os.path.exists('templates'):
        os.makedirs('templates')
    
    # Check if index.html exists, if not, tell the user to create it.
    if not os.path.exists('templates/index.html'):
        print("Please create a 'templates/index.html' file for the web interface.")
    

    app.run(debug=True)
