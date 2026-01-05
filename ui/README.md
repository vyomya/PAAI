# AI Personal Assistant - Streamlit UI

This directory contains the Streamlit web UI for the AI Personal Assistant (PAAI) application.

## 📁 Folder Structure

```
ui/
├── main.py                 # Main application entry point
├── requirements.txt        # Python dependencies
├── README.md              # This file
│
├── .streamlit/
│   └── config.toml        # Streamlit configuration
│
├── pages/                 # Multi-page app pages
│   ├── __init__.py
│   ├── chat.py            # Chat interface
│   ├── emails.py          # Email management
│   ├── tasks.py           # Task management
│   ├── settings.py        # User settings & preferences
│   └── about.py           # About page
│
├── components/            # Reusable UI components
│   ├── __init__.py
│   ├── header.py          # Application header
│   └── sidebar.py         # Navigation sidebar
│
├── utils/                 # Utility functions
│   ├── __init__.py
│   ├── config.py          # Configuration utilities
│   ├── session.py         # Session state management
│   └── helpers.py         # Helper functions
│
└── assets/                # Static assets
    ├── style.css          # Custom CSS styling
    └── images/            # Icons and images (future)
```

## 🚀 Quick Start

### Installation

1. Install dependencies:
```bash
pip install -r requirements.txt
```

2. From the `ui/` directory, run:
```bash
streamlit run main.py
```

The application will open in your browser at `http://localhost:8501`

## 📖 Pages Overview

### 🏠 Home
- Application dashboard
- Quick statistics
- Status indicators

### 💬 Chat
- Interactive chat interface with AI
- Message history
- Clear chat functionality
- Real-time responses

### 📧 Emails
- Gmail integration
- Email synchronization
- Search and filter emails
- Email detail view

### ✅ Tasks
- Create and manage tasks
- Priority-based organization
- Status tracking
- Due date management

### ⚙️ Settings
- Account configuration
- User preferences
- API key management
- Model selection
- Theme settings

### ℹ️ About
- Application information
- Feature overview
- Technology stack
- Support links

## 🔧 Configuration

### Streamlit Configuration
Edit `.streamlit/config.toml` to customize:
- Theme colors
- Page layout
- Server settings
- Browser behavior

### Custom Styling
Modify `assets/style.css` to customize the look and feel.

## 🔌 Integration with Backend

The UI is designed to integrate with the main PAAI backend modules:

- **`llm.py`**: LLM integration for chat responses
- **`gmail_api.py`**: Gmail API for email management
- **`agentic_framework.py`**: Agent orchestration
- **`tool.py`**: Tool definitions
- **`prompts.py`**: Prompt templates

Example integration in `pages/chat.py`:
```python
from llm import generate_response

response = generate_response(user_input)
```

## 🎨 Customization

### Adding New Pages

1. Create a new file in `pages/` folder:
```python
# pages/new_page.py
import streamlit as st

def render_new_page():
    st.markdown("## New Page")
    # Your content here

# pages/__init__.py
from .new_page import render_new_page
```

2. Add navigation to `components/sidebar.py`:
```python
options=["Home", "Chat", "New Page", "Settings", "About"]
```

3. Add handling in `main.py`:
```python
elif sidebar_selection == "New Page":
    from pages.new_page import render_new_page
    render_new_page()
```

### Creating Reusable Components

Add new components to the `components/` folder:

```python
# components/my_component.py
import streamlit as st

def render_my_component():
    # Your component code here
    pass
```

## 🔐 Security Considerations

- API keys are stored in session state (update for production)
- Consider using environment variables
- Implement proper authentication
- Validate all user inputs
- Use HTTPS in production

## 📦 Dependencies

- **streamlit**: Web framework
- **streamlit-option-menu**: Enhanced navigation
- **python-dotenv**: Environment variable management
- **requests**: HTTP library for API calls

## 🐛 Troubleshooting

### Application won't start
- Check if port 8501 is available
- Verify all dependencies are installed
- Check Python version (3.9+)

### Pages not loading
- Ensure all page files are in `pages/` folder
- Check imports in `main.py`
- Verify function names match

### Styling not applied
- Check `assets/style.css` exists
- Verify CSS syntax
- Clear browser cache

## 📝 Notes

- Session state is cleared on browser refresh
- Messages are stored in `st.session_state`
- For persistent storage, implement a database
- Consider using `@st.cache_data` for expensive operations

## 🤝 Contributing

To add new features:
1. Create appropriate files in respective folders
2. Update `__init__.py` files
3. Update main.py if adding pages
4. Test thoroughly

## 📄 License

Part of the PAAI project. See main README for license details.

## 🔗 Links

- [Streamlit Docs](https://docs.streamlit.io)
- [PAAI GitHub](https://github.com/vyomya/PAAI)
- [Report Issues](https://github.com/vyomya/PAAI/issues)
