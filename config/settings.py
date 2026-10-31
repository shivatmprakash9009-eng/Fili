"""Settings management for the Multi-Agent System."""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path


@dataclass
class LLMSettings:
    """LLM provider configuration."""
    provider: str = "groq"  # "groq", "openai", "grok", or "gemini"
    api_key: str = ""
    model: str = "openai/gpt-oss-120b"
    base_url: str = ""
    temperature: float = 0.7
    max_tokens: int = 2000
    timeout: int = 30


@dataclass
class EmailSettings:
    """SMTP email configuration."""
    smtp_host: str = "smtp.gmail.com"
    smtp_port: int = 587
    username: str = ""
    password: str = ""
    from_email: str = ""


@dataclass
class AgentSettings:
    """Agent behavior configuration."""
    max_retries: int = 3
    retry_delay: float = 1.0
    timeout: int = 60
    heartbeat_interval: int = 30


@dataclass
class CampaignSettings:
    """Campaign configuration."""
    daily_email_limit: int = 50
    follow_up_delay_days: int = 3
    max_follow_ups: int = 3
    default_sender_name: str = "Your Name"


@dataclass
class LoggingSettings:
    """Logging configuration."""
    log_level: str = "INFO"
    log_file: str = "logs/agent.log"
    log_format: str = "%(asctime)s [%(name)s] %(levelname)s: %(message)s"


@dataclass
class Settings:
    """Main settings container — loads from environment variables."""
    llm: LLMSettings = field(default_factory=LLMSettings)
    email: EmailSettings = field(default_factory=EmailSettings)
    agent: AgentSettings = field(default_factory=AgentSettings)
    campaign: CampaignSettings = field(default_factory=CampaignSettings)
    logging: LoggingSettings = field(default_factory=LoggingSettings)
    apollo_api_key: str = ""
    serpapi_api_key: str = ""

    @classmethod
    def from_env(cls, env_file: str | None = None) -> Settings:
        """Load settings from environment variables and optional .env file.

        Args:
            env_file: Path to .env file. If None, tries '.env' in cwd.
        """
        # Load .env file if exists
        env_path = Path(env_file) if env_file else Path(".env")
        if env_path.exists():
            _load_env_file(env_path)

        provider = os.getenv("LLM_PROVIDER", "groq").lower()
        if provider == "groq":
            default_model = "openai/gpt-oss-120b"
        elif provider in ["grok", "xai"]:
            default_model = "grok-2-latest"
        elif provider == "openai":
            default_model = "gpt-4o-mini"
        else:
            default_model = "gemini-2.0-flash"

        api_key = (
            os.getenv("GROQ_API_KEY")
            or os.getenv("LLM_API_KEY")
            or os.getenv("XAI_API_KEY")
            or os.getenv("GROK_API_KEY", "")
        )

        return cls(
            llm=LLMSettings(
                provider=provider,
                api_key=api_key,
                model=os.getenv("LLM_MODEL", default_model),
                base_url=os.getenv("LLM_BASE_URL", ""),
                temperature=float(os.getenv("LLM_TEMPERATURE", "0.7")),
                max_tokens=int(os.getenv("LLM_MAX_TOKENS", "2000")),
                timeout=int(os.getenv("LLM_TIMEOUT", "30")),
            ),
            email=EmailSettings(
                smtp_host=os.getenv("SMTP_HOST", "smtp.gmail.com"),
                smtp_port=int(os.getenv("SMTP_PORT", "587")),
                username=os.getenv("SMTP_USERNAME", ""),
                password=os.getenv("SMTP_PASSWORD", ""),
                from_email=os.getenv("FROM_EMAIL", ""),
            ),
            agent=AgentSettings(
                max_retries=int(os.getenv("AGENT_MAX_RETRIES", "3")),
                retry_delay=float(os.getenv("AGENT_RETRY_DELAY", "1.0")),
                timeout=int(os.getenv("AGENT_TIMEOUT", "60")),
                heartbeat_interval=int(os.getenv("AGENT_HEARTBEAT", "30")),
            ),
            campaign=CampaignSettings(
                daily_email_limit=int(os.getenv("DAILY_EMAIL_LIMIT", "50")),
                follow_up_delay_days=int(os.getenv("FOLLOW_UP_DELAY", "3")),
                max_follow_ups=int(os.getenv("MAX_FOLLOW_UPS", "3")),
                default_sender_name=os.getenv("SENDER_NAME", "Your Name"),
            ),
            logging=LoggingSettings(
                log_level=os.getenv("LOG_LEVEL", "INFO"),
                log_file=os.getenv("LOG_FILE", "logs/agent.log"),
            ),
            apollo_api_key=os.getenv("APOLLO_API_KEY", ""),
            serpapi_api_key=os.getenv("SERPAPI_API_KEY", ""),
        )

    def validate(self) -> list[str]:
        """Validate settings and return list of warnings."""
        warnings: list[str] = []
        if not self.llm.api_key:
            warnings.append("LLM_API_KEY not set — agents will use mock/template fallbacks")
        if not self.email.username:
            warnings.append("SMTP_USERNAME not set — email sending will be in dry-run mode")
        if not self.email.from_email:
            warnings.append("FROM_EMAIL not set")
        return warnings


def _load_env_file(path: Path) -> None:
    """Parse a .env file and set environment variables."""
    try:
        with open(path) as f:
            for line in f:
                line = line.strip()
                if not line or line.startswith("#"):
                    continue
                if "=" not in line:
                    continue
                key, _, value = line.partition("=")
                key = key.strip()
                value = value.strip().strip("\"'")
                if key and not os.getenv(key):  # Don't override existing env vars
                    os.environ[key] = value
    except OSError:
        pass
