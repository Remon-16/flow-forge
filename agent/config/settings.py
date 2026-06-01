"""Load configuration from .env and provide defaults."""

import os
from dataclasses import dataclass, field
from typing import Any, Dict

from dotenv import load_dotenv


@dataclass
class Settings:
    llm_provider: str = "openai"
    llm_api_key: str = ""
    llm_model: str = "gpt-4o"
    llm_temperature: float = 0.3
    llm_max_tokens: int = 4096
    embedding_model: str = "text-embedding-3-small"
    knowledge_db_path: str = "./chroma_data"
    max_steps: int = 10
    max_retries: int = 3

    def to_dict(self) -> Dict[str, Any]:
        return {
            "llm_provider": self.llm_provider,
            "llm_api_key": "***",
            "llm_model": self.llm_model,
            "llm_temperature": self.llm_temperature,
            "llm_max_tokens": self.llm_max_tokens,
            "embedding_model": self.embedding_model,
            "knowledge_db_path": self.knowledge_db_path,
            "max_steps": self.max_steps,
            "max_retries": self.max_retries,
        }


def load_settings(dotenv_path: str = ".env") -> Settings:
    """Load settings from .env file, falling back to defaults."""
    load_dotenv(dotenv_path, override=False)

    temperature = float(os.getenv("LLM_TEMPERATURE", "0.3"))
    max_tokens = int(os.getenv("LLM_MAX_TOKENS", "4096"))
    max_steps = int(os.getenv("MAX_STEPS", "10"))
    max_retries = int(os.getenv("MAX_RETRIES", "3"))

    return Settings(
        llm_provider=os.getenv("LLM_PROVIDER", "openai"),
        llm_api_key=os.getenv("LLM_API_KEY", ""),
        llm_model=os.getenv("LLM_MODEL", "gpt-4o"),
        llm_temperature=temperature,
        llm_max_tokens=max_tokens,
        embedding_model=os.getenv("EMBEDDING_MODEL", "text-embedding-3-small"),
        knowledge_db_path=os.getenv("KNOWLEDGE_DB_PATH", "./chroma_data"),
        max_steps=max_steps,
        max_retries=max_retries,
    )
