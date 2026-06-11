"""BatchController: orchestrates batch-by-batch test case generation.

At each iteration the controller:
1. Reads available interfaces and already-generated cases from disk
2. Uses an LLM call to decide which interfaces to cover in the next batch
3. Calls CaseGenerator for that batch
4. Validates (if enabled) and saves to YAML
5. Loops until all test points are covered
"""

import json
import logging
from pathlib import Path
from typing import Any, Dict, List, Optional

from agents.base import BaseAgent
from config.settings import Settings
from models.schema import TestPlan
from writers.yaml_writer import YamlWriter

logger = logging.getLogger(__name__)

_BATCH_DECISION_SYSTEM = (
    "你是一个测试用例分批生成决策器。你的任务是检查当前生成进度，决定下一批需要生成哪些用例。"
    "每批生成的用例数量不应超过给定的 batch_size。"
    "优先覆盖尚未生成用例的接口。如果所有测试点都已覆盖，返回 done。"
    "只输出 JSON，不要输出其他内容。"
)

_BATCH_DECISION_USER = (
    "## 测试计划中的测试点\n"
    "{test_points_summary}\n\n"
    "## 已保存的接口定义 (interfaces/)\n"
    "{saved_interfaces}\n\n"
    "## 已生成的单接口用例 (single_cases/)\n"
    "{generated_single}\n\n"
    "## 已生成的业务链路用例 (biz_flows/)\n"
    "{generated_biz}\n\n"
    "## 当前批次限制\n"
    "batch_size: {batch_size}\n"
    "待生成类型: {batch_type}\n\n"
    "请决定本批要生成的内容。输出 JSON 格式：\n"
    '{{"action": "generate"|"done", '
    '"batch_type": "single"|"biz", '
    '"interface_ids": ["id1", "id2"], '
    '"test_point_ids": ["tp1"], '
    '"reason": "决策理由"}}'
)


