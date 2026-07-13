"""URL 校验节点 — 校验接口 URL 与 API 文档原文的一致性。

validate_interface_urls node: validates interface URLs against API doc text.
"""

import logging

from agents.api_analyzer import ApiAnalyzer
from graph.state import GraphState
from prompts.render import render_prompt
from prompts.url_correction import IFACE_URL_CORRECTION_SYSTEM, IFACE_URL_CORRECTION_USER

from . import helpers as _h
from .helpers import _, _sl, save_pipeline_artifact, save_pipeline_state

logger = logging.getLogger(__name__)


def validate_interface_urls_node(state: GraphState) -> GraphState:
    """校验每个接口 URL 是否出现在 API 文档原文中。

    Validate each interface URL against the API doc text. URLs not found
    are corrected via LLM (up to max_retries). Those still failing are
    marked with ``[URL_MAY_INCORRECT]``.
    """
    state.setdefault("errors", [])
    state.setdefault("url_validation_errors", [])

    interfaces = state.get("interfaces", [])
    api_raw_text = state.get("api_raw_text", "")
    parse_mode = state.get("parse_mode", "raw")

    if not interfaces or not api_raw_text:
        logger.info("Skipping URL validation: no interfaces or api_raw_text")
        return state

    logger.info(_("url_check.checking"))
    if _sl():
        _sl().log_node_start("validate_interface_urls", "url_check")

    max_retries = _h._settings.url_doc_match_max_retries
    url_strategy = getattr(_h._settings, "url_doc_match_strategy", "warn")
    url_enabled = getattr(_h._settings, "url_doc_match_enabled", True)

    # 未启用 URL 文档匹配校验：跳过 / Not enabled: skip entirely
    if not url_enabled:
        logger.info(_("url_check.disabled"))
        return state

    # skip 策略：完全跳过 URL 校验 / Skip strategy: bypass entirely
    if url_strategy == "skip":
        logger.info(_("url_check.skipped"))
        return state

    bad_interfaces = []
    url_errors = []

    for iface in interfaces:
        url = str(iface.get("url", "")).strip() if isinstance(iface, dict) else str(getattr(iface, "url", "")).strip()
        if url and url not in api_raw_text:
            bad_interfaces.append(iface)

    if not bad_interfaces:
        logger.info(_("url_check.all_passed", count=len(interfaces)))
        if _sl():
            _sl().log_event("validate_interface_urls", status="all_passed", count=len(interfaces))
            _sl().log_node_end("validate_interface_urls")
        return state

    logger.info(_("url_check.found_bad", count=len(bad_interfaces)))

    api_analyzer = ApiAnalyzer(_h._settings)
    corrected_count = 0

    for iface in bad_interfaces:
        interface_id = iface.get("test_id", iface.get("api_name", "unknown")) if isinstance(iface, dict) else getattr(iface, "test_id", "unknown")
        bad_url = iface.get("url", "") if isinstance(iface, dict) else getattr(iface, "url", "")
        http_method = iface.get("method", "GET") if isinstance(iface, dict) else getattr(iface, "method", "GET")

        snippets = api_analyzer._fuzzy_search_api_doc(
            url=bad_url, http_method=http_method,
            api_doc_text=api_raw_text, max_snippet_tokens=4000,
        )

        corrected = False
        for retry in range(max_retries):
            try:
                correction_prompt = render_prompt(
                    IFACE_URL_CORRECTION_USER,
                    test_id=interface_id,
                    bad_url=bad_url,
                    http_method=http_method,
                    snippets=snippets,
                )
                result = api_analyzer.call_llm_json(
                    correction_prompt, IFACE_URL_CORRECTION_SYSTEM
                )
                new_url = result.get("corrected_url", "").strip() if isinstance(result, dict) else ""
                if new_url and new_url in api_raw_text:
                    if isinstance(iface, dict):
                        iface["url"] = new_url
                        iface["remark"] = (iface.get("remark") or "") + " [URL corrected by LLM]"
                    else:
                        iface.url = new_url
                        iface.remark = (getattr(iface, "remark", "") or "") + " [URL corrected by LLM]"
                    corrected_count += 1
                    corrected = True
                    logger.info("Corrected URL for %s: %s → %s", interface_id, bad_url, new_url)
                    break
                else:
                    logger.warning(
                        "URL correction retry %d/%d for %s: corrected URL '%s' not found in doc",
                        retry + 1, max_retries, interface_id, new_url,
                    )
            except Exception as e:
                logger.warning("URL correction retry %d/%d failed: %s", retry + 1, max_retries, e)

        if not corrected:
            if isinstance(iface, dict):
                iface["remark"] = (iface.get("remark") or "") + " [URL_MAY_INCORRECT]"
            else:
                iface.remark = (getattr(iface, "remark", "") or "") + " [URL_MAY_INCORRECT]"
            url_errors.append({
                "test_id": interface_id, "url": bad_url, "method": http_method,
            })

    if url_errors:
        logger.info(_("url_check.cannot_correct", count=len(url_errors)))
        for err in url_errors:
            logger.info(_("url_check.cannot_correct_item", test_id=err["test_id"], method=err["method"], url=err["url"]))
        state["url_validation_errors"] = url_errors
        # fail 策略：纠错耗尽后终止流水线 / Fail strategy: abort pipeline
        if url_strategy == "fail":
            raise ValueError(
                f"URL correction failed for {len(url_errors)} interface(s) "
                f"after {max_retries} retries"
            )
    else:
        logger.info(_("url_check.corrected_count", count=corrected_count))

    if _sl():
        _sl().log_event(
            "validate_interface_urls",
            total=len(interfaces), bad=len(bad_interfaces),
            corrected=corrected_count, failed=len(url_errors),
        )
        _sl().log_node_end("validate_interface_urls")

    # Save pipeline artifact for resume
    memory_dir = state.get("memory_dir", "")
    if memory_dir:
        save_pipeline_artifact(memory_dir, "url_validation.json", {
            "url_errors": url_errors,
            "corrected_count": corrected_count,
        })
        save_pipeline_state(memory_dir, "validate_urls")

    return state
