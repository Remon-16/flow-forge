"""Data models for the test case generation pipeline."""

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional


@dataclass
class InterfaceDef:
    """Parsed API interface definition from OpenAPI/Markdown docs."""

    test_id: str
    api_name: str
    app_name: str = ""
    method: str = "GET"
    url: str = ""
    request_head: Dict[str, Any] = field(default_factory=dict)
    request_body: Dict[str, Any] = field(default_factory=dict)
    status_code: int = 200
    assert_dict: Dict[str, Any] = field(default_factory=dict)
    assert_rules: List[str] = field(default_factory=list)
    preprocessors: List[Dict[str, Any]] = field(default_factory=list)
    postprocessors: List[Dict[str, Any]] = field(default_factory=list)
    remark: str = ""


@dataclass
class SingleTestCase:
    """A single-API test case, linked to an InterfaceDef via relevance_id."""

    test_id: str
    relevance_id: str
    tag: str = "P1"
    api_name: str = ""
    app_name: str = ""
    method: str = "GET"
    url: str = ""
    request_head: Dict[str, Any] = field(default_factory=dict)
    request_body: Dict[str, Any] = field(default_factory=dict)
    status_code: int = 200
    assert_dict: Dict[str, Any] = field(default_factory=dict)
    assert_rules: List[str] = field(default_factory=list)
    preprocessors: List[Dict[str, Any]] = field(default_factory=list)
    postprocessors: List[Dict[str, Any]] = field(default_factory=list)
    remark: str = ""


@dataclass
class BizStep:
    """A single step within a business flow test case."""

    step_id: str
    relevance_id: str
    trans: str = ""
    api_name: str = ""
    app_name: str = ""
    method: str = "GET"
    url: str = ""
    request_head: Dict[str, Any] = field(default_factory=dict)
    request_body: Dict[str, Any] = field(default_factory=dict)
    status_code: int = 200
    assert_dict: Dict[str, Any] = field(default_factory=dict)
    assert_rules: List[str] = field(default_factory=list)
    preprocessors: List[Dict[str, Any]] = field(default_factory=list)
    postprocessors: List[Dict[str, Any]] = field(default_factory=list)
    tag: str = "P1"
    remark: str = ""


@dataclass
class BizFlow:
    """A multi-step business flow test case (one Excel sheet)."""

    sheet_name: str
    steps: List[BizStep] = field(default_factory=list)


@dataclass
class PlanStep:
    """A test point description within a test plan."""

    test_id: str
    description: str
    tag: str = "P1"
    scenario_type: str = "positive"  # positive, negative, boundary, business


@dataclass
class TestPlan:
    """Structured test plan generated from requirements + API docs."""

    business_summary: str = ""
    api_definitions: List[InterfaceDef] = field(default_factory=list)
    single_test_points: Dict[str, List[PlanStep]] = field(default_factory=dict)
    mermaid_flows: Dict[str, str] = field(default_factory=dict)
    biz_flow_scenarios: List[Dict[str, Any]] = field(default_factory=list)
