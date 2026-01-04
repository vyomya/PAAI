"""
Pages module for multi-page Streamlit app
"""

from .chat import render_chat_page
from .emails import render_emails_page
from .tasks import render_tasks_page
from .settings import render_settings_page
from .about import render_about_page

__all__ = [
    "render_chat_page",
    "render_emails_page",
    "render_tasks_page",
    "render_settings_page",
    "render_about_page"
]
