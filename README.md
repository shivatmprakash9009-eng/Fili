# 🚀 Multi-Agent Lead Generation & Outreach System

An advanced **multi-agent AI system** built in Python for automated B2B lead generation, personalized outreach, and campaign management. Powered by OpenAI/Google Gemini APIs with intelligent fallbacks.

## 🏗️ Architecture

```
┌─────────────────────────────────────────────────────────┐
│                    ORCHESTRATOR                          │
│  ┌─────────────────────────────────────────────────┐    │
│  │              Message Bus (Pub/Sub)               │    │
│  └──────┬──────┬──────┬──────┬──────┬──────────────┘    │
│         │      │      │      │      │                    │
│    ┌────▼─┐ ┌──▼───┐ ┌▼────┐ ┌▼────┐ ┌▼────────┐       │
│    │Lead  │ │Content│ │Email│ │Resp.│ │Reporting│       │
│    │Rsrch │ │Writer │ │Send │ │Anlyz│ │Agent    │       │
│    └──────┘ └──────┘ └─────┘ └─────┘ └─────────┘       │
│                                                          │
│  ┌────────────────────────────────────────────────┐      │
│  │  Pipeline Engine (Sequential & Parallel)        │      │
│  │  Task Queue (Priority-Based)                    │      │
│  │  Agent Registry (Capability Discovery)          │      │
│  │  Error Recovery (Retry + Backoff)               │      │
│  └────────────────────────────────────────────────┘      │
└─────────────────────────────────────────────────────────┘
```

## ✨ Features

- **🤖 6 Specialized Agents** — Each with distinct capabilities
- **🔄 Orchestrator** — Central coordination with capability-based routing
- **📨 Message Bus** — Pub/Sub inter-agent communication
- **📋 Pipeline Engine** — Sequential & parallel workflow execution
- **🧠 AI-Powered** — OpenAI & Gemini API integration with smart fallbacks
- **📧 Email Outreach** — SMTP sending with rate limiting & dry-run mode
- **📊 Analytics** — Campaign reporting with quality scores
- **🔁 Retry Logic** — Exponential backoff on all operations
- **⚙️ Configurable** — Environment variables & .env file support

## 📁 Project Structure

```
multi-agent-system/
├── main.py                  # Entry point & CLI
├── requirements.txt         # Dependencies
├── .env.example             # Configuration template
├── core/
│   ├── __init__.py
│   ├── base_agent.py        # Abstract base agent class
│   ├── orchestrator.py      # Central orchestrator
│   ├── message_bus.py       # Pub/Sub message system
│   └── task.py              # Task & TaskResult dataclasses
├── agents/
│   ├── __init__.py
│   ├── lead_researcher.py   # Finds & scores leads
│   ├── content_writer.py    # Generates outreach content
│   ├── email_outreach.py    # Sends emails with scheduling
│   ├── response_analyzer.py # Analyzes email responses
│   └── reporting.py         # Campaign analytics & reports
├── config/
│   ├── __init__.py
│   └── settings.py          # Settings management
├── utils/
│   ├── __init__.py
│   ├── llm_client.py        # Unified LLM API client
│   └── helpers.py           # Utility functions
├── templates/               # Email/message templates
│   ├── cold_email.txt
│   ├── follow_up.txt
│   └── linkedin_message.txt
├── data/                    # Data storage
└── logs/                    # Log files
```

## 🚀 Quick Start

### 1. Install Dependencies

```bash
cd multi-agent-system
pip install -r requirements.txt
```

### 2. Configure (Optional)

```bash
cp .env.example .env
# Edit .env with your API keys
```

### 3. Run

```bash
# Basic run (dry-run mode, mock data)
python main.py

# Custom target
python main.py --target "SaaS companies" --location "USA" --max-leads 10

# With campaign name
python main.py --target "FinTech startups" --location "UK" --campaign-name "UK Q4"

# Autonomous Inbound Objection & Reply Handler Demo
python demo_autonomous_outreach.py

# Web UI Dashboard (Open http://localhost:8000 in your browser)
python dashboard.py --port 8000

# Run Automated Test Suite
python -m unittest discover tests -v
```

## ⚙️ Configuration

Set via environment variables or `.env` file:

| Variable | Default | Description |
|----------|---------|-------------|
| `LLM_PROVIDER` | `groq` | `groq` (ultra-fast LPU), `openai`, `grok`, or `gemini` |
| `GROQ_API_KEY` / `LLM_API_KEY` | — | Your Groq API key (`gsk_...`) |
| `LLM_MODEL` | `llama-3.3-70b-versatile` | `llama-3.3-70b-versatile`, `llama-3.1-8b-instant`, `mixtral-8x7b-32768` |
| `SMTP_HOST` | `smtp.gmail.com` | SMTP server |
| `SMTP_PORT` | `587` | SMTP port |
| `SMTP_USERNAME` | — | Email username |
| `SMTP_PASSWORD` | — | Email password/app password |
| `DAILY_EMAIL_LIMIT` | `50` | Max emails per day |
| `SENDER_NAME` | `Your Name` | Sender display name |

## 🤖 Agents

| Agent | Capabilities | Description |
|-------|-------------|-------------|
| **Lead Researcher** | `research_leads`, `enrich_lead`, `score_lead` | Finds companies, scores relevance |
| **Content Writer** | `generate_content`, `personalize_template`, `score_content` | Creates personalized outreach |
| **Email Outreach** | `send_emails`, `schedule_email`, `track_delivery` | Sends emails with rate limiting |
| **Response Analyzer** | `analyze_response`, `categorize_responses`, `extract_action_items` | Classifies replies, suggests actions |
| **Reporting** | `generate_report`, `collect_metrics`, `campaign_summary` | Campaign analytics & reports |

## 🔄 Default Pipeline

```
Research Leads → Generate Content → Send Emails → Generate Report
```

Each step passes its results to the next automatically.

## 📜 License

MIT License — free to use, modify, and distribute.
