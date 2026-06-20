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
    llm_context_window: int = 128000
    llm_context_compression_threshold: float = 0.9
    llm_max_output_tokens: int = 4096
    enable_knowledge: bool = False
    knowledge_dir: str = "./knowledge"
    llm_doc_max_chars: int = 30000
    max_steps: int = 10
    max_retries: int = 3
    llm_rate_limit_delay: float = 0.0  # Min seconds between LLM calls (0 = no limit)
    llm_retry_base_delay: float = 2.0  # Base seconds for exponential backoff
    output_dir: str = "./output"  # Root output directory (CLI appends timestamp by default)
    batch_size: int = 10
    enable_validation: bool = True
    max_validation_retries: int = 3
    output_format: str = "both"
    max_steps_no_progress: int = 5
    url_correction_max_retries: int = 3
    enable_plugins: bool = False
    plugin_modules: str = ""  # comma-separated module paths, executed in order
    llm_max_concurrency: int = 1  # max simultaneous LLM requests (0=unlimited, GLM free tier requires 1)
    consecutive_batch_failure_limit: int = 3  # stop after N consecutive batch failures (-1=never stop)
    llm_request_timeout: float = 600.0  # HTTP request timeout in seconds (connect + read)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "llm_provider": self.llm_provider,
            "llm_api_key": "***",
            "llm_base_url": self.llm_base_url,
            "llm_model": self.llm_model,
            "llm_temperature": self.llm_temperature,
            "llm_max_tokens": self.llm_max_tokens,
            "llm_context_window": self.llm_context_window,
            "llm_context_compression_threshold": self.llm_context_compression_threshold,
            "llm_max_output_tokens": self.llm_max_output_tokens,
            "enable_knowledge": self.enable_knowledge,
            "knowledge_dir": self.knowledge_dir,
            "llm_doc_max_chars": self.llm_doc_max_chars,
            "max_steps": self.max_steps,
            "max_retries": self.max_retries,
            "llm_rate_limit_delay": self.llm_rate_limit_delay,
            "llm_retry_base_delay": self.llm_retry_base_delay,
            "output_dir": self.output_dir,
            "batch_size": self.batch_size,
            "enable_validation": self.enable_validation,
            "max_validation_retries": self.max_validation_retries,
            "output_format": self.output_format,
            "max_steps_no_progress": self.max_steps_no_progress,
            "url_correction_max_retries": self.url_correction_max_retries,
            "enable_plugins": self.enable_plugins,
            "plugin_modules": self.plugin_modules,
            "llm_max_concurrency": self.llm_max_concurrency,
            "consecutive_batch_failure_limit": self.consecutive_batch_failure_limit,
            "llm_request_timeout": self.llm_request_timeout,
        }


def load_settings(dotenv_path: str = ".env") -> Settings:
    """Load settings from .env file, falling back to defaults."""
    load_dotenv(dotenv_path, override=False)

    temperature = float(os.getenv("LLM_TEMPERATURE", "0.3"))
    max_tokens = int(os.getenv("LLM_MAX_OUTPUT_TOKENS",
                    os.getenv("LLM_MAX_TOKENS", "4096")))
    context_window = int(os.getenv("LLM_CONTEXT_WINDOW", "128000"))
    compression_threshold = float(
        os.getenv("LLM_CONTEXT_COMPRESSION_THRESHOLD", "0.9")
    )
    max_output_tokens = int(os.getenv("LLM_MAX_OUTPUT_TOKENS",
                           os.getenv("LLM_MAX_TOKENS", "4096")))
    max_steps = int(os.getenv("MAX_STEPS", "10"))
    max_retries = int(os.getenv("MAX_RETRIES", "3"))
    llm_rate_limit_delay = float(os.getenv("LLM_RATE_LIMIT_DELAY", "0.0"))
    llm_retry_base_delay = float(os.getenv("LLM_RETRY_BASE_DELAY", "2.0"))
    enable_knowledge = os.getenv("ENABLE_KNOWLEDGE", "false").strip().lower() in (
        "true", "1", "yes", "on"
    )
    llm_doc_max_chars = int(os.getenv("LLM_DOC_MAX_CHARS", "30000"))
    enable_validation = os.getenv("ENABLE_VALIDATION", "true").strip().lower() in (
        "true", "1", "yes", "on"
    )
    batch_size = int(os.getenv("BATCH_SIZE", "10"))
    max_validation_retries = int(os.getenv("MAX_VALIDATION_RETRIES", "3"))
    max_steps_no_progress = int(os.getenv("MAX_STEPS_NO_PROGRESS", "5"))
    url_correction_max_retries = int(os.getenv("URL_CORRECTION_MAX_RETRIES", "3"))
    enable_plugins = os.getenv("ENABLE_PLUGINS", "false").strip().lower() in (
        "true", "1", "yes", "on"
    )
    plugin_modules = os.getenv("PLUGIN_MODULES", "")
    llm_max_concurrency = int(os.getenv("LLM_MAX_CONCURRENCY", "1"))
    consecutive_batch_failure_limit = int(os.getenv("CONSECUTIVE_BATCH_FAILURE_LIMIT", "3"))
    llm_request_timeout = float(os.getenv("LLM_REQUEST_TIMEOUT", "600.0"))

    return Settings(
        llm_provider=os.getenv("LLM_PROVIDER", "openai"),
        llm_api_key=os.getenv("LLM_API_KEY", ""),
        llm_base_url=os.getenv("LLM_BASE_URL", ""),
        llm_model=os.getenv("LLM_MODEL", "gpt-4o"),
        llm_temperature=temperature,
        llm_max_tokens=max_tokens,
        llm_context_window=context_window,
        llm_context_compression_threshold=compression_threshold,
        llm_max_output_tokens=max_output_tokens,
        enable_knowledge=enable_knowledge,
        knowledge_dir=os.getenv("KNOWLEDGE_DIR", "./knowledge"),
        llm_doc_max_chars=llm_doc_max_chars,
        max_steps=max_steps,
        max_retries=max_retries,
        llm_rate_limit_delay=llm_rate_limit_delay,
        llm_retry_base_delay=llm_retry_base_delay,
        output_dir=os.getenv("OUTPUT_DIR", "./output"),
        batch_size=batch_size,
        enable_validation=enable_validation,
        max_validation_retries=max_validation_retries,
        output_format=os.getenv("OUTPUT_FORMAT", "both"),
        max_steps_no_progress=max_steps_no_progress,
        url_correction_max_retries=url_correction_max_retries,
        enable_plugins=enable_plugins,
        plugin_modules=plugin_modules,
        llm_max_concurrency=llm_max_concurrency,
        consecutive_batch_failure_limit=consecutive_batch_failure_limit,
        llm_request_timeout=llm_request_timeout,
    )
