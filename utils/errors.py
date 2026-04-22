"""
ORC Research Dashboard - Error Handling Module
Provides better error boundaries and user-friendly error messages
"""

import streamlit as st
import traceback
from datetime import datetime
from typing import Callable, Optional, Any


class ErrorBoundary:
    """
    Context manager for handling errors gracefully
    
    Usage:
        with ErrorBoundary("Loading data"):
            data = load_data()
    """
    
    def __init__(self, context: str = "Operation"):
        self.context = context
        self.error = None
    
    def __enter__(self):
        return self
    
    def __exit__(self, exc_type, exc_val, exc_tb):
        if exc_type is not None:
            self.error = str(exc_val)
            st.error(f"❌ {self.context} failed: {exc_val}")
            return True  # Suppress exception


def handle_error(error: Exception, context: str = "", show_traceback: bool = False):
    """
    Handle error with user-friendly message
    
    Args:
        error: The exception that occurred
        context: Context description
        show_traceback: Whether to show technical details
    """
    error_message = str(error)
    
    # Log to session state for debugging
    if 'error_log' not in st.session_state:
        st.session_state.error_log = []
    
    st.session_state.error_log.append({
        'timestamp': datetime.now().isoformat(),
        'context': context,
        'error': error_message
    })
    
    # Show user-friendly message
    if context:
        st.error(f"❌ {context}: {error_message}")
    else:
        st.error(f"❌ An error occurred: {error_message}")
    
    # Optionally show technical details
    if show_traceback:
        with st.expander("Technical Details"):
            st.code(traceback.format_exc())


def show_error_state(title: str = "Something went wrong", message: str = ""):
    """
    Show a friendly error state with retry option
    
    Args:
        title: Error title
        message: Error message
    """
    st.error(f"❌ {title}")
    if message:
        st.info(message)
    
    # Retry button
    if st.button("🔄 Try Again"):
        st.rerun()


def show_loading_state(message: str = "Loading..."):
    """
    Show a loading state
    
    Args:
        message: Loading message
    """
    return st.spinner(f"⏳ {message}")


def safe_execute(func: Callable, default: Any = None, context: str = "") -> Any:
    """
    Execute function with error handling
    
    Args:
        func: Function to execute
        default: Default value on error
        context: Context for error message
        
    Returns:
        Function result or default value
    """
    try:
        return func()
    except Exception as e:
        handle_error(e, context)
        return default


# ============================================
# DECORATORS
# ============================================

def with_error_handling(context: str = ""):
    """
    Decorator for functions with error handling
    
    Usage:
        @with_error_handling("Fetching data")
        def fetch_data():
            ...
    """
    def decorator(func):
        def wrapper(*args, **kwargs):
            try:
                return func(*args, **kwargs)
            except Exception as e:
                error_context = context or func.__name__
                handle_error(e, error_context)
                return None
        return wrapper
    return decorator


# ============================================
# UI COMPONENTS
# ============================================

def render_error_card(error: str, timestamp: str = ""):
    """
    Render an error card component
    
    Args:
        error: Error message
        timestamp: Error timestamp
    """
    st.markdown(f"""
    <div style="
        background: #1e293b;
        border: 1px solid #ef4444;
        border-radius: 8px;
        padding: 1rem;
        margin: 1rem 0;
    ">
        <h3 style="color: #ef4444; margin-top: 0;">❌ Error</h3>
        <p style="color: #e2e8f0;">{error}</p>
        <small style="color: #64748b;">{timestamp}</small>
    </div>
    """, unsafe_allow_html=True)


def render_success_message(message: str):
    """Render a success message"""
    st.markdown(f"""
    <div style="
        background: #1e293b;
        border: 1px solid #22c55e;
        border-radius: 8px;
        padding: 1rem;
        margin: 1rem 0;
    ">
        <h3 style="color: #22c55e; margin-top: 0;">✅ Success</h3>
        <p style="color: #e2e8f0;">{message}</p>
    </div>
    """, unsafe_allow_html=True)


def render_warning_message(message: str):
    """Render a warning message"""
    st.markdown(f"""
    <div style="
        background: #1e293b;
        border: 1px solid #fbbf24;
        border-radius: 8px;
        padding: 1rem;
        margin: 1rem 0;
    ">
        <h3 style="color: #fbbf24; margin-top: 0;">⚠️ Warning</h3>
        <p style="color: #e2e8f0;">{message}</p>
    </div>
    """, unsafe_allow_html=True)