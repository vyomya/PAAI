"""
Emails page - Email management interface
"""

import streamlit as st
from datetime import datetime

def render_emails_page():
    """Render the emails page"""
    st.markdown("## 📧 Emails")
    
    # Email filters
    col1, col2, col3 = st.columns(3)
    
    with col1:
        filter_status = st.selectbox(
            "Filter by Status",
            ["All", "Unread", "Read", "Starred"],
            key="email_filter"
        )
    
    with col2:
        search_term = st.text_input("Search emails", key="email_search")
    
    with col3:
        if st.button("🔄 Sync Emails", key="sync_emails_btn"):
            st.session_state.email_sync = True
            st.toast("Syncing emails...", icon="⏳")
    
    st.divider()
    
    # Email list
    if st.session_state.emails:
        for email in st.session_state.emails:
            with st.container(border=True):
                col1, col2 = st.columns([3, 1])
                
                with col1:
                    st.markdown(f"**From:** {email.get('from', 'Unknown')}")
                    st.markdown(f"**Subject:** {email.get('subject', 'No subject')}")
                    st.caption(email.get('date', 'Unknown date'))
                
                with col2:
                    if st.button("🔍 View", key=f"view_email_{email.get('id', 'unknown')}"):
                        st.session_state.selected_email = email
    else:
        st.info("No emails to display. Try syncing your inbox.")
    
    # Email detail view
    if "selected_email" in st.session_state:
        st.divider()
        st.markdown("### Email Details")
        
        email = st.session_state.selected_email
        st.markdown(f"**From:** {email.get('from', 'Unknown')}")
        st.markdown(f"**Subject:** {email.get('subject', 'No subject')}")
        st.markdown(f"**Date:** {email.get('date', 'Unknown')}")
        st.divider()
        st.markdown(email.get('body', 'No content'))
        
        if st.button("Close", key="close_email_btn"):
            if "selected_email" in st.session_state:
                del st.session_state.selected_email
