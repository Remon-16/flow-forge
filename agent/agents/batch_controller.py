"""BatchController — 基于插件的测试用例分批生成编排器。

Plugin-based test case generation orchestrator.
流程: 骨架生成 → URL校验 → 插件执行（数据填充/断言生成/用户插件） → 输出
"""

import logging
import time
from typing import Any, Dict, List, Optional, Tuple

from plugins.base import CaseAttributeGenerator

from config.settings import Settings
from writers.yaml_writer import YamlWriter

logger = logging.getLogger(__name__)

_SKELETON_PHASE = "skeletons_generated"


class BatchController:
    """基于插件的测试用例分批生成编排器。

    Plugin-based test case generation orchestrator.
    骨架生成后按顺序遍历插件列表，每个插件处理 single/biz 用例。
    """

    def __init__(self, settings: Settings):
        self._batch_size = settings.batch_size
        self._enable_validation = settings.enable_validation
        self._max_validation_retries = settings.max_validation_retries
        self._max_steps_no_progress = settings.max_steps_no_progress
        self._url_correction_max_retries = getattr(
            settings, "url_correction_max_retries", 3
        )
        self._consecutive_failure_limit = getattr(
            settings, "consecutive_batch_failure_limit", 3
        )
        self._rate_limit_delay = getattr(settings, "llm_rate_limit_delay", 0.0)
        self._reference_dir = ""
        self._memory_dir = ""

    # ------------------------------------------------------------------
    # Public entry point
    # ------------------------------------------------------------------

    def run(
        self,
        plan,
        interfaces: List[Dict],
        output_dir: str,
        single_skel_gen: Any,
        biz_skel_gen: Any,
        plugins: List[CaseAttributeGenerator],
        user_guidance: str = "",
        reference_dir: str = "",
        api_doc_text: str = "",
        api_summary: Optional[List[Dict]] = None,
        resume: bool = False,
        memory_dir: str = "",
        resume_overwrite: bool = False,
    ) -> Dict[str, Any]:
        """执行完整的用例生成流水线。

        Run the full generation pipeline.
        返回: {"single_cases": [...], "biz_flows": [...], "failures": [...]}
        """
        from graph.checkpoint import CheckpointManager as _CkptMgr

        self._reference_dir = reference_dir
        self._memory_dir = memory_dir
        all_failures: List[Dict] = []

        ckpt_mgr = _CkptMgr(memory_dir) if memory_dir else None

        # 构建阶段列表：骨架 → 每个插件一个阶段
        # Build phase list: skeleton → one phase per plugin
        plugin_names = [p.declaration.plugin_name for p in plugins]
        phases = [_SKELETON_PHASE] + [f"plugin_{n}" for n in plugin_names]

        # ------------------------------------------------------------------
        # Resume: load checkpoint and restore state
        # ------------------------------------------------------------------
        restart_phase = _SKELETON_PHASE
        single_cases: List[Dict] = []
        biz_cases: List[Dict] = []

        if resume and ckpt_mgr and ckpt_mgr.exists():
            meta = ckpt_mgr.load_meta()
            if meta:
                restart_phase = _CkptMgr.get_restart_phase(meta)
                logger.info("Resume mode: restarting from phase '%s'", restart_phase)
                ckpt_settings = meta.get("settings", {})
                if ckpt_settings:
                    self._batch_size = ckpt_settings.get("batch_size", self._batch_size)
                    self._enable_validation = ckpt_settings.get(
                        "enable_validation", self._enable_validation
                    )
                    self._max_validation_retries = ckpt_settings.get(
                        "max_validation_retries", self._max_validation_retries
                    )
                    self._url_correction_max_retries = ckpt_settings.get(
                        "url_correction_max_retries", self._url_correction_max_retries
                    )
                data = ckpt_mgr.load_data()
                if data:
                    single_cases = data.get("single_cases", [])
                    biz_cases = data.get("biz_cases", [])
                    all_failures = data.get("failures", [])
                    logger.info(
                        "Restored checkpoint: %d single, %d biz",
                        len(single_cases), len(biz_cases),
                    )
            else:
                logger.warning("Checkpoint invalid; starting from scratch.")
                resume = False
        elif resume:
            logger.warning("No checkpoint found; starting from scratch.")
            resume = False

        def _phase_index(phase: str) -> int:
            try:
                return phases.index(phase)
            except ValueError:
                return -1

        # ================================================================
        # Step 1: Skeleton generation + URL check + correction
        # ================================================================
        if restart_phase == _SKELETON_PHASE:
            logger.info("=" * 60)
            logger.info("Step 1: Skeleton generation")
            logger.info("=" * 60)

            # 1a. Single case skeletons
            logger.info("Generating single case skeletons...")
            single_skels = single_skel_gen.generate(
                plan, interfaces, api_summary, user_guidance
            )
            logger.info("Generated %d single case skeletons", len(single_skels))

            # 1b. Biz flow skeletons
            logger.info("Generating biz flow skeletons...")
            biz_skels = []
            if hasattr(plan, "biz_flow_scenarios") and plan.biz_flow_scenarios:
                biz_skels = biz_skel_gen.generate(
                    plan, interfaces, api_summary, user_guidance
                )
                logger.info("Generated %d biz flow skeletons", len(biz_skels))
            else:
                logger.info("No biz flow scenarios in plan, skipping")

            # 1c. URL check + correction
            single_cases, single_failed = self._url_check_and_correct(
                single_skels, interfaces, api_doc_text, api_summary,
                single_skel_gen, "single"
            )
            biz_cases, biz_failed = self._url_check_and_correct(
                biz_skels, interfaces, api_doc_text, api_summary,
                biz_skel_gen, "biz"
            )

            # Handle URL-correction-exhausted cases
            for case in (single_failed or []):
                case["url"] = f"<URL not exist>{case.get('url', '')}"
                YamlWriter.write_single_case(case, output_dir)
                all_failures.append({
                    "case": case,
                    "reason": "URL correction exhausted",
                })
            for case in (biz_failed or []):
                for step in case.get("steps", []):
                    step["url"] = f"<URL not exist>{step.get('url', '')}"
                YamlWriter.write_biz_flow(case, output_dir)
                all_failures.append({
                    "case": case,
                    "reason": "URL correction exhausted",
                })

            self._save_checkpoint(ckpt_mgr, _SKELETON_PHASE, single_cases, biz_cases, all_failures, output_dir)
        else:
            logger.info("Step 1: Skeleton generation — SKIPPED (already completed)")

        # ================================================================
        # Step 2-N: Plugin execution (data filling, assertions, user plugins...)
        # ================================================================
        for i, plugin in enumerate(plugins):
            phase_name = f"plugin_{plugin.declaration.plugin_name}"
            if _phase_index(restart_phase) > _phase_index(phase_name):
                logger.info(
                    "Plugin '%s' — SKIPPED (phase %s already completed)",
                    plugin.declaration.plugin_name, phase_name,
                )
                continue

            decl = plugin.declaration
            logger.info("=" * 60)
            logger.info(
                "Plugin: %s (single=%s, biz=%s)",
                decl.plugin_name, decl.applies_to_single, decl.applies_to_biz,
            )
            logger.info("=" * 60)

            if decl.applies_to_single and single_cases:
                single_cases = self._apply_plugin(
                    plugin, single_cases, interfaces, api_summary, api_doc_text
                )
            if decl.applies_to_biz and biz_cases:
                biz_cases = self._apply_plugin(
                    plugin, biz_cases, interfaces, api_summary, api_doc_text
                )

            self._save_checkpoint(ckpt_mgr, phase_name, single_cases, biz_cases, all_failures, output_dir)

        # ================================================================
        # Final: URL safety-net check + YAML output
        # ================================================================
        if api_doc_text:
            self._final_url_check(single_cases, api_doc_text)
            self._final_url_check(biz_cases, api_doc_text)

        for case in single_cases:
            YamlWriter.write_single_case(case, output_dir)
        for case in biz_cases:
            YamlWriter.write_biz_flow(case, output_dir)

        if all_failures:
            logger.warning("%d cases had URL correction failures", len(all_failures))
            print(_("batch_controller.url_failures", count=len(all_failures)))
            YamlWriter.write_failures(all_failures, output_dir)

        return {
            "single_cases": single_cases,
            "biz_flows": biz_cases,
            "failures": all_failures,
        }

    # ------------------------------------------------------------------
    # URL check + correction
    # ------------------------------------------------------------------

    def _url_check_and_correct(
        self,
        skeletons: List[Dict],
        interfaces: List[Dict],
        api_doc_text: str,
        api_summary: Optional[List[Dict]],
        agent: Any,
        batch_type: str,
    ) -> Tuple[List[Dict], List[Dict]]:
        """Validate skeleton URLs and retry correction via LLM.

        Returns (valid_cases, failed_cases).
        """
        if not api_doc_text:
            return skeletons, []

        max_retries = self._url_correction_max_retries
        current = list(skeletons)

        for retry in range(max_retries + 1):
            bad_cases = []
            for case in current:
                urls = []
                if batch_type == "single":
                    urls = [str(case.get("url", "")).strip()]
                else:
                    urls = [str(s.get("url", "")).strip() for s in case.get("steps", [])]
                for url in urls:
                    if url and url not in api_doc_text:
                        bad_cases.append(case)
                        break

            if not bad_cases:
                logger.info("URL check passed for all %d %s skeletons", len(current), batch_type)
                return current, []

            if retry >= max_retries:
                bad_ids = set()
                for c in bad_cases:
                    key = c.get("test_id") if batch_type == "single" else c.get("sheet_name", "")
                    bad_ids.add(key)
                valid, failed = [], []
                for c in current:
                    key = c.get("test_id") if batch_type == "single" else c.get("sheet_name", "")
                    (failed if key in bad_ids else valid).append(c)
                logger.warning(
                    "URL correction exhausted for %d %s cases after %d retries",
                    len(failed), batch_type, max_retries,
                )
                return valid, failed

            logger.info(
                "URL correction retry %d/%d: %d %s cases with invalid URLs",
                retry + 1, max_retries, len(bad_cases), batch_type,
            )

            try:
                corrected = agent.correct_urls(bad_cases, interfaces, api_doc_text, api_summary)
                if corrected:
                    key_field = "test_id" if batch_type == "single" else "sheet_name"
                    corrected_map = {c.get(key_field, ""): c for c in corrected}
                    current = [corrected_map.get(c.get(key_field, ""), c) for c in current]
            except Exception as e:
                logger.warning("URL correction LLM call failed: %s", e)
                if retry >= max_retries - 1:
                    return self._split_good_bad(current, bad_cases, batch_type)

        return current, []

    @staticmethod
    def _split_good_bad(
        skeletons: List[Dict], bad_cases: List[Dict], batch_type: str
    ) -> Tuple[List[Dict], List[Dict]]:
        key_field = "test_id" if batch_type == "single" else "sheet_name"
        bad_ids = {c.get(key_field, "") for c in bad_cases}
        valid, failed = [], []
        for c in skeletons:
            (failed if c.get(key_field, "") in bad_ids else valid).append(c)
        return valid, failed

    @staticmethod
    def _final_url_check(cases: List[Dict], api_doc_text: str) -> None:
        """Last-resort URL check before writing output."""
        for case in cases:
            if isinstance(case.get("steps"), list):
                for step in case["steps"]:
                    url = str(step.get("url", "")).strip()
                    if url and url not in api_doc_text:
                        step["url"] = f"<URL not exist>{url}"
            else:
                url = str(case.get("url", "")).strip()
                if url and url not in api_doc_text:
                    case["url"] = f"<URL not exist>{url}"

    # ------------------------------------------------------------------
    # Plugin execution
    # ------------------------------------------------------------------

    def _apply_plugin(
        self,
        plugin: CaseAttributeGenerator,
        cases: List[Dict],
        interfaces: List[Dict],
        api_summary: List[Dict],
        api_doc_text: str,
    ) -> List[Dict]:
        """Run a plugin across all cases with batching and retry support."""
        decl = plugin.declaration
        batches = self._split_batches(cases)
        results: List[Dict] = []
        consecutive_failures = 0

        for i, batch in enumerate(batches):
            batch_ok = False
            for attempt in range(decl.max_retries):
                try:
                    updated = plugin.generate(batch, interfaces, api_summary, api_doc_text)
                    results.extend(updated)
                    batch_ok = True
                    break
                except Exception:
                    if attempt + 1 >= decl.max_retries:
                        if decl.error_strategy == "fail":
                            raise
                        elif decl.error_strategy == "warn":
                            logger.warning(
                                "Plugin '%s' failed after %d retries — keeping original",
                                decl.plugin_name, decl.max_retries,
                            )
                            results.extend(batch)
                        else:
                            results.extend(batch)
                    else:
                        logger.info("Plugin '%s' retry %d/%d", decl.plugin_name, attempt + 1, decl.max_retries)

            if batch_ok:
                consecutive_failures = 0
            else:
                consecutive_failures += 1
                if self._check_consecutive_failures(consecutive_failures, f"plugin '{decl.plugin_name}'"):
                    break

            self._maybe_wait_between_batches(i, len(batches))

        logger.info("Plugin '%s': processed %d cases", decl.plugin_name, len(results))
        return results

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    def _save_checkpoint(self, ckpt_mgr, phase: str, single: List, biz: List, failures: List, output_dir: str):
        """Save checkpoint data and metadata."""
        if not ckpt_mgr:
            return
        ckpt_mgr.save_data(phase, {
            "single_cases": single,
            "biz_cases": biz,
            "failures": failures,
        })
        ckpt_mgr.save_meta(
            phase, self._collect_settings(),
            {"single_cases": len(single), "biz_cases": len(biz)},
            output_dir,
        )

    def _check_consecutive_failures(self, consecutive: int, label: str) -> bool:
        limit = self._consecutive_failure_limit
        if limit < 0:
            return False
        if consecutive >= limit:
            logger.warning("Stopping [%s]: %d consecutive failures (limit=%d)", label, consecutive, limit)
            return True
        return False

    def _maybe_wait_between_batches(self, batch_idx: int, total: int):
        if batch_idx < total - 1 and self._rate_limit_delay > 0:
            logger.info("Waiting %.1fs before next batch", self._rate_limit_delay)
            time.sleep(self._rate_limit_delay)

    def _split_batches(self, items: List) -> List[List]:
        if self._batch_size == -1:
            return [items]
        return [items[i:i + self._batch_size] for i in range(0, len(items), self._batch_size)]

    def _collect_settings(self) -> Dict[str, Any]:
        return {
            "batch_size": self._batch_size,
            "enable_validation": self._enable_validation,
            "max_validation_retries": self._max_validation_retries,
            "url_correction_max_retries": self._url_correction_max_retries,
        }
