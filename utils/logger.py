"""
ORC Research Dashboard - Logging Module
Provides structured logging for the application
"""

import logging
import sys
from datetime import datetime
from pathlib import Path

# Create logger instance
logger = logging.getLogger("ORC_Dashboard")

# Configure logging format
LOG_FORMAT = "%(asctime)s | %(level)-8s | %(name)s | %(message)s"
DATE_FORMAT = "%Y-%m-%d %H:%M:%S"


def setup_logger(level=logging.INFO, log_to_file=False, log_file="logs/orc.log"):
    """
    Setup and configure the logger
    
    Args:
        level: Logging level (default: INFO)
        log_to_file: Whether to log to a file
        log_file: Path to log file
    """
    # Clear existing handlers
    logger.handlers.clear()
    
    # Set level
    logger.setLevel(level)
    
    # Console handler
    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setLevel(level)
    console_formatter = logging.Formatter(LOG_FORMAT, DATE_FORMAT)
    console_handler.setFormatter(console_formatter)
    logger.addHandler(console_handler)
    
    # File handler (optional)
    if log_to_file:
        log_path = Path(log_file)
        log_path.parent.mkdir(parents=True, exist_ok=True)
        
        file_handler = logging.FileHandler(log_file)
        file_handler.setLevel(level)
        file_handler.setFormatter(console_formatter)
        logger.addHandler(file_handler)
    
    return logger


# Default setup
_logger = setup_logger()


# Convenience functions
def log_info(message: str):
    """Log info message"""
    _logger.info(message)


def log_warning(message: str):
    """Log warning message"""
    _logger.warning(message)


def log_error(message: str, exc_info=False):
    """Log error message"""
    _logger.error(message, exc_info=exc_info)


def log_debug(message: str):
    """Log debug message"""
    _logger.debug(message)


def log_exception(message: str):
    """Log exception with traceback"""
    _logger.exception(message)


# ============================================
# APPLICATION LOGGING
# ============================================

def log_app_start():
    """Log application start"""
    log_info("=" * 50)
    log_info("ORC Research Dashboard Started")
    log_info(f"Time: {datetime.now().isoformat()}")
    log_info("=" * 50)


def log_sync_start(orcid: str):
    """Log sync operation start"""
    log_info(f"Starting sync for ORCID: {orcid[:8]}***")


def log_sync_complete(count: int, duration: float):
    """Log sync operation complete"""
    log_info(f"Sync complete: {count} publications in {duration:.2f}s")


def log_api_request(endpoint: str, status_code: int, duration: float):
    """Log API request"""
    log_info(f"API {endpoint} -> {status_code} ({duration:.2f}s)")


def log_user_action(action: str, user: str = "anonymous"):
    """Log user action"""
    log_info(f"User action: {action} by {user}")


def log_security_event(event: str, details: str = ""):
    """Log security event"""
    log_warning(f"SECURITY: {event} - {details}")