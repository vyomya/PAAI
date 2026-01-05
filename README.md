# Personal Agentic AI Assistant (PAAI)

A production-grade agentic personal assistant framework built with LangGraph, designed to orchestrate multiple specialized agents capable of reasoning, planning, and executing tasks across integrated tools including email, calendar, and long-term memory systems.

This project demonstrates how agentic workflows can evolve beyond single-turn conversational interfaces toward sophisticated executive assistant systems for real-world applications.

---

## Features

- **Multi-Agent Architecture**: Built on LangGraph for coordinated agent orchestration
- **Modular Design**: Separation of concerns across planning, execution, and tool usage layers
- **Gmail Integration**: Full Gmail API integration for email-based workflows
- **Calendar-Aware Planning**: Context-aware scheduling capabilities (in development)
- **Long-Term Memory**: User preference management and persistent context (planned)
- **Interactive Interface**: Streamlit-based UI for agent interaction and monitoring

---

## System Architecture

The system leverages LangGraph to coordinate multiple specialized agents through structured state transitions. Each agent operates within a defined scope, invoking tools explicitly based on task requirements. This architecture supports extensibility, research experimentation, and production deployment scenarios.

---

## Project Structure

```
PAAI/
├── api.py                  # Backend API for agent execution
├── ui/
│   └── main.py             # Streamlit UI entry point
├── agents/                 # Agent definitions and configurations
├── tools/                  # Tool integrations (Gmail, memory, etc.)
├── requirements.txt        # Project dependencies
└── README.md              # Project documentation
```

---

## Setup Instructions

### Prerequisites

- Python 3.8 or higher
- Google Cloud Platform account (for Gmail API)
- OpenAI API key

### Installation

**1. Clone the repository**

```bash
git clone https://github.com/vyomya/PAAI.git
cd PAAI
```

**2. Create and activate virtual environment**

```bash
python -m venv venv
source venv/bin/activate  # macOS/Linux
# venv\Scripts\activate   # Windows
```

**3. Install dependencies**

```bash
pip install -r requirements.txt
```

### Configuration

**Gmail API Setup**

Create the following files in the project root directory:

- `credentials.json` - Download from Google Cloud Console after enabling the Gmail API
- `token.json` - Auto-generated during first authentication

**OpenAI API Key**

Create a file named `openAIkey.txt` in the project root:

```text
sk-your-api-key-here
```

---

## Running the Application

**1. Start the backend API**

```bash
python api.py
```

**2. Launch the Streamlit interface** (in a separate terminal)

```bash
streamlit run ui/main.py
```

The application interface will open automatically in your default browser.

---

## Development Roadmap

Active development items are tracked in the GitHub Issues section:

- Long-term memory and preference management system
- Calendar integration and scheduling intelligence
- User authentication and authorization framework
- Enhanced agent reasoning and response quality
- UI/UX improvements and workflow optimization

For detailed tracking of features and bugs, please refer to the Issues section of the repository.

---

## Contributing

Contributions are welcome from researchers, engineers, and AI practitioners. Areas of particular interest include:

- Novel agent architectures and coordination patterns
- Memory system improvements
- Tool integration enhancements
- Performance optimization
- Documentation and testing

Please review open Issues before starting work on new features.

---

## Technical Background

This project explores practical implementations of agentic AI systems, focusing on:

- Multi-agent coordination using graph-based state machines
- Tool-augmented language model reasoning
- Long-term context management
- Real-world task execution reliability

The system is designed for both research experimentation and production deployment scenarios.


---

## Contact

For questions, collaboration opportunities, or technical discussions regarding agentic AI systems and LLM applications, please open an issue or reach out through GitHub.

**Repository**: [https://github.com/vyomya/PAAI](https://github.com/vyomya/PAAI)
