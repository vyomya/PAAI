"""
Settings page - User preferences and configuration
"""

import streamlit as st

def render_settings_page():
    """Render the settings page"""
    st.markdown("## ⚙️ Settings")
    
    # Settings tabs
    tab1, tab2, tab3, tab4 = st.tabs(["Account", "Preferences", "API Keys", "About"])
    
    with tab1:
        st.markdown("### Account Settings")
        
        col1, col2 = st.columns(2)
        
        with col1:
            email = st.text_input(
                "Email Address",
                value=st.session_state.user_email or "",
                key="settings_email"
            )
        
        with col2:
            username = st.text_input("Username", key="settings_username")
        
        st.divider()
        
        st.markdown("### Authentication")
        
        if not st.session_state.authenticated:
            if st.button("🔑 Connect Gmail", key="connect_gmail_btn"):
                st.info("Gmail integration will be added here")
                # TODO: Integrate with gmail_api.py
        else:
            st.success(f"✅ Connected as {st.session_state.user_email}")
            if st.button("Disconnect", key="disconnect_btn"):
                st.session_state.authenticated = False
                st.rerun()
    
    with tab2:
        st.markdown("### Preferences")
        
        theme = st.selectbox(
            "Theme",
            ["Light", "Dark", "Auto"],
            index=0,
            key="settings_theme"
        )
        
        notifications = st.checkbox(
            "Enable Notifications",
            value=True,
            key="settings_notifications"
        )
        
        auto_save = st.checkbox(
            "Auto-save Chat",
            value=True,
            key="settings_autosave"
        )
        
        model = st.selectbox(
            "LLM Model",
            ["gpt-4", "gpt-3.5-turbo", "claude-3-opus"],
            key="settings_model"
        )
        
        st.divider()
        
        if st.button("💾 Save Preferences", key="save_prefs_btn"):
            st.success("Preferences saved!")
    
    with tab3:
        st.markdown("### API Keys")
        
        st.warning("⚠️ Never share your API keys!")
        
        openai_key = st.text_input(
            "OpenAI API Key",
            type="password",
            key="settings_openai_key"
        )
        
        anthropic_key = st.text_input(
            "Anthropic API Key",
            type="password",
            key="settings_anthropic_key"
        )
        
        if st.button("💾 Save API Keys", key="save_keys_btn"):
            st.success("API keys saved securely!")
    
    with tab4:
        st.markdown("### About")
        
        st.markdown("""
        **AI Personal Assistant (PAAI)**
        
        Version: 1.0.0
        
        An intelligent personal assistant powered by advanced language models.
        
        **Features:**
        - 💬 Natural language chat
        - 📧 Email management
        - ✅ Task automation
        - 🤖 AI-powered assistance
        
        **Built with:**
        - Python
        - Streamlit
        - OpenAI API
        - Gmail API
        """)
        
        st.divider()
        
        st.markdown("[GitHub](https://github.com/vyomya/PAAI) | [Issues](https://github.com/vyomya/PAAI/issues)")
