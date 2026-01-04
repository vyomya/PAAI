"""
AI Personal Assistant - Main Streamlit Application
Entry point for the web UI
"""

import streamlit as st
import sys
from pathlib import Path

# Add parent directory to path to import main modules
sys.path.insert(0, str(Path(__file__).parent.parent))

from utils.config import set_page_config, load_custom_css
from utils.session import initialize_session_state
from components.sidebar import render_sidebar
from components.header import render_header

def main():
    """Main application entry point"""
    # Configure page
    set_page_config()
    
    # Load custom CSS
    load_custom_css()
    
    # Initialize session state
    initialize_session_state()
    
    # Render header
    render_header()
    
    # Render sidebar
    sidebar_selection = render_sidebar()
    
    # Display main content based on sidebar selection
    if sidebar_selection == "Home":
        st.markdown("## 🏠 Welcome to AI Personal Assistant")
        st.info("Select an option from the sidebar to get started.")
        st.divider()
        
        col1, col2, col3 = st.columns(3)
        with col1:
            st.metric("Requests", "0", "Today")
        with col2:
            st.metric("Tasks", "0", "Pending")
        with col3:
            st.metric("Status", "Active", "Online")
    
    elif sidebar_selection == "Chat":
        from pages.chat import render_chat_page
        render_chat_page()
    
    elif sidebar_selection == "Emails":
        from pages.emails import render_emails_page
        render_emails_page()
    
    elif sidebar_selection == "Tasks":
        from pages.tasks import render_tasks_page
        render_tasks_page()
    
    elif sidebar_selection == "Settings":
        from pages.settings import render_settings_page
        render_settings_page()
    
    elif sidebar_selection == "About":
        from pages.about import render_about_page
        render_about_page()

if __name__ == "__main__":
    main()
