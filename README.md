# Premiere Timeline Extractor

A web-based tool to extract all the clips with timecodes from a selected timeline from Adobe Premiere Pro project files (`.prproj`).

## Features

- **Web Interface**: Upload `.prproj` files and select sequences to analyze
- **CLI Support**: Command-line interface for direct conversion to CSV
- **Timeline Visualization - BETA**: Interactive visual representation of your timeline
- **Tabular Data**: Sortable tables with clip information
- **Source Recognition**: Automatic detection of selected stock footage providers (Imago, Colourbox, Artlist), their IDs and if given, the clip title.
- **Accurate Timecodes**: FPS-aware timecode calculations and rounded to the nearest second.

## Clip information
- **Clip name**: The name of the clip
- **Clip type**: The media type of the clip (e.g., video, audio, image)
- **Instances count**: How many times a same clip appears in the sequence
- **Instances Start and End**: The timecodes with in and out timestamps for every instance (each instance separated by "|")
- **Source**: The source of the clip for supported stock providers (see below)
- **Media ID**: For supported sources, the ID of the media provider
- **Title**: For supported sources, the title of the media


## Supported Stock Footage Providers

- **Imago**: The source recognition feature can detect Imago clips and extract their IDs
- **Colourbox**: The feature can identify Colourbox clips and retrieve their IDs
- **Artlist**: The source recognition feature can recognize Artlist clips and extract their IDs and titles.

## Quick Start

### Prerequisites

- Python 3.10+

### Installation

```bash
# Clone the repository
git clone https://github.com/catastrofia/premiere-timeline-extractor.git
cd premiere-timeline-extractor

# Install dependencies
pip install -r requirements.txt
```

### Usage

#### Web Interface

```bash
python app.py
```

Then open http://127.0.0.1:5000 in your browser.

#### Command Line

```bash
python export_timeline_csv.py <path/to/project.prproj>
```

## Best Practices for premiere projects
- Make sure to keep a clean timeline: remove unused clips and tracks. (Recommended to make a copy of your sequence and then clean the copy)
- For better source and title recognition, use the following naming convention for the clips adding descriptive titles at the end of clip names following an "_" (e.g.,"originalClipName" --rename--> "OriginalClipName_DescriptiveTitle")

## Bugs and Suggestions

If you encounter any bugs or have any feature requests or suggestions, please create a new issue on GitHub here https://github.com/catastrofia/premiere-timeline-extractor/issues/new/choose

## Testing

```bash
# Run all tests
pytest -v

# Run with coverage
pytest --cov=components --cov-report=html
```

## License

MIT License - see [LICENSE](LICENSE) for details.
