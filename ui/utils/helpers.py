"""
Helper utilities for UI components
"""

import streamlit as st
from datetime import datetime
from typing import Any, Dict, List

def format_timestamp(timestamp: datetime) -> str:
    """Format timestamp for display"""
    return timestamp.strftime("%B %d, %Y at %I:%M %p")

def display_error(message: str):
    """Display error message"""
    st.error(f"❌ {message}")

def display_success(message: str):
    """Display success message"""
    st.success(f"✅ {message}")

def display_warning(message: str):
    """Display warning message"""
    st.warning(f"⚠️ {message}")

def display_info(message: str):
    """Display info message"""
    st.info(f"ℹ️ {message}")

def display_loading(message: str = "Loading..."):
    """Display loading spinner"""
    with st.spinner(message):
        pass

def create_metric_card(title: str, value: Any, delta: str = None):
    """Create a metric card"""
    if delta:
        st.metric(title, value, delta)
    else:
        st.metric(title, value)

def create_two_column_layout():
    """Create a two column layout"""
    return st.columns(2)

def create_three_column_layout():
    """Create a three column layout"""
    return st.columns(3)

def truncate_text(text: str, max_length: int = 100) -> str:
    """Truncate text to max length"""
    if len(text) > max_length:
        return text[:max_length] + "..."
    return text