class BatchController(BaseAgent):
    """Orchestrates batch-by-batch test case generation.

    Reads from / writes to the YAML output directory. Uses LLM calls
    at each iteration to decide which interfaces / test points to
    include in the next batch.
    """

    def __init__(self, settings: Settings):
        super().__init__(
            api_key=settings.llm_api_key,
            model=settings.llm_model,
            temperature=0.3,
            max_tokens=settings.llm_max_tokens,
            max_retries=settings.max_retries,
            max_steps=settings.max_steps,
            base_url=settings.llm_base_url,
        )
        self._batch_size = settings.batch_size
        self._enable_validation = settings.enable_validation
        self._max_validation_retries = settings.max_validation_retries

    # ------------------------------------------------------------------
    # Public entry point
    # ------------------------------------------------------------------

    def run(
        self,
        plan: TestPlan,
        interfaces: List[Dict],
        output_dir: str,
        case_generator: Any,
        validator: Any = None,
        user_guidance: str = "",
    ) -> Dict[str, Any]:
        """Run batch generation for both single cases and biz flows.

        Returns dict with:
          - single_cases: list of generated single case dicts
          - biz_flows: list of generated biz flow dicts
          - failures: list of cases that failed validation after all retries
        """
        self.reset_steps()

        all_single: List[Dict] = []
        all_biz: List[Dict] = []
        all_failures: List[Dict] = []

        # ---- Phase 1: Single cases ----
        logger.info("BatchController: starting single-case generation")
        single_result = self._generate_phase(
            plan=plan,
            interfaces=interfaces,
            output_dir=output_dir,
            batch_type="single",
            case_generator=case_generator,
            validator=validator,
            user_guidance=user_guidance,
        )
        all_single = single_result["cases"]
        all_failures.extend(single_result["failures"])

        # ---- Phase 2: Biz flows ----
        if plan.biz_flow_scenarios:
            logger.info("BatchController: starting biz-flow generation")
            biz_result = self._generate_phase(
                plan=plan,
                interfaces=interfaces,
                output_dir=output_dir,
                batch_type="biz",
                case_generator=case_generator,
                validator=validator,
                user_guidance=user_guidance,
            )
            all_biz = biz_result["cases"]
            all_failures.extend(biz_result["failures"])

        # Write failure log if any
        if all_failures:
            YamlWriter.write_failures(all_failures, output_dir)
            logger.warning("BatchController: %d cases failed after all retries", len(all_failures))

        return {
            "single_cases": all_single,
            "biz_flows": all_biz,
            "failures": all_failures,
        }

    # ------------------------------------------------------------------
    # Phase runner
    # ------------------------------------------------------------------

    def _generate_phase(
        self,
        plan: TestPlan,
        interfaces: List[Dict],
        output_dir: str,
        batch_type: str,
        case_generator: Any,
        validator: Any,
        user_guidance: str = "",
    ) -> Dict[str, Any]:
        """Run batch loop for one phase (single or biz)."""
        all_cases: List[Dict] = []
        all_failures: List[Dict] = []
        max_iterations = 50  # safety cap

        for iteration in range(1, max_iterations + 1):
            self.check_step()

            # Build progress snapshot
            saved_iface_ids = YamlWriter.list_interface_ids(output_dir)
            generated_ids = YamlWriter.list_generated_case_ids(output_dir, batch_type)
            test_points_summary = self._summarize_test_points(plan, batch_type)

            # Ask LLM to decide next batch
            decision = self._decide_batch(
                test_points_summary=test_points_summary,
                saved_interface_ids=saved_iface_ids,
                generated_ids=generated_ids,
                batch_type=batch_type,
            )

            if decision.get("action") == "done":
                logger.info("BatchController: %s phase complete after %d iterations",
                            batch_type, iteration)
                break

            batch_iface_ids = decision.get("interface_ids", [])
            batch_tp_ids = decision.get("test_point_ids", [])

            if not batch_iface_ids:
                logger.info("BatchController: no more interfaces to cover for %s", batch_type)
                break

            # Load the relevant interfaces
            batch_ifaces = [
                i for i in interfaces
                if str(i.get("test_id", "")) in batch_iface_ids
            ]
            if not batch_ifaces:
                batch_ifaces = self._load_interfaces_from_disk(output_dir, batch_iface_ids)

            if not batch_ifaces:
                logger.warning("BatchController: no matching interfaces found for %s", batch_iface_ids)
                continue

            # Resolve test points
            batch_tps = self._resolve_test_points(plan, batch_iface_ids, batch_tp_ids, batch_type)

            logger.info("BatchController [%s] batch %d: %d interfaces, %d test points",
                        batch_type, iteration, len(batch_ifaces), len(batch_tps))

            # Generate
            try:
                generated = case_generator.generate_batch(
                    interfaces=batch_ifaces,
                    test_points=batch_tps,
                    batch_type=batch_type,
                    user_guidance=user_guidance,
                )
            except Exception as e:
                logger.exception("BatchController: generation failed for batch %d", iteration)
                continue

            if not generated:
                logger.warning("BatchController: empty generation result for batch %d", iteration)
                continue

            cases = generated if isinstance(generated, list) else (
                generated.get("single_cases") or generated.get("biz_flows") or []
            )

            # Validate
            if validator and self._enable_validation:
                valid, invalid, errors = validator.validate(cases, "single" if batch_type == "single" else "biz_flow")

                if invalid:
                    logger.info("BatchController: %d/%d cases invalid, retrying...",
                                len(invalid), len(cases))
                    retry_valid, still_invalid, summary = validator.validate_with_retry(
                        case_generator=case_generator,
                        invalid_cases=invalid,
                        interfaces=batch_ifaces,
                        test_points=batch_tps,
                        batch_type=batch_type,
                        max_retries=self._max_validation_retries,
                    )
                    cases = valid + retry_valid
                    for entry in summary:
                        if entry["retries"] >= self._max_validation_retries:
                            all_failures.append(entry)

            # Save
            for case in cases:
                if batch_type == "single":
                    YamlWriter.write_single_case(case, output_dir)
                else:
                    YamlWriter.write_biz_flow(case, output_dir)

            all_cases.extend(cases)
            logger.info("BatchController: saved %d %s cases (total: %d)",
                        len(cases), batch_type, len(all_cases))

        # Also load any cases that were already on disk before this run
        if batch_type == "single":
            existing = YamlWriter.read_single_cases(output_dir)
        else:
            existing = YamlWriter.read_biz_flows(output_dir)

        # Merge: prefer newly generated over existing (by test_id)
        merged = {self._case_key(c, batch_type): c for c in existing}
        for c in all_cases:
            merged[self._case_key(c, batch_type)] = c

        return {"cases": list(merged.values()), "failures": all_failures}

    # ------------------------------------------------------------------
    # LLM batch decision
    # ------------------------------------------------------------------

    def _decide_batch(
        self,
        test_points_summary: str,
        saved_interface_ids: List[str],
        generated_ids: List[str],
        batch_type: str,
    ) -> Dict[str, Any]:
        """Ask the LLM to decide what to generate in the next batch."""
        prompt = _BATCH_DECISION_USER.format(
            test_points_summary=test_points_summary,
            saved_interfaces=json.dumps(saved_interface_ids, ensure_ascii=False),
            generated_single=json.dumps(generated_ids, ensure_ascii=False)
            if batch_type == "single" else "[]",
            generated_biz=json.dumps(generated_ids, ensure_ascii=False)
            if batch_type == "biz" else "[]",
            batch_size=self._batch_size,
            batch_type=batch_type,
        )

        try:
            result = self.call_llm_json(prompt, _BATCH_DECISION_SYSTEM)
            return result if isinstance(result, dict) else {}
        except Exception:
            logger.warning("BatchController: decision LLM call failed, falling back to auto-select")
            return self._fallback_decision(saved_interface_ids, generated_ids)

    def _fallback_decision(
        self, saved_interface_ids: List[str], generated_ids: List[str]
    ) -> Dict[str, Any]:
        """Simple rule-based fallback when the LLM decision call fails."""
        remaining = [i for i in saved_interface_ids if i not in generated_ids]
        if not remaining:
            return {"action": "done"}
        batch = remaining[: self._batch_size]
        return {"action": "generate", "interface_ids": batch, "test_point_ids": []}

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _summarize_test_points(plan: TestPlan, batch_type: str) -> str:
        """Build a compact summary of test points for the decision prompt."""
        parts = []
        if batch_type == "single":
            for api_id, points in plan.single_test_points.items():
                parts.append(f"{api_id}: {len(points)} test points")
                for p in points:
                    parts.append(f"  - [{p.tag}] {p.test_id}: {p.description}")
        else:
            for scenario in plan.biz_flow_scenarios:
                parts.append(
                    f"- {scenario.get('name', '')}: {scenario.get('description', '')}"
                )
        return "\n".join(parts) if parts else "(none)"

    @staticmethod
    def _resolve_test_points(
        plan: TestPlan,
        iface_ids: List[str],
        tp_ids: List[str],
        batch_type: str,
    ) -> List[Dict]:
        """Get the test point dicts relevant to the given interface ids."""
        result = []
        if batch_type == "single":
            for api_id in iface_ids:
                points = plan.single_test_points.get(api_id, [])
                for p in points:
                    d = {
                        "test_id": p.test_id,
                        "description": p.description,
                        "tag": p.tag,
                        "scenario_type": p.scenario_type,
                    }
                    if not tp_ids or p.test_id in tp_ids:
                        result.append(d)
        return result

    @staticmethod
    def _load_interfaces_from_disk(output_dir: str, ids: List[str]) -> List[Dict]:
        """Load specific interfaces from the YAML directory."""
        all_ifaces = YamlWriter.read_interfaces(output_dir)
        return [i for i in all_ifaces if str(i.get("test_id", "")) in ids]

    @staticmethod
    def _case_key(case, batch_type: str) -> str:
        if batch_type == "single":
            if isinstance(case, dict):
                return str(case.get("test_id", ""))
            return str(getattr(case, "test_id", ""))
        if isinstance(case, dict):
            return str(case.get("sheet_name", ""))
        return str(getattr(case, "sheet_name", ""))
