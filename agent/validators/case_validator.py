"""CaseValidator: validates generated test case format and retries on failure."""

import json
import logging
import re
from typing import Any, Dict, List, Optional, Tuple

from agents.base import BaseAgent
from config.settings import Settings

logger = logging.getLogger(__name__)


def _get_field(obj, field, default=None):
    """Get a field value from a dict or a dataclass/object."""
    if isinstance(obj, dict):
        return obj.get(field, default)
    return getattr(obj, field, default)


_VAR_REF_RE = re.compile(r"#\{([^}]+)\}")

from flow_forge_schemas import (
    REQUIRED_SINGLE as _REQUIRED_SINGLE,
    REQUIRED_BIZ_STEP as _REQUIRED_BIZ_STEP,
    REQUIRED_BIZ_FLOW as _REQUIRED_BIZ_FLOW,
    VALID_HTTP_METHODS as _VALID_HTTP_METHODS,
    VALID_TAGS as _VALID_TAGS,
)


class CaseValidator(BaseAgent):
    """Validate generated test cases for structural correctness.

    Checks required fields, types, JSON path syntax, and #{var} references.
    Can retry failed cases by submitting them back to the case generator.
    """

    def __init__(self, settings: Settings):
        super().__init__(
            api_key=settings.llm_api_key,
            model=settings.llm_model,
            temperature=0.1,
            max_retries=settings.max_retries,
            max_steps=settings.max_steps,
            base_url=settings.llm_base_url,
        )

    def validate(
        self, cases: List[Dict], schema_type: str
    ) -> Tuple[List[Dict], List[Dict], List[str]]:
        """Validate a batch of cases.

        Returns (valid_cases, invalid_cases, error_messages).
        """
        valid = []
        invalid = []
        errors = []

        for i, case in enumerate(cases):
            case_errors = self._validate_one(case, schema_type)
            if case_errors:
                invalid.append(case)
                errors.append(
                    f"Case[{i}] {_get_field(case, 'test_id') or _get_field(case, 'sheet_name', 'unknown')}: "
                    + "; ".join(case_errors)
                )
            else:
                valid.append(case)

        return valid, invalid, errors

    def _validate_one(self, case: Dict, schema_type: str) -> List[str]:
        errors = []

        if schema_type == "single":
            errors.extend(self._check_required(case, _REQUIRED_SINGLE))
            errors.extend(self._check_method(case))
            errors.extend(self._check_tag(case))
            errors.extend(self._check_url(case))
            errors.extend(self._check_status_code(case))
            errors.extend(self._check_json_field(case, "request_head"))
            errors.extend(self._check_json_field(case, "request_body"))
            errors.extend(self._check_assert_dict(case))
            errors.extend(self._check_assert_rules(case))
        elif schema_type == "biz_flow":
            errors.extend(self._check_required(case, _REQUIRED_BIZ_FLOW))
            steps = _get_field(case, "steps", [])
            if not isinstance(steps, list) or len(steps) == 0:
                errors.append("steps must be a non-empty list")
            else:
                for si, step in enumerate(steps):
                    step_errors = self._validate_one_biz_step(step, si)
                    errors.extend(step_errors)
                    step_inherit = str(_get_field(step, "inherit", ""))
                    if step_inherit:
                        errors.extend(self._check_inherit_refs(step_inherit, steps))

        return errors

    def _validate_one_biz_step(self, step: Dict, idx: int) -> List[str]:
        errors = []
        prefix = f"steps[{idx}]"
        errors.extend(
            [f"{prefix}.{e}" for e in self._check_required(step, _REQUIRED_BIZ_STEP)]
        )
        errors.extend([f"{prefix}.{e}" for e in self._check_method(step)])
        errors.extend([f"{prefix}.{e}" for e in self._check_tag(step)])
        errors.extend([f"{prefix}.{e}" for e in self._check_url(step)])
        errors.extend([f"{prefix}.{e}" for e in self._check_status_code(step)])
        errors.extend(
            [f"{prefix}.{e}" for e in self._check_json_field(step, "request_head")]
        )
        errors.extend(
            [f"{prefix}.{e}" for e in self._check_json_field(step, "request_body")]
        )
        errors.extend([f"{prefix}.{e}" for e in self._check_assert_dict(step)])
        errors.extend([f"{prefix}.{e}" for e in self._check_assert_rules(step)])
        return errors

    @staticmethod
    def _check_required(case: Dict, required: List[str]) -> List[str]:
        errors = []
        for field in required:
            val = _get_field(case, field)
            if val is None or (isinstance(val, str) and not val.strip()):
                errors.append(f"missing required field '{field}'")
        return errors

    @staticmethod
    def _check_method(case: Dict) -> List[str]:
        method = str(_get_field(case, "method", "")).upper()
        if method and method not in _VALID_HTTP_METHODS:
            return [f"invalid HTTP method '{method}'"]
        return []

    @staticmethod
    def _check_tag(case: Dict) -> List[str]:
        tag = str(_get_field(case, "tag", ""))
        if tag and tag not in _VALID_TAGS:
            return [f"invalid tag '{tag}' (expected P0-P3)"]
        return []

    @staticmethod
    def _check_url(case: Dict) -> List[str]:
        url = str(_get_field(case, "url", ""))
        if url and "\n" in url:
            return ["url contains newline"]
        return []

    @staticmethod
    def _check_status_code(case: Dict) -> List[str]:
        sc = _get_field(case, "status_code")
        if sc is not None:
            try:
                code = int(sc)
                if code < 100 or code > 599:
                    return [f"invalid status_code {code}"]
            except (ValueError, TypeError):
                return [f"status_code must be int, got {type(sc).__name__}"]
        return []

    @staticmethod
    def _check_json_field(case: Dict, field: str) -> List[str]:
        val = _get_field(case, field)
        if val is None:
            return []
        if isinstance(val, str):
            try:
                json.loads(val)
            except (json.JSONDecodeError, ValueError):
                return [f"'{field}' is not valid JSON"]
        elif not isinstance(val, dict):
            return [f"'{field}' must be dict or JSON string, got {type(val).__name__}"]
        return []

    @staticmethod
    def _check_assert_dict(case: Dict) -> List[str]:
        ad = _get_field(case, "assert_dict", {})
        if not ad:
            return []
        if isinstance(ad, str):
            try:
                ad = json.loads(ad)
            except (json.JSONDecodeError, ValueError):
                return ["assert_dict is not valid JSON"]
        if not isinstance(ad, dict):
            return [f"assert_dict must be dict, got {type(ad).__name__}"]
        return []

    @staticmethod
    def _check_assert_rules(case: Dict) -> List[str]:
        ar = _get_field(case, "assert_rules")
        if ar is None or (isinstance(ar, list) and len(ar) == 0):
            return []
        if isinstance(ar, str):
            try:
                ar = json.loads(ar)
            except (json.JSONDecodeError, ValueError):
                return ["assert_rules is not valid JSON"]
        if not isinstance(ar, list):
            return [f"assert_rules must be a list, got {type(ar).__name__}"]
        for i, item in enumerate(ar):
            if not isinstance(item, str):
                return [f"assert_rules[{i}] must be a string, got {type(item).__name__}"]
        return []

    @staticmethod
    def _check_inherit_refs(inherit, steps: List[Dict]) -> List[str]:
        errors = []
        step_ids = {str(_get_field(s, "step_id", "")) for s in steps}

        def _check_entry(key: str, value: str) -> None:
            if not value:
                errors.append(f"Inherit key '{key}' has empty value")
                return
            dot_idx = value.find(".")
            if dot_idx > 0:
                ref_step = value[:dot_idx]
                if ref_step not in step_ids:
                    errors.append(f"Inherit key '{key}' references unknown StepID '{ref_step}'")

        # 新格式：dict
        if isinstance(inherit, dict):
            for key, value in inherit.items():
                key = str(key).strip()
                value_str = str(value).strip() if value else ""
                _check_entry(key, value_str)
            return errors

        # 旧格式回退：逗号分隔字符串
        if isinstance(inherit, str) and inherit.strip():
            for pair in inherit.split(","):
                pair = pair.strip()
                if not pair or "=" not in pair:
                    continue
                key, value = pair.split("=", 1)
                key = key.strip()
                value = value.strip()
                _check_entry(key, value)

        return errors

    def validate_with_retry(
        self,
        case_generator: Any,
        invalid_cases: List[Dict],
        interfaces: List[Dict],
        test_points: List[Dict],
        batch_type: str,
        max_retries: int = 3,
    ) -> Tuple[List[Dict], List[Dict], List[Dict]]:
        """Retry invalid cases up to max_retries times.

        Returns (all_valid_cases, still_invalid_cases, retry_summary).
        retry_summary: [{"case_id": ..., "errors": [...], "retries": N}, ...]
        """
        all_valid: List[Dict] = []
        pending = list(invalid_cases)
        failure_log: Dict[str, Dict] = {}

        for retry in range(1, max_retries + 1):
            if not pending:
                break

            logger.info("Validation retry %d/%d for %d cases", retry, max_retries, len(pending))

            try:
                regenerated = case_generator.generate_batch(
                    interfaces=interfaces,
                    test_points=test_points,
                    batch_type=batch_type,
                    previous_errors=pending,
                )
            except Exception as e:
                logger.warning("Retry %d generation failed: %s", retry, e)
                for case in pending:
                    cid = _get_field(case, "test_id") or _get_field(case, "sheet_name", "unknown")
                    if cid not in failure_log:
                        failure_log[cid] = {"case": case, "errors": [str(e)], "retries": retry}
                break

            new_cases = regenerated if isinstance(regenerated, list) else regenerated.get("cases", [])
            if not new_cases:
                for case in pending:
                    cid = _get_field(case, "test_id") or _get_field(case, "sheet_name", "unknown")
                    if cid not in failure_log:
                        failure_log[cid] = {"case": case, "errors": ["regeneration returned empty"], "retries": retry}
                break

            valid, invalid, errors = self.validate(new_cases, batch_type)
            all_valid.extend(valid)

            next_pending = []
            for case, err in zip(invalid, errors):
                cid = _get_field(case, "test_id") or _get_field(case, "sheet_name", "unknown")
                if cid not in failure_log:
                    failure_log[cid] = {"case": case, "errors": [], "retries": 0}
                failure_log[cid]["errors"].append(err)
                failure_log[cid]["retries"] = retry
                if retry < max_retries:
                    next_pending.append(case)

            pending = next_pending

        still_invalid = []
        retry_summary = []
        for cid, info in failure_log.items():
            entry = {"case_id": cid, "errors": info["errors"], "retries": info["retries"]}
            retry_summary.append(entry)
            if info["retries"] >= max_retries:
                still_invalid.append(info["case"])

        return all_valid, still_invalid, retry_summary
