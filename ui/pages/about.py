"""
About page - Information about the application
"""

import streamlit as st

def render_about_page():
    """Render the about page"""
    st.markdown("## ℹ️ About AI Personal Assistant")
    
    st.markdown("""
    ### Welcome to PAAI
    
    **AI Personal Assistant (PAAI)** is an intelligent personal assistant designed to help you manage
    your daily tasks, communications, and information processing using advanced language models.
    
    ---
    
    ### Key Features
    
    🤖 **Intelligent Chat**
    - Natural language conversations
    - Context-aware responses
    - Multi-turn dialogue support
    
    📧 **Email Management**
    - Gmail integration
    - Smart email filtering
    - Automated email responses
    
    ✅ **Task Management**
    - Create and organize tasks
    - Priority-based filtering
    - Deadline tracking
    
    🔐 **Privacy & Security**
    - End-to-end encrypted communication
    - Secure API key storage
    - Local data processing options
    
    ---
    
    ### Technology Stack
    
    - **Frontend:** Streamlit
    - **Backend:** Python
    - **LLM:** OpenAI, Anthropic, or local models
    - **APIs:** Gmail API, Custom tools
    - **Database:** Session state management
    
    ---
    
    ### Getting Started
    
    1. Go to **Settings** and authenticate with your Gmail account
    2. Configure your preferred LLM model
    3. Start chatting in the **Chat** section
    4. Manage your emails in the **Emails** section
    5. Organize tasks in the **Tasks** section
    
    ---
    
    ### Documentation
    
    For detailed documentation and API reference, visit the [GitHub repository](https://github.com/vyomya/PAAI).
    
    ### Support
    
    Found a bug or have a feature request? [Open an issue](https://github.com/vyomya/PAAI/issues) on GitHub.
    
    ---
    
    ### License
    
    This project is licensed under the MIT License. See LICENSE file for details.
    
    **© 2026 PAAI - AI Personal Assistant**
    """)
    
    st.divider()
    
    col1, col2, col3 = st.columns(3)
    
    with col1:
        st.metric("Version", "1.0.0")
    
    with col2:
        st.metric("Status", "Active")
    
    with col3:
        st.metric("Last Updated", "2026-01-04")
