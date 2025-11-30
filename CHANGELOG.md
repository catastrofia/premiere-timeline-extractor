# Changelog

All notable changes to this project will be documented in this file. See [standard-version](https://github.com/conventional-changelog/standard-version) for commit guidelines.

## [1.2.0] - 2025-11-30

### Fixed
- Fixed JavaScript syntax errors in templates/results.html: wrapped Jinja2 data in template literals, JSON.parse, Number; expanded object shorthand.
- Fixed Pylance warning in export_timeline_csv.py: moved load_project_file to module level.

### Added/Improved
- Accurate timecode calculations using detected FPS from project FrameRate (fps_map, fallback 23.976).
- UI display of detected FPS, sequence name, formatted duration.
- Grouped table: merge overlapping intervals for timecodes.
- source_sequence tracking/column in per-instance data/tables.
- Enhanced deduplication by (name, parent_sequence, start_tc, end_tc).
- Frontend timeline: nested containers/children synthesis/toggle.
- Sequence switching via temp_file_id.
- Robust clip type detection: project-wide extension search.
- Added "Hide Graphics" option to the table.
## 1.1.0 (2025-11-23)


### Features

* Add app versioning and UI layout ([2212ac7](https://github.com/catastrofia/premiere-timeline-extractor/commit/2212ac71abeb0807f419b340afacfd3a91e667fa))

## [1.0.0] - 2025-11-18
- Initial release
