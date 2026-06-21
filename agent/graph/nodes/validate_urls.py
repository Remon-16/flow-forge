"""URL 校验节点 — 校验接口 URL 与 API 文档原文的一致性。

validate_interface_urls node: validates interface URLs against API doc text.
"""

import logging

from agents.api_analyzer import ApiAnalyzer
from graph.state import GraphState

from .helpers import _settings, _sl

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

    print(f"\n[URL校验] 校验接口 URL 与文档原文的一致性...")
    if _sl():
        _sl().log_node_start("validate_interface_urls", "url_check")

    max_retries = _settings.url_correction_max_retries
    bad_interfaces = []
    url_errors = []

    for iface in interfaces:
        url = str(iface.get("url", "")).strip() if isinstance(iface, dict) else str(getattr(iface, "url", "")).strip()
        if url and url not in api_raw_text:
            bad_interfaces.append(iface)

    if not bad_interfaces:
        print(f"  → 所有 {len(interfaces)} 个接口 URL 校验通过")
        if _sl():
            _sl().log_event("validate_interface_urls", status="all_passed", count=len(interfaces))
            _sl().log_node_end("validate_interface_urls")
        return state

    print(f"  → 发现 {len(bad_interfaces)} 个接口 URL 不在文档原文中，尝试 LLM 纠正...")

    api_analyzer = ApiAnalyzer(_settings)
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
                correction_prompt = (
                    f"以下接口的 URL 在 API 文档中未找到匹配。"
                    f"请根据文档原文中的正确 URL 来纠正它。\n\n"
                    f"## 需要纠正的接口\n"
                    f"- test_id: {interface_id}\n"
                    f"- 当前 URL: {bad_url}\n"
                    f"- HTTP 方法: {http_method}\n\n"
                    f"## API 文档相关片段\n{snippets}\n\n"
                    f"请返回一个 JSON 对象，包含 corrected_url 字段。"
                    f"只输出 JSON，不要包含其他内容。"
                )
                result = api_analyzer.call_llm_json(
                    correction_prompt,
                    "你是接口文档专家，根据文档原文纠正 URL 错误。",
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
        print(f"\n  ⚠ 以下 {len(url_errors)} 个接口 URL 无法自动纠正，已标记为 [URL_MAY_INCORRECT]：")
        for err in url_errors:
            print(f"    - {err['test_id']}: {err['method']} {err['url']}")
        state["url_validation_errors"] = url_errors
    else:
        print(f"\n  → 成功纠正 {corrected_count} 个接口 URL")

    if _sl():
        _sl().log_event(
            "validate_interface_urls",
            total=len(interfaces), bad=len(bad_interfaces),
            corrected=corrected_count, failed=len(url_errors),
        )
        _sl().log_node_end("validate_interface_urls")

    return state
