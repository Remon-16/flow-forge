"""BatchController — 基于插件的测试用例分批生成编排器。

Plugin-based test case generation orchestrator.
流程: 骨架生成 → URL校验 → 插件执行（数据填充/断言生成/用户插件） → 输出
"""

import logging
import time
from typing import Any, Dict, List, Optional, Tuple

from plugins.base import CaseAttributeGenerator

from config.settings import Settings, get_strategy, get_url_failure_action
from flow_forge_schemas import URL_NOT_EXIST_PREFIX
from i18n import _
from writers.yaml_writer import YamlWriter

logger = logging.getLogger(__name__)

_SKELETON_PHASE = "skeletons_generated"


class BatchController:
    """基于插件的测试用例分批生成编排器。

    Plugin-based test case generation orchestrator.
    骨架生成后按顺序遍历插件列表，每个插件处理 single/biz 用例。
    """

    def __init__(self, settings: Settings):
        self._batch_size = settings.plugin_batch_size
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
        # 校验规则列表 / Validation rules list
        self._validation_rules = getattr(settings, "validation_rules", [])
        self._url_failure_action = get_url_failure_action(self._validation_rules)
        self._reference_dir = ""
        self._memory_dir = ""

    # ------------------------------------------------------------------
    # 公开入口 / Public entry point
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
        case_type: str = "both",
    ) -> Dict[str, Any]:
        """执行完整的用例生成流水线 / Run the full generation pipeline.

        返回: {"single_cases": [...], "biz_flows": [...], "failures": [...]}
        """
        # === 初始化 / Setup ===
        self._reference_dir = reference_dir
        self._memory_dir = memory_dir
        all_failures: List[Dict] = []

        from graph.checkpoint import CheckpointManager as _CkptMgr
        ckpt_mgr = _CkptMgr(memory_dir) if memory_dir else None

        # 构建阶段列表：骨架 → 每个插件一个阶段
        # Build phase list: skeleton → one phase per plugin
        plugin_names = [p.declaration.plugin_name for p in plugins]
        phases = [_SKELETON_PHASE] + [f"plugin_{n}" for n in plugin_names]
        self._phases = phases

        # === 断点续跑：加载检查点并恢复状态 / Resume: load checkpoint and restore state ===
        restart_phase = _SKELETON_PHASE
        single_cases: List[Dict] = []
        biz_cases: List[Dict] = []

        if resume and ckpt_mgr and ckpt_mgr.exists():
            meta = ckpt_mgr.load_meta()
            if meta:
                restart_phase, single_cases, biz_cases, all_failures = \
                    self._restore_from_checkpoint(ckpt_mgr, meta)
            else:
                logger.warning(_("batch_controller.resume_invalid"))
        elif resume:
            logger.warning(_("batch_controller.resume_none"))

        # === 步骤1：骨架生成 + URL校验 + 纠正 / Step 1: Skeleton generation + URL check + correction ===
        if restart_phase == _SKELETON_PHASE:
            logger.info("=" * 60)
            logger.info(_("batch_controller.step_skeleton"))
            logger.info("=" * 60)
            single_cases, biz_cases, all_failures = self._run_skeleton_phase(
                plan, interfaces, api_doc_text, api_summary,
                single_skel_gen, biz_skel_gen, user_guidance, case_type,
                output_dir, all_failures, ckpt_mgr, phases)
        else:
            logger.info(_("batch_controller.step_skeleton_skipped"))

        # === 步骤2-N：插件执行（数据填充/断言生成/用户插件）/ Step 2-N: Plugin execution ===
        single_cases, biz_cases, all_failures = self._run_plugin_phase(
            plugins, restart_phase, single_cases, biz_cases, all_failures,
            interfaces, api_summary, api_doc_text, ckpt_mgr, output_dir, phases)

        # === 最终步骤：URL 兜底校验 + YAML 输出 / Final: URL safety-net check + YAML output ===
        return self._finalize_and_output(
            single_cases, biz_cases, all_failures, api_doc_text, output_dir)

    # ------------------------------------------------------------------
    # 步骤实现 / Step implementations
    # ------------------------------------------------------------------

    def _run_skeleton_phase(
        self,
        plan,
        interfaces: List[Dict],
        api_doc_text: str,
        api_summary: Optional[List[Dict]],
        single_skel_gen: Any,
        biz_skel_gen: Any,
        user_guidance: str,
        case_type: str,
        output_dir: str,
        all_failures: List[Dict],
        ckpt_mgr: Any,
        phases: List[str],
    ) -> Tuple[List[Dict], List[Dict], List[Dict]]:
        """步骤1：骨架生成 + URL 校验 + 纠正 / Step 1: Skeleton generation + URL check + correction.

        Returns (single_cases, biz_cases, all_failures).
        """
        # 1a. 单接口用例骨架 / Single case skeletons
        if case_type in ("both", "single"):
            logger.info(_("batch_controller.skeleton_generating_single"))
            single_skels = single_skel_gen.generate(
                plan, interfaces, api_summary, user_guidance
            )
            logger.info(_("batch_controller.skeleton_generated_single", count=len(single_skels)))
        else:
            logger.info(_("batch_controller.skeleton_skip_single_case_type", case_type=case_type))
            single_skels = []

        # 1b. 业务链路骨架 / Biz flow skeletons
        if case_type in ("both", "biz"):
            logger.info(_("batch_controller.skeleton_generating_biz"))
            biz_skels = []
            if hasattr(plan, "biz_flow_scenarios") and plan.biz_flow_scenarios:
                biz_skels = biz_skel_gen.generate(
                    plan, interfaces, api_summary, user_guidance
                )
                logger.info(_("batch_controller.skeleton_generated_biz", count=len(biz_skels)))
            else:
                logger.info(_("batch_controller.skeleton_skip_biz"))
        else:
            logger.info(_("batch_controller.skeleton_skip_biz_case_type", case_type=case_type))
            biz_skels = []

        # 1c. URL 校验 + 纠正 / URL check + correction
        single_cases, single_failed = self._url_check_and_correct(
            single_skels, interfaces, api_doc_text, api_summary,
            single_skel_gen, "single"
        )
        biz_cases, biz_failed = self._url_check_and_correct(
            biz_skels, interfaces, api_doc_text, api_summary,
            biz_skel_gen, "biz"
        )

        # 根据 url_failure_action 决定丢弃或保留 / Discard or keep based on url_failure_action
        if self._url_failure_action == "keep":
            single_cases, biz_cases = self._handle_url_failures_keep(
                single_failed, biz_failed, single_cases, biz_cases)
        else:
            all_failures = self._handle_url_failures_discard(
                single_failed, biz_failed, output_dir, all_failures)

        self._save_checkpoint(ckpt_mgr, _SKELETON_PHASE, single_cases, biz_cases,
                              all_failures, output_dir, phases=phases)
        return single_cases, biz_cases, all_failures

    def _run_plugin_phase(
        self,
        plugins: List[CaseAttributeGenerator],
        restart_phase: str,
        single_cases: List[Dict],
        biz_cases: List[Dict],
        all_failures: List[Dict],
        interfaces: List[Dict],
        api_summary: Optional[List[Dict]],
        api_doc_text: str,
        ckpt_mgr: Any,
        output_dir: str,
        phases: List[str],
    ) -> Tuple[List[Dict], List[Dict], List[Dict]]:
        """步骤2-N：遍历插件逐个执行 / Step 2-N: Iterate plugins and execute each.

        Returns (single_cases, biz_cases, all_failures).
        """
        def _idx(p: str) -> int:
            try:
                return phases.index(p)
            except ValueError:
                return -1

        for plugin in plugins:
            phase_name = f"plugin_{plugin.declaration.plugin_name}"
            if _idx(restart_phase) > _idx(phase_name):
                logger.info(
                    _("batch_controller.plugin_skipped",
                      name=plugin.declaration.plugin_name, phase=phase_name),
                )
                continue

            decl = plugin.declaration
            logger.info("=" * 60)
            logger.info(
                _("batch_controller.plugin_header",
                  name=decl.plugin_name, single=decl.applies_to_single, biz=decl.applies_to_biz),
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

            self._save_checkpoint(ckpt_mgr, phase_name, single_cases, biz_cases,
                                  all_failures, output_dir, phases=phases)

        return single_cases, biz_cases, all_failures

    # ------------------------------------------------------------------
    # URL 校验 + 纠正 / URL check + correction
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
        """校验骨架 URL 并尝试 LLM 修正 / Validate skeleton URLs and retry correction via LLM.

        Returns (valid_cases, failed_cases).
        """
        # 查询 URL 校验策略 / Query URL check strategy
        url_strategy = get_strategy(self._validation_rules, "url_check")

        # skip 策略：完全跳过 URL 校验 / Skip strategy: bypass entirely
        if url_strategy == "skip":
            logger.info(_("batch_controller.url_check_skipped",
                        count=len(skeletons), type=batch_type))
            return skeletons, []

        # 无 API 文档文本时跳过 / Skip when no API doc text
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
                logger.info(_("batch_controller.url_passed", count=len(current), type=batch_type))
                return current, []

            if retry >= max_retries:
                # fail 策略：抛异常终止 / Fail strategy: raise error
                if url_strategy == "fail":
                    raise ValueError(
                        f"URL check failed for {len(bad_cases)} {batch_type} cases "
                        f"after {max_retries} retries"
                    )
                # warn 策略：拆分为 valid/failed，failed 添加前缀
                # Warn strategy: split valid/failed, prefix failed URLs
                bad_ids = set()
                for c in bad_cases:
                    key = c.get("test_id") if batch_type == "single" else c.get("sheet_name", "")
                    bad_ids.add(key)
                valid, failed = [], []
                for c in current:
                    key = c.get("test_id") if batch_type == "single" else c.get("sheet_name", "")
                    (failed if key in bad_ids else valid).append(c)
                logger.warning(
                    _("batch_controller.url_exhausted",
                      count=len(failed), type=batch_type, retries=max_retries),
                )
                return valid, failed

            logger.info(
                _("batch_controller.url_correction_retry",
                  retry=retry + 1, max=max_retries, count=len(bad_cases), type=batch_type),
            )

            try:
                corrected = agent.correct_urls(bad_cases, interfaces, api_doc_text, api_summary)
                if corrected:
                    key_field = "test_id" if batch_type == "single" else "sheet_name"
                    corrected_map = {c.get(key_field, ""): c for c in corrected}
                    current = [corrected_map.get(c.get(key_field, ""), c) for c in current]
            except Exception as e:
                logger.warning(_("batch_controller.url_correction_llm_error", error=str(e)))
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
        """最终兜底 URL 校验——写入输出前的最后检查，跳过已有前缀的 URL。
        Last-resort URL check before writing output. Skips URLs that already have
        the URL_NOT_EXIST_PREFIX to avoid double-prefixing.
        """
        for case in cases:
            if isinstance(case.get("steps"), list):
                for step in case["steps"]:
                    url = str(step.get("url", "")).strip()
                    if url and url not in api_doc_text and not url.startswith(URL_NOT_EXIST_PREFIX):
                        step["url"] = f"{URL_NOT_EXIST_PREFIX}{url}"
            else:
                url = str(case.get("url", "")).strip()
                if url and url not in api_doc_text and not url.startswith(URL_NOT_EXIST_PREFIX):
                    case["url"] = f"{URL_NOT_EXIST_PREFIX}{url}"

    def _handle_url_failures_keep(
        self,
        single_failed: List[Dict],
        biz_failed: List[Dict],
        single_cases: List[Dict],
        biz_cases: List[Dict],
    ) -> Tuple[List[Dict], List[Dict]]:
        """保留 URL 校验失败用例：添加前缀标记并合并回有效列表。
        Keep URL-check-failed cases: add prefix marker and merge back to valid lists.
        """
        for case in (single_failed or []):
            case["url"] = f"{URL_NOT_EXIST_PREFIX}{case.get('url', '')}"
        for case in (biz_failed or []):
            for step in case.get("steps", []):
                step["url"] = f"{URL_NOT_EXIST_PREFIX}{step.get('url', '')}"
        if single_failed:
            logger.info(_("batch_controller.url_failure_keep",
                          count=len(single_failed), type="single"))
            single_cases.extend(single_failed)
        if biz_failed:
            logger.info(_("batch_controller.url_failure_keep",
                          count=len(biz_failed), type="biz"))
            biz_cases.extend(biz_failed)
        return single_cases, biz_cases

    def _handle_url_failures_discard(
        self,
        single_failed: List[Dict],
        biz_failed: List[Dict],
        output_dir: str,
        all_failures: List[Dict],
    ) -> List[Dict]:
        """丢弃 URL 校验失败用例：添加前缀标记，写入 failures.yaml。
        Discard URL-check-failed cases: add prefix marker, write to failures.yaml.
        """
        for case in (single_failed or []):
            case["url"] = f"{URL_NOT_EXIST_PREFIX}{case.get('url', '')}"
            YamlWriter.write_single_case(case, output_dir)
            all_failures.append({"case": case, "reason": "URL correction exhausted"})
        for case in (biz_failed or []):
            for step in case.get("steps", []):
                step["url"] = f"{URL_NOT_EXIST_PREFIX}{step.get('url', '')}"
            YamlWriter.write_biz_flow(case, output_dir)
            all_failures.append({"case": case, "reason": "URL correction exhausted"})
        return all_failures

    # ------------------------------------------------------------------
    # 插件执行 / Plugin execution
    # ------------------------------------------------------------------

    def _apply_plugin(
        self,
        plugin: CaseAttributeGenerator,
        cases: List[Dict],
        interfaces: List[Dict],
        api_summary: List[Dict],
        api_doc_text: str,
    ) -> List[Dict]:
        """对一批用例执行单个插件，含分批和重试 / Run a plugin across all cases with batching and retry."""
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
                                _("batch_controller.plugin_failed_after_retries",
                                  name=decl.plugin_name, retries=decl.max_retries),
                            )
                            results.extend(batch)
                        else:
                            results.extend(batch)
                    else:
                        logger.info(_("batch_controller.plugin_retry",
                                    name=decl.plugin_name, attempt=attempt + 1, max=decl.max_retries))

            if batch_ok:
                consecutive_failures = 0
            else:
                consecutive_failures += 1
                if self._check_consecutive_failures(consecutive_failures, f"plugin '{decl.plugin_name}'"):
                    break

            self._maybe_wait_between_batches(i, len(batches))

        logger.info(_("batch_controller.plugin_result", name=decl.plugin_name, count=len(results)))
        return results

    # ------------------------------------------------------------------
    # 辅助方法 / Helpers
    # ------------------------------------------------------------------

    def _restore_from_checkpoint(
        self,
        ckpt_mgr: Any,
        meta: Dict,
    ) -> Tuple[str, List[Dict], List[Dict], List[Dict]]:
        """从有效检查点恢复设置和用例数据 / Restore settings and case data from valid checkpoint.

        Returns (restart_phase, single_cases, biz_cases, all_failures).
        """
        from graph.checkpoint import CheckpointManager as _CkptMgr

        restart_phase = _CkptMgr.get_restart_phase(meta)
        logger.info(_("batch_controller.resume_phase", phase=restart_phase))

        ckpt_settings = meta.get("settings", {})
        if ckpt_settings:
            self._batch_size = ckpt_settings.get("batch_size", self._batch_size)
            self._enable_validation = ckpt_settings.get(
                "enable_validation", self._enable_validation)
            self._max_validation_retries = ckpt_settings.get(
                "max_validation_retries", self._max_validation_retries)
            self._url_correction_max_retries = ckpt_settings.get(
                "url_correction_max_retries", self._url_correction_max_retries)

        data = ckpt_mgr.load_data()
        single_cases: List[Dict] = data.get("single_cases", []) if data else []
        biz_cases: List[Dict] = data.get("biz_cases", []) if data else []
        all_failures: List[Dict] = data.get("failures", []) if data else []

        if data:
            logger.info(_("batch_controller.resume_restored",
                          single=len(single_cases), biz=len(biz_cases)))

        return restart_phase, single_cases, biz_cases, all_failures

    def _finalize_and_output(
        self,
        single_cases: List[Dict],
        biz_cases: List[Dict],
        all_failures: List[Dict],
        api_doc_text: str,
        output_dir: str,
    ) -> Dict[str, Any]:
        """最终 URL 兜底校验 + YAML 输出 / Final URL safety-net check + YAML output."""
        if api_doc_text:
            self._final_url_check(single_cases, api_doc_text)
            self._final_url_check(biz_cases, api_doc_text)

        for case in single_cases:
            YamlWriter.write_single_case(case, output_dir)
        for case in biz_cases:
            YamlWriter.write_biz_flow(case, output_dir)

        if all_failures:
            logger.warning(_("batch_controller.url_failures", count=len(all_failures)))
            YamlWriter.write_failures(all_failures, output_dir)

        return {
            "single_cases": single_cases,
            "biz_flows": biz_cases,
            "failures": all_failures,
        }

    def _save_checkpoint(self, ckpt_mgr, phase: str, single: List, biz: List,
                         failures: List, output_dir: str, phases: List[str] = None):
        """保存检查点数据和元数据 / Save checkpoint data and metadata."""
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
            phases=phases,
        )

    def _check_consecutive_failures(self, consecutive: int, label: str) -> bool:
        limit = self._consecutive_failure_limit
        if limit < 0:
            return False
        if consecutive >= limit:
            logger.warning(_("batch_controller.consecutive_failures",
                            label=label, n=consecutive, limit=limit))
            return True
        return False

    def _maybe_wait_between_batches(self, batch_idx: int, total: int):
        if batch_idx < total - 1 and self._rate_limit_delay > 0:
            logger.info(_("batch_controller.wait_between_batches", delay=self._rate_limit_delay))
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
            "validation_rules": self._validation_rules,
        }
