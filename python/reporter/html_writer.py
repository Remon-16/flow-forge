import json
import logging
import os
from datetime import datetime
from typing import Any, Dict, List

logger = logging.getLogger(__name__)


class HTMLReportWriter:
    """Generates a self-contained HTML test report."""

    def __init__(self, config: Dict[str, Any]):
        self.config = config
        self.report_name = config.get("reportName", "APIReport")
        self.env_name = config.get("envName", "")
        self.case_file_path = config.get("caseFilePath", "")

    def write(
        self,
        single_results: List[Dict[str, Any]],
        biz_results: List[Dict[str, Any]],
    ) -> str:
        report_dir = self._ensure_report_dir()
        filename = self._generate_filename()
        filepath = os.path.join(report_dir, filename)

        single_passed = sum(1 for r in single_results if r.get("passed"))
        single_failed = len(single_results) - single_passed
        single_rate = (single_passed / len(single_results) * 100) if single_results else 0

        biz_passed = sum(1 for r in biz_results if r.get("passed"))
        biz_failed = len(biz_results) - biz_passed
        biz_rate = (biz_passed / len(biz_results) * 100) if biz_results else 0

        total = len(single_results) + len(biz_results)

        html_parts: List[str] = []
        self._write_html_start(html_parts, total, single_passed, single_failed,
                               single_rate, biz_passed, biz_failed, biz_rate)

        if single_results:
            self._write_single_section(html_parts, single_results,
                                       single_passed, single_failed, single_rate)
        if biz_results:
            self._write_biz_section(html_parts, biz_results,
                                    biz_passed, biz_failed, biz_rate)

        self._write_html_end(html_parts)

        content = "\n".join(html_parts)
        with open(filepath, "w", encoding="utf-8") as f:
            f.write(content)

        logger.info("HTML report written to %s", filepath)
        return filepath

    def _generate_filename(self) -> str:
        base = os.path.splitext(os.path.basename(self.case_file_path))[0] or "report"
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        return f"{base}_{timestamp}.html"

    def _ensure_report_dir(self) -> str:
        current_dir = os.path.dirname(os.path.abspath(__file__))
        root_dir = os.path.dirname(current_dir)
        report_dir = os.path.join(root_dir, "report")
        os.makedirs(report_dir, exist_ok=True)
        return report_dir

    def _write_html_start(
        self, parts: List[str], total: int,
        s_passed: int, s_failed: int, s_rate: float,
        b_passed: int, b_failed: int, b_rate: float,
    ) -> None:
        parts.append("<!DOCTYPE html>")
        parts.append("<html lang=\"zh-CN\">")
        parts.append("<head>")
        parts.append("<meta charset=\"UTF-8\">")
        parts.append(f"<title>{self.report_name}</title>")
        parts.append("<style>")
        parts.append(self._css())
        parts.append("</style>")
        parts.append("</head>")
        parts.append("<body>")

        parts.append(f"<h1>{self.report_name} 接口测试报告</h1>")
        parts.append("<div class=\"summary\">")
        parts.append(f"<p><strong>环境:</strong> {self.env_name}</p>")
        parts.append(f"<p><strong>测试时间:</strong> {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}</p>")
        parts.append(f"<p><strong>总用例数:</strong> {total}</p>")
        parts.append("</div>")

    def _write_single_section(
        self, parts: List[str], results: List[Dict[str, Any]],
        passed: int, failed: int, rate: float,
    ) -> None:
        coll_id = "single_list"
        parts.append("<div class=\"section\">")
        parts.append(
            "<div class=\"section-header\" onclick=\"toggle('" + coll_id + "')\">"
            "▼ 单接口用例数"
            f" <span class=\"pass\">通过 {passed}</span>"
            f" <span class=\"fail\">失败 {failed}</span>"
            f" 通过率 {rate:.1f}%"
            "</div>"
        )
        parts.append(f"<div class=\"section-body\" id=\"{coll_id}\">")

        sorted_results = sorted(results, key=lambda r: (r.get("passed"), r.get("test_id", "")))
        for i, r in enumerate(sorted_results, 1):
            self._write_single_case(parts, i, r)

        parts.append("</div></div>")

    def _write_single_case(
        self, parts: List[str], index: int, result: Dict[str, Any]
    ) -> None:
        status = "PASS" if result.get("passed") else "FAIL"
        css_class = "case-pass" if result.get("passed") else "case-fail"
        test_id = result.get("test_id", "")
        api_name = result.get("api_name", "")
        tag = result.get("tag", "")

        parts.append(f"<div class=\"case-card {css_class}\">")
        tag_badge = f" <span class=\"tag\">{tag}</span>" if tag else ""
        parts.append(
            f"<div class=\"case-title\">[{status}] {index}. {test_id} - {api_name}{tag_badge}</div>"
        )
        parts.append("<div class=\"case-detail\">")

        parts.append(f"<p><strong>AppName:</strong> {result.get('app_name', '')}</p>")
        parts.append(f"<p><strong>baseURL:</strong> {result.get('base_url', '')}</p>")
        parts.append(f"<p><strong>URL:</strong> {result.get('url', '')}</p>")
        parts.append(f"<p><strong>Method:</strong> {result.get('method', '')}</p>")

        error = result.get("error")
        if error:
            parts.append(f"<p class=\"error-msg\"><strong>Error:</strong> {self._h(error)}</p>")
            parts.append("</div></div>")
            return

        self._write_processor_results(parts, result)
        self._write_json_block(parts, "Request Headers", result.get("request_headers"))
        self._write_json_block(parts, "Request Body", result.get("request_body"))
        self._write_json_block(parts, "Response Body", result.get("response_body"))
        self._write_assertions(parts, result.get("assertions", []))

        parts.append("</div></div>")

    def _write_biz_section(
        self, parts: List[str], results: List[Dict[str, Any]],
        passed: int, failed: int, rate: float,
    ) -> None:
        coll_id = "biz_list"
        parts.append("<div class=\"section\">")
        parts.append(
            "<div class=\"section-header\" onclick=\"toggle('" + coll_id + "')\">"
            "▼ 业务用例数"
            f" <span class=\"pass\">通过 {passed}</span>"
            f" <span class=\"fail\">失败 {failed}</span>"
            f" 通过率 {rate:.1f}%"
            "</div>"
        )
        parts.append(f"<div class=\"section-body\" id=\"{coll_id}\">")

        sorted_results = sorted(results, key=lambda r: (r.get("passed"), r.get("sheet_name", "")))
        for i, r in enumerate(sorted_results, 1):
            self._write_biz_flow(parts, i, r)

        parts.append("</div></div>")

    def _write_biz_flow(
        self, parts: List[str], index: int, result: Dict[str, Any]
    ) -> None:
        sheet_name = result.get("sheet_name", "unknown")
        parse_error = result.get("parse_error")
        passed = result.get("passed")
        css_class = "case-pass" if passed else "case-fail"

        parts.append(f"<div class=\"case-card {css_class}\">")
        parts.append(f"<div class=\"case-title\">{index}. {sheet_name}</div>")
        parts.append("<div class=\"case-detail\">")

        if parse_error:
            parts.append(f"<p class=\"error-msg\">解析业务链路用例解析异常，异常参数为: {self._h(parse_error)}</p>")
            parts.append("<p><strong>业务链路用例执行了 0 条</strong></p>")
            parts.append("</div></div>")
            return

        flow_chain = result.get("flow_chain", "")
        if flow_chain:
            parts.append(f"<p><strong>执行链路:</strong> {self._h(flow_chain)}</p>")

        steps = result.get("steps", [])
        if not steps:
            parts.append("</div></div>")
            return

        for j, step in enumerate(steps, 1):
            step_id = step.get("step_id", step.get("test_id", ""))
            api_name = step.get("api_name", "")
            s_passed = step.get("passed")
            s_class = "step-pass" if s_passed else "step-fail"
            coll_id = f"biz_{index}_{j}"

            parts.append(f"<div class=\"step-card {s_class}\">")
            parts.append(
                f"<div class=\"step-header\" onclick=\"toggle('{coll_id}')\">"
                f"{'PASS' if s_passed else 'FAIL'} Step{j}. {step_id} - {api_name}"
                "</div>"
            )
            parts.append(f"<div class=\"step-body\" id=\"{coll_id}\">")

            parts.append(f"<p><strong>AppName:</strong> {step.get('app_name', '')}</p>")
            parts.append(f"<p><strong>baseURL:</strong> {step.get('base_url', '')}</p>")
            parts.append(f"<p><strong>URL:</strong> {step.get('url', '')}</p>")
            parts.append(f"<p><strong>Method:</strong> {step.get('method', '')}</p>")

            s_error = step.get("error")
            if s_error:
                parts.append(f"<p class=\"error-msg\"><strong>Error:</strong> {self._h(s_error)}</p>")
                parts.append("</div></div>")
                continue

            self._write_processor_results(parts, step)
            self._write_json_block(parts, "Request Headers", step.get("request_headers"))
            self._write_json_block(parts, "Request Body", step.get("request_body"))
            self._write_json_block(parts, "Response Body", step.get("response_body"))
            self._write_assertions(parts, step.get("assertions", []))

            parts.append("</div></div>")

        parts.append("</div></div>")

    @staticmethod
    def _write_processor_results(parts: List[str], result: Dict[str, Any]) -> None:
        """Render preprocessor / postprocessor execution results."""
        for label, key in [("PreProcessor", "preprocessor_results"),
                           ("PostProcessor", "postprocessor_results")]:
            for pr in result.get(key) or []:
                status = pr.get("status", "")
                name = pr.get("name", "unknown")
                error = pr.get("error", "")
                if error or status != "ok":
                    parts.append(
                        f"<p class=\"error-msg\"><strong>{label} [{name}]:</strong> "
                        f"{HTMLReportWriter._h(error or status)}</p>"
                    )

    def _write_json_block(self, parts: List[str], title: str, data: Any) -> None:
        parts.append(f"<p><strong>{title}:</strong></p>")
        if data is not None:
            content = json.dumps(data, ensure_ascii=False, indent=2)
            parts.append(f"<pre><code>{self._h(content)}</code></pre>")
        else:
            parts.append("<p><em>(empty)</em></p>")

    def _write_assertions(self, parts: List[str], assertions: List[Dict]) -> None:
        if not assertions:
            return
        parts.append("<p><strong>断言结果:</strong></p>")
        parts.append("<table><tr><th>Field</th><th>Expected</th><th>Actual</th><th>Result</th></tr>")
        for a in assertions:
            a_class = "assert-pass" if a["passed"] else "assert-fail"
            parts.append(
                f"<tr class=\"{a_class}\">"
                f"<td>{self._h(a.get('field', ''))}</td>"
                f"<td>{self._h(a.get('expected', ''))}</td>"
                f"<td>{self._h(a.get('actual', ''))}</td>"
                f"<td>{'PASS' if a['passed'] else 'FAIL'}</td>"
                "</tr>"
            )
        parts.append("</table>")

    def _write_html_end(self, parts: List[str]) -> None:
        parts.append("<script>")
        parts.append("function toggle(id) {")
        parts.append("  var el = document.getElementById(id);")
        parts.append("  if (el) { el.style.display = el.style.display === 'none' ? 'block' : 'none'; }")
        parts.append("}")
        parts.append("</script>")
        parts.append("</body>")
        parts.append("</html>")

    def _css(self) -> str:
        return """
body { font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
       margin: 20px; background: #f5f5f5; color: #333; }
h1 { color: #1a1a1a; border-bottom: 2px solid #4a90d9; padding-bottom: 10px; }
.summary { background: #fff; padding: 15px 20px; border-radius: 6px; margin-bottom: 20px;
           box-shadow: 0 1px 3px rgba(0,0,0,0.1); }
.section { margin-bottom: 20px; }
.section-header { background: #4a90d9; color: #fff; padding: 10px 16px;
                  border-radius: 6px; cursor: pointer; font-weight: bold; }
.section-header .pass { margin-left: 12px; }
.section-header .fail { color: #ffcccc; margin-left: 8px; }
.section-body { display: block; margin-top: 10px; }
.case-card { background: #fff; border-radius: 6px; margin-bottom: 10px;
             box-shadow: 0 1px 3px rgba(0,0,0,0.1); overflow: hidden; }
.case-pass { border-left: 4px solid #28a745; }
.case-fail { border-left: 4px solid #dc3545; }
.case-title { padding: 10px 16px; font-weight: bold;
              background: #fafafa; border-bottom: 1px solid #eee; }
.case-pass .case-title { color: #155724; }
.case-fail .case-title { color: #721c24; }
.case-detail { padding: 12px 16px; }
.case-detail p { margin: 4px 0; }
.tag { background: #e9ecef; padding: 1px 6px; border-radius: 3px; font-size: 0.85em; }
.error-msg { color: #dc3545; font-weight: bold; }
.step-card { border-radius: 4px; margin: 8px 0; border: 1px solid #dee2e6; }
.step-pass { border-left: 3px solid #28a745; }
.step-fail { border-left: 3px solid #dc3545; }
.step-header { padding: 8px 12px; cursor: pointer; font-weight: bold; background: #f8f9fa; }
.step-body { padding: 8px 12px; display: block; }
pre { background: #f4f4f4; padding: 10px; border-radius: 4px; overflow-x: auto; }
code { font-size: 0.9em; }
table { border-collapse: collapse; width: 100%; margin: 8px 0; }
th, td { border: 1px solid #dee2e6; padding: 6px 10px; text-align: left; }
th { background: #e9ecef; }
.assert-pass { background: #d4edda; }
.assert-fail { background: #f8d7da; }
"""
    @staticmethod
    def _h(val: Any) -> str:
        return str(val).replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
