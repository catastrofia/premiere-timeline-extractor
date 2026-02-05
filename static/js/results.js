/**
 * Premiere Timeline Extractor - Results Page JavaScript
 * Handles timeline visualization, table interactions, and CSV export
 */

// --- Timeline Data & State ---
let zoomLevel = 1.0; // 1.0 = 100%
let timelineDuration = 0;
let timelineItems = [];
let groupedCsv = '';
let perInstanceCsv = '';

// Initialize data from backend (backendData is set in the HTML before this script loads)
function initializeData() {
    if (typeof backendData !== 'undefined') {
        groupedCsv = backendData.groupedCsv;
        perInstanceCsv = backendData.perInstanceCsv;
        timelineItems = backendData.timelineItems;
        timelineDuration = backendData.timelineDuration;
        
        console.log("Backend data received:", {
            groupedCsv: groupedCsv,
            perInstanceCsv: perInstanceCsv,
            timelineItems: timelineItems,
            timelineDuration: timelineDuration
        });
    } else {
        console.error("backendData is not defined - data initialization failed");
    }
}

// --- Timecode Conversion Utilities ---

// Convert timecode (HH:MM:SS) to seconds
function tcToSeconds(tc) {
    if (!tc) return 0;
    const parts = tc.split(':').map(Number);
    if (parts.length !== 3) return 0;
    return parts[0] * 3600 + parts[1] * 60 + parts[2];
}

// Convert seconds to timecode (HH:MM:SS)
function tc_from_seconds(s) {
    const hh = String(Math.floor(s / 3600)).padStart(2, '0');
    const mm = String(Math.floor((s % 3600) / 60)).padStart(2, '0');
    const ss = String(Math.round(s % 60)).padStart(2, '0');
    return `${hh}:${mm}:${ss}`;
}

// --- Nested Sequence Processing ---

// Process nested sequences
function processNestedSequences() {
    const nestedSequenceNames = new Set();
    
    // Find all nested sequence names
    timelineItems.forEach(item => {
        // A clip is a child of a nest if it has a source_sequence
        if (item.source_sequence && item.type !== 'Nested sequence') {
            nestedSequenceNames.add(item.source_sequence);
        }
    });
    
    // Mark which items are containers and which are children
    return timelineItems.map(item => {
        if (item.type === 'Nested sequence') {
            return { ...item, is_nested_container: true };
        }
        if (item.source_sequence) {
            return { ...item, is_nested_child: true };
        }
        return item;
    });
}

// --- View Toggling Logic ---
function setupViewToggle() {
    const viewToggle = document.getElementById('view-toggle');
    const groupedTable = document.getElementById('grouped-table');
    const perInstanceTable = document.getElementById('per-instance-table');
    
    viewToggle.addEventListener('change', () => {
        if (viewToggle.checked) {
            console.log("Switching to 'Per Instance' table view.");
            groupedTable.classList.add('hidden');
            perInstanceTable.classList.remove('hidden');
            // Recalculate height for the parent collapsible container
            refreshCollapsibleHeight(perInstanceTable);
        } else {
            groupedTable.classList.remove('hidden');
            perInstanceTable.classList.add('hidden');
            refreshCollapsibleHeight(groupedTable);
        }
    });
}

// --- Download CSV Logic ---
function setupDownloadButton() {
    const downloadButton = document.getElementById('download-csv');
    const viewToggle = document.getElementById('view-toggle');
    
    downloadButton.addEventListener('click', () => {
        const isPerInstance = viewToggle.checked;
        console.log(`Preparing to download ${isPerInstance ? 'per-instance' : 'grouped'} CSV.`);
        const csvContent = isPerInstance ? perInstanceCsv : groupedCsv;
        const filename = isPerInstance ? 'timeline_per-instance.csv' : 'timeline_grouped.csv';
        
        const blob = new Blob([csvContent], { type: 'text/csv;charset=utf-8;' });
        const link = document.createElement('a');
        const url = URL.createObjectURL(blob);
        link.setAttribute('href', url);
        link.setAttribute('download', filename);
        link.style.visibility = 'hidden';
        document.body.appendChild(link);
        link.click();
        document.body.removeChild(link);
    });
}

