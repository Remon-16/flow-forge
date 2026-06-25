"""提示词统一导出。

Unified prompt exports — all agent prompts in one namespace.
"""

from .render import render_prompt

# Shared constants
KNOWLEDGE_SECTION_HEADER = "## Knowledge Base Reference\n"

# API analysis
from .api_analyzer import (
    API_ANALYSIS_REVISE_SYSTEM,
    API_ANALYSIS_REVISE_USER,
    API_ANALYSIS_SYSTEM,
    API_ANALYSIS_USER,
    RAW_API_ANALYSIS_SYSTEM,
    RAW_API_ANALYSIS_USER,
    RAW_API_CHUNK_NOTICE,
)

# Requirement analysis
from .requirement_analysis import (
    REQ_CHUNK_NOTICE,
    REQUIREMENT_ANALYSIS_SYSTEM,
    REQUIREMENT_ANALYSIS_USER,
)

# Plan generation
from .plan_generation import (
    PLAN_GENERATION_SYSTEM,
    PLAN_GENERATION_USER,
    REFERENCE_DIR_EMPTY,
    REFERENCE_DIR_GUIDANCE,
    REFERENCE_DIR_UNREADABLE,
    REF_SECTION_EXISTING_BIZ_FLOWS,
    REF_SECTION_EXISTING_INTERFACES,
    REF_SECTION_EXISTING_PLAN,
    REF_SECTION_EXISTING_SINGLE_CASES,
)

# Plan parsing
from .plan_parser import (
    PLAN_CHUNK_NOTICE,
    PLAN_PARSER_SYSTEM,
    PLAN_PARSER_USER,
)

# Plan revision
from .plan_reviser import (
    PLAN_ANNOTATION_REVISER_SYSTEM,
    PLAN_ANNOTATION_REVISER_USER,
    PLAN_REVISER_SYSTEM,
    PLAN_REVISER_USER,
)

# Case generation (legacy)
from .case_generation import (
    CASE_GENERATION_SYSTEM,
    CASE_GENERATION_USER,
    VALIDATION_ERROR_FOOTER,
    VALIDATION_ERROR_HEADER,
)

# Skeleton generation
from .skeleton_generation import (
    BIZ_SKELETON_SYSTEM,
    BIZ_SKELETON_USER,
    SINGLE_SKELETON_SYSTEM,
    SINGLE_SKELETON_USER,
    URL_CORRECTION_SYSTEM,
    URL_CORRECTION_USER,
)

# URL correction (additional interface-level variant)
from .url_correction import (
    IFACE_URL_CORRECTION_SYSTEM,
    IFACE_URL_CORRECTION_USER,
)


# Doc parser
from .doc_parser import (
    DOC_CHUNK_NOTICE,
    DOC_DEFAULT_FILE_TYPE_HINT,
    DOC_PARSER_SYSTEM,
    DOC_PARSER_USER,
)

# Compression & system prompts
from .compression import COMPRESSION_SYSTEM, DEFAULT_CHUNK_NOTICE
from .json_fix import JSON_FIX_PROMPT

__all__ = [
    "render_prompt",
    "KNOWLEDGE_SECTION_HEADER",
    # API analysis
    "API_ANALYSIS_SYSTEM",
    "API_ANALYSIS_USER",
    "RAW_API_ANALYSIS_SYSTEM",
    "RAW_API_ANALYSIS_USER",
    "RAW_API_CHUNK_NOTICE",
    "API_ANALYSIS_REVISE_SYSTEM",
    "API_ANALYSIS_REVISE_USER",
    # Requirement analysis
    "REQUIREMENT_ANALYSIS_SYSTEM",
    "REQUIREMENT_ANALYSIS_USER",
    "REQ_CHUNK_NOTICE",
    # Plan generation
    "PLAN_GENERATION_SYSTEM",
    "PLAN_GENERATION_USER",
    "REFERENCE_DIR_EMPTY",
    "REFERENCE_DIR_GUIDANCE",
    "REFERENCE_DIR_UNREADABLE",
    "REF_SECTION_EXISTING_BIZ_FLOWS",
    "REF_SECTION_EXISTING_INTERFACES",
    "REF_SECTION_EXISTING_PLAN",
    "REF_SECTION_EXISTING_SINGLE_CASES",
    # Plan parsing
    "PLAN_CHUNK_NOTICE",
    "PLAN_PARSER_SYSTEM",
    "PLAN_PARSER_USER",
    # Plan revision
    "PLAN_REVISER_SYSTEM",
    "PLAN_REVISER_USER",
    "PLAN_ANNOTATION_REVISER_SYSTEM",
    "PLAN_ANNOTATION_REVISER_USER",
    # Case generation
    "CASE_GENERATION_SYSTEM",
    "CASE_GENERATION_USER",
    "VALIDATION_ERROR_FOOTER",
    "VALIDATION_ERROR_HEADER",
    # Skeleton generation
    "SINGLE_SKELETON_SYSTEM",
    "SINGLE_SKELETON_USER",
    "BIZ_SKELETON_SYSTEM",
    "BIZ_SKELETON_USER",
    "URL_CORRECTION_SYSTEM",
    "URL_CORRECTION_USER",
    # URL correction (additional)
    "IFACE_URL_CORRECTION_SYSTEM",
    "IFACE_URL_CORRECTION_USER",

    # Doc parser
    "DOC_CHUNK_NOTICE",
    "DOC_DEFAULT_FILE_TYPE_HINT",
    "DOC_PARSER_SYSTEM",
    "DOC_PARSER_USER",
    # Compression & system
    "COMPRESSION_SYSTEM",
    "DEFAULT_CHUNK_NOTICE",
    "JSON_FIX_PROMPT",
]
