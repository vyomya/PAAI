"""
Chat page - Interactive chat interface
"""

import streamlit as st
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from utils.session import add_message, get_messages, clear_messages

def render_chat_page():
    """Render the chat page"""
    st.markdown("## 💬 Chat with AI")
    
    col1, col2 = st.columns([4, 1])
    with col2:
        if st.button("Clear Chat", key="clear_chat_btn"):
            clear_messages()
            st.rerun()
    
    st.divider()
    
    # Chat history display
    messages = get_messages()
    
    chat_container = st.container()
    
    with chat_container:
        for message in messages:
            if message["role"] == "user":
                st.chat_message("user").write(message["content"])
            else:
                st.chat_message("assistant").write(message["content"])
    
    # Chat input
    st.divider()
    
    user_input = st.chat_input("Type your message here...")
    
    if user_input:
        # Add user message
        add_message("user", user_input)
        
        # Display user message
        st.chat_message("user").write(user_input)
        
        # Simulate AI response (replace with actual LLM call)
        with st.spinner("AI is thinking..."):
            # TODO: Integrate with your LLM module
            response = f"Echo: {user_input}"
            add_message("assistant", response)
            st.chat_message("assistant").write(response)
        
        st.rerun()
