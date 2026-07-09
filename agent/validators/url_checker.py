"""URL existence checker: validates generated URLs against the raw API documentation."""

from typing import Dict, List

from flow_forge_schemas import URL_NOT_EXIST_PREFIX


def check_url_existence(cases: List[Dict], api_doc_text: str) -> None:
    """Prepend '<URL not exist>' to any generated URL not found in the API doc text.

    Searches for each case's URL string directly in the original API documentation
    text provided by the user. If the URL does not appear anywhere in the raw
    document, it is flagged as a likely AI hallucination.
    """
    if not api_doc_text.strip():
        return

    for case in cases:
        # Single test case — url at top level
        url = str(case.get("url", "")).strip()
        if url and url not in api_doc_text:
            case["url"] = f"{URL_NOT_EXIST_PREFIX}{url}"

        # Business flow — url inside each step
        for step in (case.get("steps") or []):
            url = str(step.get("url", "")).strip()
            if url and url not in api_doc_text:
                step["url"] = f"{URL_NOT_EXIST_PREFIX}{url}"
