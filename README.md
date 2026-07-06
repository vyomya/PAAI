# Personal Agentic AI Assistant (PAAI)

A production-grade agentic personal assistant built with LangGraph and Alibaba Cloud's Qwen model (qwen-plus via DashScope). It orchestrates multiple specialized agents — Summarizer, Priority, Email, Calendar, and History — to manage Gmail, Google Calendar, and long-term user memory in a single conversational interface.

---

## Demo

[![PAAI Demo](https://img.shields.io/badge/YouTube-Demo-red?logo=youtube)](https://www.youtube.com/watch?v=ElsC_qagOJA)

[Watch the 3-minute demo on YouTube →](https://www.youtube.com/watch?v=ElsC_qagOJA)

---

## Alibaba Cloud

This project runs on **Alibaba Cloud Model Studio (DashScope)** using the `qwen-plus` model via OpenAI-compatible API.

- [View Alibaba Cloud integration proof →](docs/alibaba_cloud_proof.md)

All LLM inference — planning, classification, agent execution, preference extraction, and step evaluation — routes through DashScope's international endpoint.

---

## Architecture

PAAI Architecture

<img width="528" height="498" alt="image" src="https://github.com/user-attachments/assets/7ca5ca0c-6d51-4041-9700-2b165e61a742" />

The system uses LangGraph to coordinate agents through structured state transitions. An LLM-based classifier routes each message to the right flow before the planner runs. Each agent operates within a defined scope and invokes tools explicitly. A persistent memory layer stores conversation history (ChromaDB) and user preferences (SQLite) across sessions.

---

## Features

- **Multi-agent orchestration** — Planner, Summarizer, Priority, Email, Calendar, and History agents coordinated via LangGraph
- **LLM-based classifier** — Replaces keyword regex; understands task, preference, and correction intent in natural language
- **Step-level evaluation loop** — Each agent output is validated against its specific step goal and automatically retried with targeted feedback
- **Persistent semantic memory** — ChromaDB vector embeddings for conversation retrieval; `GetRecentMessages` and `SearchMessages` tools for the history agent
- **Dynamic preference system** — Confidence scoring, per-agent scope, passive learning from every interaction, and decay over time
- **Gmail integration** — Full Gmail API for fetching, reading, and drafting emails
- **Google Calendar integration** — Fetch and create calendar events
- **FastAPI backend + Streamlit UI**
- **Powered by Qwen** — `qwen-plus` via Alibaba Cloud DashScope

---

## Project Structure

```
PAAI/
├── api.py                      # FastAPI backend
├── agentic_framework.py        # LangGraph graph, all agent nodes, routing logic
├── db.py                       # ChromaDB (messages) + SQLite (preferences, sessions)
├── prompts.py                  # All LLM prompts — planner, agents, evaluators, classifier
├── tool.py                     # Tool definitions — Gmail, Calendar, GetTime, history tools
├── llm.py                      # Qwen/DashScope LLM setup
├── gmail_api.py                # Gmail API wrapper
├── calendar_api.py             # Google Calendar API wrapper
├── generic_tools.py            # GetTime and utility tools
├── ui/
│   └── main.py                 # Streamlit UI
├── docs/
│   ├── architecture.png        # System architecture diagram
│   └── alibaba_cloud_proof.md  # Alibaba Cloud deployment proof
├── requirements.txt
└── README.md
```

---

## Setup Instructions

### Prerequisites

- Python 3.9 or higher
- Google Cloud Platform account (for Gmail and Calendar APIs)
- Alibaba Cloud account (for Qwen API via DashScope)

### Installation

**1. Clone the repository**

```bash
git clone https://github.com/vyomya/PAAI.git
cd PAAI
```

**2. Create and activate a virtual environment**

```bash
python -m venv venv
source venv/bin/activate       # macOS / Linux
# venv\Scripts\activate        # Windows
```

**3. Install dependencies**

```bash
pip install -r requirements.txt
```

---

### Configuration

#### Alibaba Cloud — Qwen API (DashScope)

1. Sign up at [alibabacloud.com](https://alibabacloud.com) (international) or [bailian.aliyun.com](https://bailian.aliyun.com) (China)
2. Navigate to **Model Studio** and click **Activate** — this enables your free tier (70M tokens for new users)
3. Go to **API Keys** → **Create API Key** → copy the key
4. Create a file named `qwenkey.txt` in the project root:

```text
sk-your-dashscope-key-here
```

> **Regional note:** Use the international endpoint if your account was created on alibabacloud.com. China-registered accounts use a different endpoint — see `llm.py`.

#### Gmail API

1. Go to [Google Cloud Console](https://console.cloud.google.com) and enable the **Gmail API** and **Google Calendar API**
2. Create OAuth 2.0 credentials (Desktop app)
3. Download and place the following files in the project root:
   - `credentials.json` — downloaded from Google Cloud Console
   - `token.json` — auto-generated on first run after OAuth login

---

## Running the Application

**1. Start the FastAPI backend**

```bash
python api.py
```

**2. Launch the Streamlit interface** (in a separate terminal)

```bash
streamlit run ui/main.py
```

The interface will open in your browser automatically.

---

## How It Works

```
User message
     ↓
LLM Classifier  →  preference · task · correction
     ↓
Preference agent (if preference detected)
     ↓
Planner  →  generates step-by-step execution plan using qwen-plus
     ↓
Specialized agents  →  Summarizer · Priority · Email · Calendar · History
     ↓
Step evaluator  →  validates each step's output against its specific goal
     ↓
Final evaluator + passive preference extractor
     ↓
ChromaDB (messages) + SQLite (preferences, sessions)
```

### Agents

| Agent | Responsibility |
|---|---|
| `summarizer_agent` | Fetches and summarizes emails from Gmail |
| `priority_agent` | Builds a prioritized todo list from summaries |
| `email_agent` | Drafts and sends emails |
| `calendar_agent` | Fetches and creates Google Calendar events |
| `history_agent` | Retrieves relevant past conversation context |
| `preference_agent` | Extracts and saves user preferences |

### Memory

| Layer | Storage | Purpose |
|---|---|---|
| Message history | ChromaDB | Semantic retrieval of past conversations |
| Preferences | SQLite | Confidence-scored, scoped, decaying rules per agent |
| Sessions | SQLite | Input/output/plan summary per run |

---

## Qwen / Alibaba Cloud Integration

The LLM is configured in `llm.py` using LangChain's `ChatOpenAI` with DashScope's OpenAI-compatible endpoint:

```python
from langchain_openai import ChatOpenAI

llm = ChatOpenAI(
    api_key=api_key,                          # from qwenkey.txt
    base_url="https://dashscope-intl.aliyuncs.com/compatible-mode/v1",
    model="qwen-plus",
    temperature=0,
    max_retries=2,
)
```

No additional packages are required beyond `langchain-openai`. Tool calling, streaming, and JSON mode all work identically to OpenAI's API — only the `base_url`, `api_key`, and `model` change.

For full Alibaba Cloud deployment proof, see [`docs/alibaba_cloud_proof.md`](docs/alibaba_cloud_proof.md).

---

## Contributing

Contributions are welcome. Areas of interest:

- Additional agent types (web search, file management, task databases)
- Skills system — saved named workflows triggered by phrase
- User authentication and multi-user support
- Performance optimization and latency reduction
- Testing and evaluation framework

Please open an issue before starting work on new features.

---

## License

This project is licensed under the MIT License — see the [LICENSE](LICENSE) file for details.

---

## Contact

For questions, collaboration, or technical discussion, open an issue or reach out via GitHub.

**Repository:** [https://github.com/vyomya/PAAI](https://github.com/vyomya/PAAI)
