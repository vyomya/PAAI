"""
Configuration utilities for Streamlit UI
"""

import streamlit as st
from pathlib import Path

def set_page_config():
    """Set up initial page configuration"""
    st.set_page_config(
        page_title="AI Personal Assistant",
        page_icon="🤖",
        layout="wide",
        initial_sidebar_state="expanded",
        menu_items={
            'Get Help': 'https://github.com/vyomya/PAAI',
            'Report a bug': 'https://github.com/vyomya/PAAI/issues',
            'About': '# AI Personal Assistant\nPowered by advanced LLM technology'
        }
    )

def load_custom_css():
    """Load custom CSS styling"""
    css_path = Path(__file__).parent.parent / "assets" / "style.css"
    if css_path.exists():
        with open(css_path, "r") as f:
            st.markdown(f"<style>{f.read()}</style>", unsafe_allow_html=True)

def get_theme_config():
    """Get theme configuration"""
    return {
        "primaryColor": "#FF6B35",
        "backgroundColor": "#F7F7F7",
        "secondaryBackgroundColor": "#E8E8E8",
        "textColor": "#262730",
        "font": "sans serif"
    }
