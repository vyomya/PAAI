"""
Header component for the application
"""

import streamlit as st
from datetime import datetime

def render_header():
    """Render the application header"""
    col1, col2, col3 = st.columns([2, 2, 1])
    
    with col1:
        st.title("🤖 AI Personal Assistant")
    
    with col3:
        current_time = datetime.now().strftime("%H:%M")
        st.metric("Time", current_time)
    
    st.divider()
