"""提示词统一导出。

Unified prompt exports — all agent prompts in one namespace.
"""

from .render import render_prompt

# API analysis
from .api_analyzer import (
    API_ANALYSIS_REVISE_SYSTEM,
    API_ANALYSIS_REVISE_USER,
    API_ANALYSIS_SYSTEM,
    API_ANALYSIS_USER,
    RAW_API_ANALYSIS_SYSTEM,
    RAW_API_ANALYSIS_USER,
)

# Requirement analysis
from .requirement_analysis import (
    REQUIREMENT_ANALYSIS_SYSTEM,
    REQUIREMENT_ANALYSIS_USER,
)

# Plan generation
from .plan_generation import PLAN_GENERATION_SYSTEM, PLAN_GENERATION_USER

# Plan parsing
from .plan_parser import PLAN_PARSER_SYSTEM, PLAN_PARSER_USER

# Plan revision
from .plan_reviser import (
    PLAN_ANNOTATION_REVISER_SYSTEM,
    PLAN_ANNOTATION_REVISER_USER,
    PLAN_REVISER_SYSTEM,
    PLAN_REVISER_USER,
)

# Case generation (legacy)
from .case_generation import CASE_GENERATION_SYSTEM, CASE_GENERATION_USER

# Skeleton generation
from .skeleton_generation import (
    BIZ_SKELETON_SYSTEM,
    BIZ_SKELETON_USER,
    SINGLE_SKELETON_SYSTEM,
    SINGLE_SKELETON_USER,
    URL_CORRECTION_SYSTEM,
    URL_CORRECTION_USER,
)

# Data filling
from .data_filling import (
    BIZ_DATA_FILLING_SYSTEM,
    BIZ_DATA_FILLING_USER,
    SINGLE_DATA_FILLING_SYSTEM,
    SINGLE_DATA_FILLING_USER,
)

# Assertion generation
from .assertion_generation import (
    BIZ_ASSERTION_SYSTEM,
    BIZ_ASSERTION_USER,
    SINGLE_ASSERTION_SYSTEM,
    SINGLE_ASSERTION_USER,
)

# Doc parser
from .doc_parser import DOC_PARSER_SYSTEM, DOC_PARSER_USER

__all__ = [
    "render_prompt",
    # API analysis
    "API_ANALYSIS_SYSTEM",
    "API_ANALYSIS_USER",
    "RAW_API_ANALYSIS_SYSTEM",
    "RAW_API_ANALYSIS_USER",
    "API_ANALYSIS_REVISE_SYSTEM",
    "API_ANALYSIS_REVISE_USER",
    # Requirement analysis
    "REQUIREMENT_ANALYSIS_SYSTEM",
    "REQUIREMENT_ANALYSIS_USER",
    # Plan generation
    "PLAN_GENERATION_SYSTEM",
    "PLAN_GENERATION_USER",
    # Plan parsing
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
    # Skeleton generation
    "SINGLE_SKELETON_SYSTEM",
    "SINGLE_SKELETON_USER",
    "BIZ_SKELETON_SYSTEM",
    "BIZ_SKELETON_USER",
    "URL_CORRECTION_SYSTEM",
    "URL_CORRECTION_USER",
    # Data filling
    "SINGLE_DATA_FILLING_SYSTEM",
    "SINGLE_DATA_FILLING_USER",
    "BIZ_DATA_FILLING_SYSTEM",
    "BIZ_DATA_FILLING_USER",
    # Assertion generation
    "SINGLE_ASSERTION_SYSTEM",
    "SINGLE_ASSERTION_USER",
    "BIZ_ASSERTION_SYSTEM",
    "BIZ_ASSERTION_USER",
    # Doc parser
    "DOC_PARSER_SYSTEM",
    "DOC_PARSER_USER",
]
