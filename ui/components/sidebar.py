"""
Sidebar component for navigation
"""

import streamlit as st

def render_sidebar():
    """Render the sidebar navigation"""
    with st.sidebar:
        st.markdown("### Navigation")
        
        # Navigation menu
        page = st.radio(
            "Go to",
            options=[
                "Home",
                "Chat",
                "Emails",
                "Tasks",
                "Settings",
                "About"
            ],
            label_visibility="collapsed"
        )
        
        st.divider()
        
        # Status section
        st.markdown("### Status")
        
        col1, col2 = st.columns(2)
        with col1:
            st.metric("Connection", "Active", "🟢")
        with col2:
            st.metric("API", "Ready", "🟢")
        
        st.divider()
        
        # User section
        st.markdown("### User")
        
        if st.session_state.authenticated:
            st.write(f"Logged in as: {st.session_state.user_email}")
            if st.button("Logout", key="logout_btn"):
                st.session_state.authenticated = False
                st.rerun()
        else:
            st.info("Not authenticated. Go to Settings to login.")
        
        st.divider()
        
        # Footer
        st.caption("© 2026 PAAI - AI Personal Assistant")
    
    return page