// --- Table Interaction Logic ---
function makeTableInteractive(tableId) {
    const table = document.querySelector(`#${tableId} .data-table`);
    const headers = table.querySelectorAll('th');
    const tbody = table.querySelector('tbody');
    
    // Skip resizer for tables with no headers (or if something goes wrong)
    if (headers.length === 0) {
        return;
    }
    
    // Add resizers to headers
    headers.forEach(header => {
        const resizer = document.createElement('div');
        resizer.className = 'resizer';
        header.appendChild(resizer);
        makeResizable(header, resizer);
    });
    
    // 1. Column Sorting
    headers.forEach((header) => {
        // Don't sort if the click is on the resizer
        header.addEventListener('click', (e) => {
            if (e.target.classList.contains('resizer')) return;
            
            const index = Array.from(header.parentNode.children).indexOf(header);
            const rows = Array.from(tbody.querySelectorAll('tr'));
            const isAsc = !header.classList.contains('sort-asc');
            
            // Remove sorting classes from all headers
            headers.forEach(h => h.classList.remove('sort-asc', 'sort-desc'));
            header.classList.toggle('sort-asc', isAsc);
            header.classList.toggle('sort-desc', !isAsc);
            
            // Sort the rows
            rows.sort((a, b) => {
                const aText = a.children[index].textContent.trim();
                const bText = b.children[index].textContent.trim();
                
                // Basic numeric or string comparison
                const aVal = isNaN(aText) || aText === '' ? aText : parseFloat(aText);
                const bVal = isNaN(bText) || bText === '' ? bText : parseFloat(bText);
                
                if (aVal < bVal) return isAsc ? -1 : 1;
                if (aVal > bVal) return isAsc ? 1 : -1;
                return 0;
            });
            
            // Re-append sorted rows
            rows.forEach(row => tbody.appendChild(row));
        });
    });
    
    // 2. Column Reordering
    const headerRow = table.querySelector('thead tr');
    new Sortable(headerRow, {
        animation: 150,
        onEnd: (evt) => {
            const oldIndex = evt.oldIndex;
            const newIndex = evt.newIndex;
            const rows = Array.from(tbody.querySelectorAll('tr'));
            rows.forEach(row => {
                const cell = row.children[oldIndex];
                row.insertBefore(cell, row.children[newIndex + (oldIndex < newIndex ? 1 : 0)]);
            });
        }
    });
}

// Make table columns resizable
function makeResizable(header, resizer) {
    const table = header.closest('.data-table');
    let x = 0;
    let w = 0;
    
    const mouseDownHandler = function (e) {
        x = e.clientX;
        w = header.offsetWidth;
        document.addEventListener('mousemove', mouseMoveHandler);
        document.addEventListener('mouseup', mouseUpHandler);
        table.style.tableLayout = 'fixed'; // Ensure fixed layout during resize
        e.preventDefault(); // Prevent text selection
    };
    
    const mouseMoveHandler = function (e) {
        const dx = e.clientX - x;
        header.style.width = `${w + dx}px`;
        header.style.minWidth = `${w + dx}px`; // Persist width
    };
    
    const mouseUpHandler = function () {
        document.removeEventListener('mousemove', mouseMoveHandler);
        document.removeEventListener('mouseup', mouseUpHandler);
    };
    
    resizer.addEventListener('mousedown', mouseDownHandler);
}

// --- Advanced Table Filtering Logic ---
function setupTableFilters() {
    const searchInput = document.getElementById('search-input');
    const typeFilter = document.getElementById('type-filter');
    const audioFilters = document.querySelectorAll('input[name="audio-filter"]');
    const hideGraphicsCheckbox = document.getElementById('hide-graphics');
    
    // Populate type filter dropdown
    const clipTypes = new Set();
    timelineItems.forEach(item => {
        if (item.type !== 'Nested sequence') {
            clipTypes.add(item.type);
        }
    });
    
    clipTypes.forEach(type => {
        const option = document.createElement('option');
        option.value = type;
        option.textContent = type;
        typeFilter.appendChild(option);
    });
    
    // Apply filters function
    function applyFilters() {
        const searchText = searchInput.value.toLowerCase();
        const selectedType = typeFilter.value;
        const audioFilterValue = document.querySelector('input[name="audio-filter"]:checked').value;
        const hideGraphics = hideGraphicsCheckbox.checked;
        
        const tables = [
            document.getElementById('grouped-table'), 
            document.getElementById('per-instance-table')
        ];
        
        tables.forEach(table => {
            const rows = table.querySelectorAll('tbody tr');
            rows.forEach(row => {
                const rowText = row.textContent.toLowerCase();
                const rowType = row.dataset.type;
                
                const searchMatch = rowText.includes(searchText);
                const typeMatch = !selectedType || rowType === selectedType;
                
                let audioMatch = true;
                if (audioFilterValue === 'audio-only') {
                    audioMatch = rowType === 'Audio';
                } else if (audioFilterValue === 'video-only') {
                    audioMatch = rowType !== 'Audio';
                }
                
                const graphicsMatch = !hideGraphics || rowType !== 'Graphic';
                
                row.style.display = (searchMatch && typeMatch && audioMatch && graphicsMatch) ? '' : 'none';
            });
        });
    }
    
    // Add event listeners
    searchInput.addEventListener('keyup', applyFilters);
    typeFilter.addEventListener('change', applyFilters);
    audioFilters.forEach(radio => radio.addEventListener('change', applyFilters));
    hideGraphicsCheckbox.addEventListener('change', applyFilters);
}

