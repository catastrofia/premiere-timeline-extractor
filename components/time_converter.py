"""
Time conversion utilities for Premiere Pro timeline data.
Handles conversion between ticks, frames, seconds, and timecode formats.
"""
from typing import Optional, Union, Tuple
import math
from config import config
from components.logger import get_logger

logger = get_logger()

def tc_to_seconds(tc: Optional[str]) -> float:
    """
    Converts HH:MM:SS timecode string to seconds.
    
    Args:
        tc: Timecode string in HH:MM:SS format
        
    Returns:
        Equivalent time in seconds as float
    """
    if not tc:
        return 0.0
    
    parts = tc.split(':')
    if len(parts) != 3:
        return 0.0
    
    try:
        h, m, s = map(int, parts)
        return float(h * 3600 + m * 60 + s)
    except (ValueError, TypeError):
        return 0.0

def tc_from_seconds(s: Union[int, float]) -> str:
    """
    Converts seconds to HH:MM:SS timecode string.
    
    Args:
        s: Time in seconds
        
    Returns:
        Formatted timecode string
    """
    s_round = int(round(float(s)))
    if s_round < 0:
        sign = '-'
        s_abs = -s_round
    else:
        sign = ''
        s_abs = s_round
        
    hh = s_abs // 3600
    mm = (s_abs % 3600) // 60
    ss = s_abs % 60
    
    return f"{sign}{hh:02d}:{mm:02d}:{ss:02d}"

def seconds_aligned_from_raw(
    raw: Optional[int], 
    ticks_per_frame: Optional[int], 
    fps: Optional[float]
) -> Optional[float]:
    """
    Converts Premiere Pro raw tick values to seconds.
    
    Premiere stores TrackItem Start/End in integer 'ticks'. The TrackGroup/FrameRate
    element in the sequence appears to hold the number of ticks per frame (not ticks/sec).
    So: frames = raw / ticks_per_frame; seconds = frames / fps
    
    Args:
        raw: Raw tick value from Premiere Pro XML
        ticks_per_frame: Number of ticks per frame
        fps: Frames per second
        
    Returns:
        Time in seconds, or None if conversion not possible
    """
    if raw is None or ticks_per_frame is None or fps is None:
        return None
        
    frames = float(raw) / float(ticks_per_frame)
    # Frames should be integral (or very close); align to nearest frame
    frames_rounded = round(frames)
    seconds = frames_rounded / float(fps)
    
    return seconds

def get_fps_from_raw_value(frame_rate_value: int) -> Tuple[float, bool]:
    """
    Maps raw Premiere Pro frame rate value to a standard FPS value.
    
    Args:
        frame_rate_value: Raw frame rate value from Premiere Pro XML
        
    Returns:
        Tuple of (fps_value, is_common_value) where is_common_value indicates
        if this is a recognized standard frame rate
    """
    # First try direct lookup
    familiar_fps = config.FPS_MAP.get(frame_rate_value)
    if familiar_fps:
        return familiar_fps, True
        
    # Handle cases where the value from XML is scaled (e.g., by 1000)
    temp_val = frame_rate_value
    while temp_val > 1000000:  # A reasonable lower bound for these tick values
        if temp_val in config.FPS_MAP:
            return config.FPS_MAP[temp_val], True
        temp_val //= 10  # Scale down and try again
            
    # If we can't find a match, log a warning and return the default
    logger.warning(f"Unrecognized frame rate value: {frame_rate_value}. Using default: {config.DEFAULT_FPS}")
    return config.DEFAULT_FPS, False

def ensure_minimum_duration(start_sec: float, end_sec: float) -> Tuple[float, float]:
    """
    Ensures a clip has the minimum required duration.
    
    Args:
        start_sec: Start time in seconds
        end_sec: End time in seconds
        
    Returns:
        Tuple of (start_sec, end_sec) with minimum duration applied
    """
    duration = end_sec - start_sec
    
    # If duration is less than minimum and start is within reasonable range
    if duration < config.MIN_CLIP_DURATION and start_sec < 3600:
        end_sec = start_sec + config.MIN_CLIP_DURATION
        
    return start_sec, end_sec