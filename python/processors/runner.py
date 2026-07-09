"""Orchestrate pre/post processor execution for a test case."""

import logging
from typing import Any, Dict, List, Tuple

from processors.base import ProcessorError

logger = logging.getLogger(__name__)


def run_preprocessors(
    case: Dict[str, Any],
    global_config: Dict[str, Any],
) -> Tuple[Dict[str, Any], Dict[str, Any], List[Dict[str, Any]]]:
    """Execute all preprocessors declared on a test case.

    Args:
        case: The test case dict (must contain ``preprocessors`` list and
              ``request_head`` / ``request_body`` keys).
        global_config: Full merged env configuration.

    Returns:
        ``(modified_headers, modified_body, results)`` where *results* is a
        list of per-processor outcome dicts.

    Raises:
        ProcessorError: Immediately if any preprocessor fails.
    """
    from processors.base import _PRE_PROCESSOR_REGISTRY

    headers = dict(case.get("request_head") or {})
    body = dict(case.get("request_body") or {})
    processor_items = case.get("preprocessors") or []
    results: List[Dict[str, Any]] = []

    for item in processor_items:
        name = item.get("name", "")
        case_config = item.get("config") or {}

        processor_cls = _PRE_PROCESSOR_REGISTRY.get(name)
        if processor_cls is None:
            raise ProcessorError(
                f"PreProcessor '{name}' not found in registry. "
                f"Available: {list(_PRE_PROCESSOR_REGISTRY.keys())}",
                processor_name=name,
            )

        instance = processor_cls()
        if not instance.can_process(case):
            results.append({"name": name, "status": "skipped"})
            continue

        try:
            headers, body = instance.process(headers, body, case_config, global_config)
            results.append({"name": name, "status": "ok"})
        except ProcessorError:
            raise
        except Exception as exc:
            logger.exception("PreProcessor '%s' failed", name)
            raise ProcessorError(str(exc), processor_name=name) from exc

    return headers, body, results


def run_postprocessors(
    case: Dict[str, Any],
    response: Any,  # requests.Response
    global_config: Dict[str, Any],
) -> List[Dict[str, Any]]:
    """Execute all postprocessors declared on a test case.

    Args:
        case: The test case dict.
        response: The ``requests.Response`` object.
        global_config: Full merged env configuration.

    Returns:
        List of per-processor outcome dicts.

    Raises:
        ProcessorError: Immediately if any postprocessor fails.
    """
    from processors.base import _POST_PROCESSOR_REGISTRY

    request_headers = dict(case.get("request_head") or {})
    request_body = dict(case.get("request_body") or {})
    response_headers = dict(response.headers) if response is not None else {}
    response_body = _extract_body(response) if response is not None else None

    processor_items = case.get("postprocessors") or []
    results: List[Dict[str, Any]] = []

    for item in processor_items:
        name = item.get("name", "")
        case_config = item.get("config") or {}

        processor_cls = _POST_PROCESSOR_REGISTRY.get(name)
        if processor_cls is None:
            raise ProcessorError(
                f"PostProcessor '{name}' not found in registry. "
                f"Available: {list(_POST_PROCESSOR_REGISTRY.keys())}",
                processor_name=name,
            )

        instance = processor_cls()
        try:
            instance.process(
                request_headers, request_body,
                response_headers, response_body,
                case_config, global_config,
            )
            results.append({"name": name, "status": "ok"})
        except ProcessorError:
            raise
        except Exception as exc:
            logger.exception("PostProcessor '%s' failed", name)
            raise ProcessorError(str(exc), processor_name=name) from exc

    return results


def _extract_body(response: Any) -> Any:
    """Extract parsed body from a requests.Response."""
    try:
        return response.json()
    except (ValueError, AttributeError):
        try:
            return response.text
        except AttributeError:
            return None