// --- Collapsible Sections Logic ---
function setupCollapsibleSections() {
    document.querySelectorAll('.collapsible-header').forEach(button => {
        button.addEventListener('click', function() {
            this.classList.toggle('active');
            let content = this.nextElementSibling;
            content.classList.toggle('active');
            
            if (content.style.maxHeight) {
                content.style.maxHeight = null;
            } else {
                content.style.maxHeight = (content.scrollHeight + 50) + "px";
            }
        });
    });
}

// Helper to refresh collapsible section heights
function refreshCollapsibleHeight(element) {
    const content = element.closest('.collapsible-content');
    if (content && content.classList.contains('active')) {
        content.style.maxHeight = (content.scrollHeight + 50) + "px";
    }
}

// --- Timeline Visualization Logic ---
function setupTimelineVisualization() {
    const timelineWrapper = document.querySelector('.timeline-wrapper');
    const ruler = document.querySelector('.timeline-ruler');
    const videoSection = document.getElementById('video-section');
    const audioSection = document.getElementById('audio-section');
    const zoomInButton = document.getElementById('zoom-in');
    const zoomOutButton = document.getElementById('zoom-out');
    const timelineContainer = document.querySelector('.timeline-container');
    const separator = document.querySelector('.timeline-separator');
    const showNestedClipsToggle = document.getElementById('show-nested-clips');
    
    // Process nested sequences
    const synthesizedTimelineItems = processNestedSequences();
    
    // Render timeline function
    function renderTimeline() {
        console.log(`Rendering timeline with zoomLevel: ${zoomLevel}`);
        
        // Clear previous render
        ruler.innerHTML = '';
        videoSection.innerHTML = '';
        audioSection.innerHTML = '';
        
        // Set the total width of the timeline based on zoom
        const totalWidthPercent = 100 * zoomLevel;
        timelineWrapper.style.width = `${totalWidthPercent}%`;
        
        // Render Ruler
        const visibleDuration = timelineDuration / zoomLevel;
        const step = Math.max(1, Math.round(visibleDuration / 8 / 5) * 5); // Aim for ~8 ruler marks
        for (let i = 0; i <= timelineDuration; i += step) {
            const percent = (i / timelineDuration) * 100;
            ruler.innerHTML += `<div class="ruler-mark" style="left: ${percent}%;"></div>`;
            ruler.innerHTML += `<div class="ruler-label" style="left: ${percent}%;">~${Math.round(i)}s</div>`;
        }
        
        const showNestedClips = showNestedClipsToggle.checked;
        
        // Filter items based on the toggle
        const itemsToRender = synthesizedTimelineItems.filter(item => {
            if (showNestedClips) {
                // If showing nested, hide the containers
                return !item.is_nested_container;
            } else {
                // If not showing nested, hide the children
                return !item.is_nested_child;
            }
        });
        
        // Render Timeline Items
        const nonAudioItems = itemsToRender.filter(item => !item.is_audio);
        const audioItems = itemsToRender.filter(item => item.is_audio);
        
        // Calculate the required number of tracks BEFORE positioning the items
        const maxNonAudioTrack = Math.max(...nonAudioItems.map(i => i.track), -1) + 1;
        
        [nonAudioItems, audioItems].forEach((items, sectionIndex) => {
            const sectionDiv = sectionIndex === 0 ? videoSection : audioSection;
            
            items.forEach(item => {
                const startSec = tcToSeconds(item.start_tc);
                const endSec = tcToSeconds(item.end_tc);
                const duration = endSec - startSec;
                
                let displayName = item.name;
                if (item.source_sequence) {
                    displayName = `${item.name} (From nested sequence: <b>${item.source_sequence}</b>)`;
                }
                
                const tooltipContent = `<b>Clip Name:</b> ${displayName}<br><b>Instances:</b> ${item.instance_count}<br><b>Timecode:</b> ${item.start_tc} - ${item.end_tc}<br><b>Type:</b> ${item.type}`;
                
                const itemDiv = document.createElement('div');
                
                let classList = `timeline-item ${item.type.toLowerCase().replace(' ', '-')}`;
                if (item.is_nested_child) {
                    classList += ' nested-child';
                }
                itemDiv.className = classList;
                
                itemDiv.style.left = `${(startSec / timelineDuration) * 100}%`;
                itemDiv.style.width = `${(duration / timelineDuration) * 100}%`;
                
                // Stack audio from top-down, non-audio from bottom-up
                let topPosition;
                if (item.is_audio) {
                    topPosition = item.track * 25;
                } else {
                    topPosition = (maxNonAudioTrack - 1 - item.track) * 25;
                }
                itemDiv.style.top = `${topPosition}px`;
                
                itemDiv.textContent = displayName;
                
                // Custom Tooltip Events
                const tooltipEl = document.getElementById('timeline-tooltip');
                itemDiv.addEventListener('mousemove', (e) => {
                    tooltipEl.innerHTML = tooltipContent;
                    tooltipEl.style.visibility = 'visible';
                    // Position tooltip near cursor, but don't let it go off-screen
                    const top = e.pageY + 15;
                    const left = Math.min(e.pageX + 15, document.body.clientWidth - tooltipEl.offsetWidth - 15);
                    tooltipEl.style.top = `${top}px`;
                    tooltipEl.style.left = `${left}px`;
                });
                
                itemDiv.addEventListener('mouseleave', () => {
                    tooltipEl.style.visibility = 'hidden';
                });
                
                sectionDiv.appendChild(itemDiv);
            });
        });
        
        // Set heights of sections
        const maxAudioTrack = Math.max(...audioItems.map(i => i.track), -1) + 1;
        const minAudioHeight = 50; // Minimum pixels to ensure the "Audio" label is visible
        
        videoSection.style.height = `${maxNonAudioTrack * 25}px`;
        audioSection.style.height = `${Math.max(minAudioHeight, maxAudioTrack * 25)}px`;
    }
    
    // Setup zoom controls
    zoomInButton.addEventListener('click', () => {
        zoomLevel = Math.min(8.0, zoomLevel * 1.5); // Max zoom 800%
        renderTimeline();
    });
    
    zoomOutButton.addEventListener('click', () => {
        zoomLevel = Math.max(1.0, zoomLevel / 1.5); // Min zoom 100%
        renderTimeline();
    });
    
    // Setup nested clips toggle
    showNestedClipsToggle.addEventListener('change', () => {
        renderTimeline();
        initTimelineHeight(); // Recalculate height as content changes
        
        // After rendering, the visualizer's height has changed.
        // We must now update the max-height of its parent collapsible container.
        const timelineCollapsible = document.querySelector('.timeline-container').closest('.collapsible-content');
        if (timelineCollapsible && timelineCollapsible.classList.contains('active')) {
            timelineCollapsible.style.maxHeight = (timelineCollapsible.scrollHeight + 50) + "px";
        }
    });
    
    // Initialize timeline label heights
    function initTimelineHeight() {
        const visualizerContent = document.querySelector('.timeline-visualizer-content');
        const labelGutter = document.getElementById('label-gutter');
        const labelContainer = document.getElementById('label-container');
        const separatorChar = document.getElementById('label-separator-char');
        
        // Get absolute positions to guarantee alignment
        const separatorRect = separator.getBoundingClientRect();
        const gutterRect = labelGutter.getBoundingClientRect();
        
        // Calculate the desired absolute Y position for the center of the separator char
        const separatorCenterY = separatorRect.top + (separatorRect.height / 2);
        const desiredGutterY = separatorCenterY - gutterRect.top;
        
        labelContainer.style.top = `${desiredGutterY - separatorChar.offsetTop - (separatorChar.offsetHeight / 2)}px`;
    }
    
    // Hide audio label and separator if there are no audio clips
    function setupAudioVisibility() {
        const audioItems = synthesizedTimelineItems.filter(item => item.is_audio);
        if (audioItems.length === 0) {
            document.getElementById('audio-label').style.display = 'none';
        }
        if (audioItems.length === 0 || timelineItems.length === audioItems.length) {
            separator.style.display = 'none';
        }
    }
    
    // Return functions that need to be called after DOM is ready
    return {
        renderTimeline,
        initTimelineHeight,
        setupAudioVisibility
    };
}

// --- Main Initialization ---
document.addEventListener('DOMContentLoaded', () => {
    console.log("DOM fully loaded. Starting initialization.");
    
    // Initialize data from backend first (backendData is set in HTML before this script)
    initializeData();
    
    // Set initial height for all active collapsible sections
    document.querySelectorAll('.collapsible-content.active').forEach(content => {
        content.style.maxHeight = (content.scrollHeight + 50) + "px";
    });
    
    // Setup all interactive components
    setupViewToggle();
    setupDownloadButton();
    makeTableInteractive('grouped-table');
    makeTableInteractive('per-instance-table');
    setupTableFilters();
    setupCollapsibleSections();
    
    // Setup and initialize timeline visualization
    const timeline = setupTimelineVisualization();
    timeline.setupAudioVisibility();
    timeline.renderTimeline();
    timeline.initTimelineHeight();
    
    // After the timeline is rendered, update its container height
    const timelineCollapsible = document.querySelector('.timeline-container').closest('.collapsible-content');
    if (timelineCollapsible && timelineCollapsible.classList.contains('active')) {
        timelineCollapsible.style.maxHeight = (timelineCollapsible.scrollHeight + 50) + "px";
    }
});