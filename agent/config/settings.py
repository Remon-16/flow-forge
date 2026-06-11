"""Load configuration from .env and provide defaults."""

import os
from dataclasses import dataclass, field
from typing import Any, Dict

from dotenv import load_dotenv


@dataclass
class Settings:
    llm_provider: str = "openai"
    llm_api_key: str = ""
    llm_base_url: str = ""
    llm_model: str = "gpt-4o"
    llm_temperature: float = 0.3
    llm_max_tokens: int = 4096
    enable_knowledge: bool = False
    knowledge_dir: str = "./knowledge"
    llm_doc_max_chars: int = 30000
    max_steps: int = 10
    max_retries: int = 3
    output_dir: str = "./output"
    batch_size: int = 10
    enable_validation: bool = True
    max_validation_retries: int = 3
    output_format: str = "both"

    def to_dict(self) -> Dict[str, Any]:
        return {
            "llm_provider": self.llm_provider,
            "llm_api_key": "***",
            "llm_base_url": self.llm_base_url,
            "llm_model": self.llm_model,
            "llm_temperature": self.llm_temperature,
            "llm_max_tokens": self.llm_max_tokens,
            "enable_knowledge": self.enable_knowledge,
            "knowledge_dir": self.knowledge_dir,
            "llm_doc_max_chars": self.llm_doc_max_chars,
            "max_steps": self.max_steps,
            "max_retries": self.max_retries,
            "output_dir": self.output_dir,
            "batch_size": self.batch_size,
            "enable_validation": self.enable_validation,
            "max_validation_retries": self.max_validation_retries,
            "output_format": self.output_format,
        }


def load_settings(dotenv_path: str = ".env") -> Settings:
    """Load settings from .env file, falling back to defaults."""
    load_dotenv(dotenv_path, override=False)

    temperature = float(os.getenv("LLM_TEMPERATURE", "0.3"))
    max_tokens = int(os.getenv("LLM_MAX_TOKENS", "4096"))
    max_steps = int(os.getenv("MAX_STEPS", "10"))
    max_retries = int(os.getenv("MAX_RETRIES", "3"))
    enable_knowledge = os.getenv("ENABLE_KNOWLEDGE", "false").strip().lower() in (
        "true", "1", "yes", "on"
    )
    llm_doc_max_chars = int(os.getenv("LLM_DOC_MAX_CHARS", "30000"))
    enable_validation = os.getenv("ENABLE_VALIDATION", "true").strip().lower() in (
        "true", "1", "yes", "on"
    )
    batch_size = int(os.getenv("BATCH_SIZE", "10"))
    max_validation_retries = int(os.getenv("MAX_VALIDATION_RETRIES", "3"))

    return Settings(
        llm_provider=os.getenv("LLM_PROVIDER", "openai"),
        llm_api_key=os.getenv("LLM_API_KEY", ""),
        llm_base_url=os.getenv("LLM_BASE_URL", ""),
        llm_model=os.getenv("LLM_MODEL", "gpt-4o"),
        llm_temperature=temperature,
        llm_max_tokens=max_tokens,
        enable_knowledge=enable_knowledge,
        knowledge_dir=os.getenv("KNOWLEDGE_DIR", "./knowledge"),
        llm_doc_max_chars=llm_doc_max_chars,
        max_steps=max_steps,
        max_retries=max_retries,
        output_dir=os.getenv("OUTPUT_DIR", "./output"),
        batch_size=batch_size,
        enable_validation=enable_validation,
        max_validation_retries=max_validation_retries,
        output_format=os.getenv("OUTPUT_FORMAT", "both"),
    )
