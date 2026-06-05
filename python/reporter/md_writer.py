import json
import logging
import os
from datetime import datetime
from typing import Any, Dict, List

logger = logging.getLogger(__name__)


class MarkdownReportWriter:
    """Generates a Markdown test report from execution results."""

    def __init__(self, config: Dict[str, Any]):
        self.config = config
        self.report_name = config.get("reportName", "APIReport")
        self.env_name = config.get("envName", "")
        self.base_url = config.get("baseURL", "")
        self.case_file_path = config.get("caseFilePath", "")

    def write(self, results: List[Dict[str, Any]]) -> str:
        report_dir = self._ensure_report_dir()
        filename = self._generate_filename()
        filepath = os.path.join(report_dir, filename)

        total = len(results)
        passed = sum(1 for r in results if r.get("passed"))
        failed = total - passed
        pass_rate = (passed / total * 100) if total > 0 else 0

        lines: List[str] = []
        self._write_header(lines, total, passed, failed, pass_rate)
        self._write_summary_table(lines, total, passed, failed, pass_rate)

        for i, result in enumerate(results, 1):
            self._write_case(lines, i, result)

        content = "\n".join(lines)
        with open(filepath, "w", encoding="utf-8") as f:
            f.write(content)

        logger.info("Report written to %s (%d cases)", filepath, total)
        return filepath

    def _generate_filename(self) -> str:
        base = os.path.splitext(os.path.basename(self.case_file_path))[0] or "report"
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        return f"{base}_{timestamp}.md"

    def _ensure_report_dir(self) -> str:
        current_dir = os.path.dirname(os.path.abspath(__file__))
        root_dir = os.path.dirname(current_dir)
        report_dir = os.path.join(root_dir, "report")
        os.makedirs(report_dir, exist_ok=True)
        return report_dir

    def _write_header(
        self, lines: List[str], total: int, passed: int, failed: int, pass_rate: float
    ) -> None:
        lines.append(f"# {self.report_name} 接口测试报告")
        lines.append("")
        lines.append(f"- **环境**: {self.env_name}")
        lines.append(f"- **Base URL**: {self.base_url}")
        lines.append(f"- **测试时间**: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
        lines.append(f"- **总用例数**: {total}")
        lines.append(f"- **通过**: {passed}")
        lines.append(f"- **失败**: {failed}")
        lines.append(f"- **通过率**: {pass_rate:.1f}%")
        lines.append("")

    def _write_summary_table(
        self, lines: List[str], total: int, passed: int, failed: int, pass_rate: float
    ) -> None:
        lines.append("## 测试概览")
        lines.append("")
        lines.append("| 指标 | 数值 |")
        lines.append("|------|------|")
        lines.append(f"| 总用例数 | {total} |")
        lines.append(f"| 通过 | {passed} |")
        lines.append(f"| 失败 | {failed} |")
        lines.append(f"| 通过率 | {pass_rate:.1f}% |")
        lines.append("")

    def _write_case(
        self, lines: List[str], index: int, result: Dict[str, Any]
    ) -> None:
        status = "PASS" if result.get("passed") else "FAIL"
        test_id = result.get("test_id", "")
        api_name = result.get("api_name", "")
        tag = result.get("tag", "")

        lines.append("---")
        lines.append("")
        tag_suffix = f" `{tag}`" if tag else ""
        lines.append(f"### {index}. [{status}] {test_id} - {api_name}{tag_suffix}")
        lines.append("")

        lines.append(f"- **Method**: {result.get('method', '')}")
        lines.append(f"- **URL**: {result.get('url', '')}")
        lines.append("")

        error = result.get("error")
        if error:
            lines.append(f"> **Error**: {error}")
            lines.append("")
            return

        self._write_json_section(lines, "Request Headers", result.get("request_headers"))
        self._write_json_section(lines, "Request Body", result.get("request_body"))
        self._write_json_section(lines, "Response Body", result.get("response_body"))

        assertions = result.get("assertions")
        if assertions:
            self._write_assertions(lines, assertions)

    def _write_json_section(
        self, lines: List[str], title: str, data: Any
    ) -> None:
        lines.append(f"**{title}**")
        lines.append("")
        if data is not None:
            lines.append("```json")
            lines.append(json.dumps(self._sanitize(data), ensure_ascii=False, indent=2))
            lines.append("```")
        else:
            lines.append("*(empty)*")
        lines.append("")

    def _write_assertions(
        self, lines: List[str], assertions: List[Dict[str, Any]]
    ) -> None:
        lines.append("**断言结果**")
        lines.append("")
        lines.append("| Field | Expected | Actual | Result |")
        lines.append("|-------|----------|--------|--------|")
        for a in assertions:
            status = "PASS" if a["passed"] else "**FAIL**"
            lines.append(
                f"| {a['field']} | {a.get('expected', '')} | {a.get('actual', '')} | {status} |"
            )
        lines.append("")

    @staticmethod
    def _sanitize(data: Any) -> Any:
        """Convert non-serializable values to strings for safe JSON output."""
        if isinstance(data, dict):
            return {k: MarkdownReportWriter._sanitize(v) for k, v in data.items()}
        if isinstance(data, list):
            return [MarkdownReportWriter._sanitize(v) for v in data]
        try:
            json.dumps(data)
            return data
        except (TypeError, ValueError):
            return str(data)
