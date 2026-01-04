"""
Session state management utilities
"""

import streamlit as st

def initialize_session_state():
    """Initialize all session state variables"""
    # Chat related
    if "messages" not in st.session_state:
        st.session_state.messages = []
    
    if "current_model" not in st.session_state:
        st.session_state.current_model = "gpt-4"
    
    # User preferences
    if "user_settings" not in st.session_state:
        st.session_state.user_settings = {
            "theme": "light",
            "notifications": True,
            "auto_save": True
        }
    
    # Email related
    if "emails" not in st.session_state:
        st.session_state.emails = []
    
    if "email_sync" not in st.session_state:
        st.session_state.email_sync = False
    
    # Tasks related
    if "tasks" not in st.session_state:
        st.session_state.tasks = []
    
    # Authentication
    if "authenticated" not in st.session_state:
        st.session_state.authenticated = False
    
    if "user_email" not in st.session_state:
        st.session_state.user_email = None

def clear_messages():
    """Clear chat messages from session"""
    st.session_state.messages = []

def add_message(role: str, content: str):
    """Add a message to session state"""
    st.session_state.messages.append({
        "role": role,
        "content": content
    })

def get_messages():
    """Get all messages from session state"""
    return st.session_state.messages
