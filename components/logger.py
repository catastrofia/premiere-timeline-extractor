"""
Centralized logging configuration for the Premiere Pro timeline extractor.
Replaces print() statements with structured logging.
"""
import logging
import os
import sys
from typing import Optional, TextIO, Union

# Define logger levels
DEBUG = logging.DEBUG
INFO = logging.INFO
WARNING = logging.WARNING
ERROR = logging.ERROR
CRITICAL = logging.CRITICAL

# Create the main application logger
logger = logging.getLogger('premiere_timeline')

def setup_logging(level: int = logging.INFO, 
                 log_file: Optional[str] = None,
                 file_handler_level: int = logging.DEBUG) -> None:
    """
    Configure the application logger with console and optional file output.
    
    Args:
        level: Logging level for console output
        log_file: Optional path to log file
        file_handler_level: Logging level for file output
    """
    # Clear any existing handlers
    for handler in logger.handlers[:]:
        logger.removeHandler(handler)
    
    # Set the base logger level to the lowest of console/file to ensure messages are processed
    logger.setLevel(min(level, file_handler_level if log_file else level))
    
    # Create console handler
    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setLevel(level)
    console_format = logging.Formatter('%(asctime)s - %(levelname)s - %(message)s')
    console_handler.setFormatter(console_format)
    logger.addHandler(console_handler)
    
    # Create file handler if log_file is specified
    if log_file:
        # Ensure directory exists
        log_dir = os.path.dirname(log_file)
        if log_dir and not os.path.exists(log_dir):
            os.makedirs(log_dir)
            
        file_handler = logging.FileHandler(log_file, encoding='utf-8')
        file_handler.setLevel(file_handler_level)
        file_format = logging.Formatter('%(asctime)s - %(levelname)s - %(message)s')
        file_handler.setFormatter(file_format)
        logger.addHandler(file_handler)

def get_logger() -> logging.Logger:
    """
    Get the configured application logger.
    
    Returns:
        The configured logger instance
    """
    return logger

class LogCapture:
    """Context manager to capture log output to a string buffer."""
    
    def __init__(self, target_logger: Optional[logging.Logger] = None, level: int = logging.DEBUG):
        """
        Initialize log capture.
        
        Args:
            target_logger: Logger to capture (defaults to application logger)
            level: Minimum log level to capture
        """
        self.logger = target_logger or logger
        self.level = level
        self.string_io = None
        self.string_handler = None
        self.previous_level = None
        
    def __enter__(self) -> TextIO:
        """Start capturing logs to a string buffer."""
        import io
        self.string_io = io.StringIO()
        self.string_handler = logging.StreamHandler(self.string_io)
        self.string_handler.setLevel(self.level)
        formatter = logging.Formatter('%(message)s')  # Simplified format for captured output
        self.string_handler.setFormatter(formatter)
        
        # Store and potentially adjust the logger level
        self.previous_level = self.logger.level
        if self.level < self.previous_level:
            self.logger.setLevel(self.level)
            
        self.logger.addHandler(self.string_handler)
        return self.string_io
        
    def __exit__(self, exc_type, exc_val, exc_tb):
        """Stop capturing and restore logger state."""
        if self.string_handler:
            self.logger.removeHandler(self.string_handler)
            
        # Restore previous logger level if we changed it
        if self.previous_level is not None and self.logger.level != self.previous_level:
            self.logger.setLevel(self.previous_level)

# Initialize with default settings
setup_logging()