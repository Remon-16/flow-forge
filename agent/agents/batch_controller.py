"""BatchController: orchestrates three-step test case generation.

Step 1: Skeleton generation (one-shot, no batching)
Step 2: Data filling (code-based batching)
Step 3: Assertion generation (code-based batching)

Batching is done by simple code splitting — no LLM involved in batch decisions.
"""

import json
import logging
import time
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from agents.base import BaseAgent, ConvergenceError
from config.settings import Settings
from writers.yaml_writer import YamlWriter
from validators.url_checker import check_url_existence

logger = logging.getLogger(__name__)


class BatchController(BaseAgent):
    """Orchestrates three-step test case generation.

    Reads from / writes to the YAML output directory. Uses code-based
    batch splitting (no LLM batch decisions).
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
        self._max_steps_no_progress = settings.max_steps_no_progress
        self._url_correction_max_retries = getattr(
            settings, "url_correction_max_retries", 3
        )
        self._enable_plugins = getattr(settings, "enable_plugins", False)
        self._plugin_modules = getattr(settings, "plugin_modules", "")
        self._consecutive_failure_limit = getattr(
            settings, "consecutive_batch_failure_limit", 3
        )
        self._reference_dir = ""

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
        single_data_filler: Any,
        biz_data_filler: Any,
        single_assert_gen: Any,
        biz_assert_gen: Any,
        validator: Any = None,
        user_guidance: str = "",
        reference_dir: str = "",
        api_doc_text: str = "",
        api_summary: Optional[List[Dict]] = None,
    ) -> Dict[str, Any]:
        """Run the three-step generation pipeline.

        Returns dict with:
          - single_cases: list of complete single case dicts
          - biz_flows: list of complete biz flow dicts
          - failures: list of cases that failed after all retries
        """
        self._reference_dir = reference_dir
        all_failures: List[Dict] = []

        # ================================================================
        # Step 1: Skeleton generation (one-shot) + URL check + correction
        # ================================================================
        logger.info("=" * 60)
        logger.info("Step 1: Skeleton generation")
        logger.info("=" * 60)

        # 1a. Single case skeletons
        logger.info("Generating single case skeletons...")
        single_skeletons = single_skel_gen.generate(
            plan, interfaces, api_summary, user_guidance
        )
        logger.info("Generated %d single case skeletons", len(single_skeletons))

        # 1b. Biz flow skeletons
        logger.info("Generating biz flow skeletons...")
        biz_skeletons = []
        if hasattr(plan, "biz_flow_scenarios") and plan.biz_flow_scenarios:
            biz_skeletons = biz_skel_gen.generate(
                plan, interfaces, api_summary, user_guidance
            )
            logger.info("Generated %d biz flow skeletons", len(biz_skeletons))
        else:
            logger.info("No biz flow scenarios in plan, skipping")

        # 1c. URL check + correction retry
        single_valid, single_url_failed = self._url_check_and_correct(
            single_skeletons, interfaces, api_doc_text, api_summary,
            single_skel_gen, "single"
        )
        biz_valid, biz_url_failed = self._url_check_and_correct(
            biz_skeletons, interfaces, api_doc_text, api_summary,
            biz_skel_gen, "biz"
        )

        # Handle URL-correction-exhausted cases: mark, skip, log
        if single_url_failed:
            for case in single_url_failed:
                case["url"] = f"<URL not exist>{case.get('url', '')}"
                YamlWriter.write_single_case(case, output_dir)
                all_failures.append({
                    "case": case,
                    "reason": "URL correction exhausted — URL not found in API doc",
                })
        if biz_url_failed:
            for case in biz_url_failed:
                for step in case.get("steps", []):
                    step["url"] = f"<URL not exist>{step.get('url', '')}"
                YamlWriter.write_biz_flow(case, output_dir)
                all_failures.append({
                    "case": case,
                    "reason": "URL correction exhausted — URL not found in API doc",
                })

        # ================================================================
        # Step 2: Data filling (code-based batching)
        # ================================================================
        logger.info("=" * 60)
        logger.info("Step 2: Data filling")
        logger.info("=" * 60)

        single_filled = self._run_data_filling_phase(
            single_valid, interfaces, api_summary, api_doc_text,
            user_guidance, "single", single_data_filler, validator
        )
        biz_filled = self._run_data_filling_phase(
            biz_valid, interfaces, api_summary, api_doc_text,
            user_guidance, "biz", biz_data_filler, validator
        )

        # ================================================================
        # Step 3: Assertion generation (code-based batching)
        # ================================================================
        logger.info("=" * 60)
        logger.info("Step 3: Assertion generation")
        logger.info("=" * 60)

        single_complete = self._run_assertion_phase(
            single_filled, interfaces, api_summary, user_guidance, "single",
            single_assert_gen, validator
        )
        biz_complete = self._run_assertion_phase(
            biz_filled, interfaces, api_summary, user_guidance, "biz",
            biz_assert_gen, validator
        )

        # ================================================================
        # Step 4: Custom plugin execution (optional)
        # ================================================================
        if self._enable_plugins and self._plugin_modules:
            logger.info("=" * 60)
            logger.info("Step 4: Custom plugin execution")
            logger.info("=" * 60)

            plugin_paths = [
                p.strip() for p in self._plugin_modules.split(",") if p.strip()
            ]
            from plugins.loader import load_plugins
            plugins = load_plugins(plugin_paths)

            for plugin in plugins:
                decl = plugin.declaration
                logger.info(
                    "Running plugin: %s (single=%s, biz=%s)",
                    decl.plugin_name,
                    decl.applies_to_single,
                    decl.applies_to_biz,
                )
                if decl.applies_to_single:
                    single_complete = self._apply_plugin(
                        plugin, single_complete, interfaces, api_summary, api_doc_text
                    )
                if decl.applies_to_biz:
                    biz_complete = self._apply_plugin(
                        plugin, biz_complete, interfaces, api_summary, api_doc_text
                    )

        # ================================================================
        # Final URL safety-net check before writing
        # ================================================================
        if api_doc_text:
            self._final_url_check(single_complete, api_doc_text)
            self._final_url_check(biz_complete, api_doc_text)

        # ================================================================
        # Save final YAML
        # ================================================================
        for case in single_complete:
            YamlWriter.write_single_case(case, output_dir)
        for case in biz_complete:
            YamlWriter.write_biz_flow(case, output_dir)

        # Print failure summary
        if all_failures:
            logger.warning(
                "BatchController: %d cases had URL correction failures",
                len(all_failures),
            )
            print(f"\n⚠ URL 纠错失败 {len(all_failures)} 个用例，已添加 <URL not exist> 标记，请手动修正：")
            for f in all_failures:
                case = f["case"]
                name = case.get("test_id") or case.get("sheet_name", "?")
                print(f"  - {name}: {f['reason']}")

        # Write failure log
        if all_failures:
            YamlWriter.write_failures(all_failures, output_dir)

        return {
            "single_cases": single_complete,
            "biz_flows": biz_complete,
            "failures": all_failures,
        }

    # ------------------------------------------------------------------
    # URL check + correction retry
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
        """Validate skeleton URLs and retry correction via LLM on failure.

        Returns:
            (valid_cases, failed_cases) — cases that passed (or were
            corrected) and cases that failed after all retries.
        """
        if not api_doc_text:
            return skeletons, []

        max_retries = self._url_correction_max_retries
        current = list(skeletons)

        for retry in range(max_retries + 1):
            # Find cases with bad URLs
            bad_cases = []
            for case in current:
                urls_to_check: List[str] = []
                if batch_type == "single":
                    urls_to_check = [str(case.get("url", "")).strip()]
                else:
                    urls_to_check = [
                        str(s.get("url", "")).strip()
                        for s in case.get("steps", [])
                    ]

                for url in urls_to_check:
                    if url and url not in api_doc_text:
                        bad_cases.append(case)
                        break

            if not bad_cases:
                logger.info("URL check passed for all %d %s skeletons", len(current), batch_type)
                return current, []

            if retry >= max_retries:
                # Retries exhausted — split into good and bad
                bad_ids = set()
                for c in bad_cases:
                    if batch_type == "single":
                        bad_ids.add(c.get("test_id", ""))
                    else:
                        bad_ids.add(c.get("sheet_name", ""))

                valid = []
                failed = []
                for c in current:
                    key = c.get("test_id") if batch_type == "single" else c.get("sheet_name", "")
                    if key in bad_ids:
                        failed.append(c)
                    else:
                        valid.append(c)

                logger.warning(
                    "URL correction exhausted for %d %s cases after %d retries",
                    len(failed), batch_type, max_retries,
                )
                return valid, failed

            # Attempt correction
            logger.info(
                "URL correction retry %d/%d: %d %s cases with invalid URLs",
                retry + 1, max_retries, len(bad_cases), batch_type,
            )

            try:
                corrected = agent.correct_urls(
                    bad_cases, interfaces, api_doc_text, api_summary
                )
                if corrected:
                    # Merge: replace bad cases with corrected versions
                    if batch_type == "single":
                        corrected_map = {c.get("test_id", ""): c for c in corrected}
                        new_list = []
                        for c in current:
                            key = c.get("test_id", "")
                            new_list.append(corrected_map.get(key, c))
                        current = new_list
                    else:
                        corrected_map = {c.get("sheet_name", ""): c for c in corrected}
                        new_list = []
                        for c in current:
                            key = c.get("sheet_name", "")
                            new_list.append(corrected_map.get(key, c))
                        current = new_list
            except Exception as e:
                logger.warning("URL correction LLM call failed: %s", e)
                # If correction call itself fails, treat as retry exhausted
                if retry >= max_retries - 1:
                    return self._split_good_bad(current, bad_cases, batch_type)

        return current, []

    @staticmethod
    def _split_good_bad(
        skeletons: List[Dict], bad_cases: List[Dict], batch_type: str
    ) -> Tuple[List[Dict], List[Dict]]:
        """Split skeletons into good (URL ok) and bad (URL still bad)."""
        if batch_type == "single":
            bad_ids = {c.get("test_id", "") for c in bad_cases}
        else:
            bad_ids = {c.get("sheet_name", "") for c in bad_cases}
        valid = []
        failed = []
        for c in skeletons:
            key = c.get("test_id") if batch_type == "single" else c.get("sheet_name", "")
            if key in bad_ids:
                failed.append(c)
            else:
                valid.append(c)
        return valid, failed

    # ------------------------------------------------------------------
    # Final URL safety-net check
    # ------------------------------------------------------------------

    @staticmethod
    def _final_url_check(cases: List[Dict], api_doc_text: str) -> None:
        """Last-resort URL check before writing. Adds marker to any URL
        that still fails validation — should rarely trigger."""
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
    # Phase runners (data filling / assertion generation)
    # ------------------------------------------------------------------

    def _run_data_filling_phase(
        self,
        skeletons: List[Dict],
        interfaces: List[Dict],
        api_summary: Optional[List[Dict]],
        api_doc_text: str,
        user_guidance: str,
        batch_type: str,
        filler: Any,
        validator: Any,
    ) -> List[Dict]:
        """Run data filling with code-based batching + optional validation."""
        if not skeletons:
            return []

        batches = self._split_batches(skeletons)
        logger.info(
            "Data filling [%s]: %d skeletons in %d batches (batch_size=%d)",
            batch_type, len(skeletons), len(batches), self._batch_size,
        )

        all_filled: List[Dict] = []
        consecutive_failures = 0
        for i, batch in enumerate(batches):
            logger.info("Data filling [%s] batch %d/%d: %d items",
                        batch_type, i + 1, len(batches), len(batch))
            try:
                filled = filler.fill_batch(
                    batch, interfaces, api_summary, api_doc_text, user_guidance
                )
            except ConvergenceError as e:
                consecutive_failures += 1
                logger.warning("Data filling [%s] converged at batch %d: %s", batch_type, i + 1, e)
                if self._check_consecutive_failures(consecutive_failures, batch_type):
                    break
                continue
            except Exception as e:
                consecutive_failures += 1
                logger.exception("Data filling [%s] failed for batch %d", batch_type, i + 1)
                if self._check_consecutive_failures(consecutive_failures, batch_type):
                    break
                continue

            consecutive_failures = 0

            if not filled:
                continue

            # Validate + retry
            if validator and self._enable_validation:
                validate_type = "single" if batch_type == "single" else "biz_flow"
                valid, invalid, errors = validator.validate(filled, validate_type)
                if invalid:
                    logger.info("Data filling [%s]: %d/%d invalid, retrying...",
                                batch_type, len(invalid), len(filled))
                    retry_valid, still_invalid, summary = validator.validate_with_retry(
                        case_generator=filler,
                        invalid_cases=invalid,
                        interfaces=interfaces,
                        test_points=None,
                        batch_type=batch_type,
                        max_retries=self._max_validation_retries,
                    )
                    filled = valid + retry_valid

            all_filled.extend(filled)

            # Batch 间延迟（最后一个 batch 不需要等）
            if i < len(batches) - 1 and self._rate_limit_delay > 0:
                logger.info("Waiting %.1fs before next batch", self._rate_limit_delay)
                time.sleep(self._rate_limit_delay)

        logger.info("Data filling [%s]: %d cases filled total", batch_type, len(all_filled))
        return all_filled

    def _run_assertion_phase(
        self,
        cases: List[Dict],
        interfaces: List[Dict],
        api_summary: Optional[List[Dict]],
        user_guidance: str,
        batch_type: str,
        assertion_gen: Any,
        validator: Any,
    ) -> List[Dict]:
        """Run assertion generation with code-based batching + optional validation."""
        if not cases:
            return []

        batches = self._split_batches(cases)
        logger.info(
            "Assertion generation [%s]: %d cases in %d batches (batch_size=%d)",
            batch_type, len(cases), len(batches), self._batch_size,
        )

        all_complete: List[Dict] = []
        consecutive_failures = 0
        for i, batch in enumerate(batches):
            logger.info("Assertion generation [%s] batch %d/%d: %d items",
                        batch_type, i + 1, len(batches), len(batch))
            try:
                complete = assertion_gen.fill_batch(
                    batch, interfaces, api_summary, user_guidance
                )
            except ConvergenceError as e:
                consecutive_failures += 1
                logger.warning("Assertion generation [%s] converged at batch %d: %s", batch_type, i + 1, e)
                if self._check_consecutive_failures(consecutive_failures, batch_type):
                    break
                continue
            except Exception as e:
                consecutive_failures += 1
                logger.exception("Assertion generation [%s] failed for batch %d", batch_type, i + 1)
                if self._check_consecutive_failures(consecutive_failures, batch_type):
                    break
                continue

            consecutive_failures = 0

            if not complete:
                continue

            # Validate + retry
            if validator and self._enable_validation:
                validate_type = "single" if batch_type == "single" else "biz_flow"
                valid, invalid, errors = validator.validate(complete, validate_type)
                if invalid:
                    logger.info("Assertion generation [%s]: %d/%d invalid, retrying...",
                                batch_type, len(invalid), len(complete))
                    retry_valid, still_invalid, summary = validator.validate_with_retry(
                        case_generator=assertion_gen,
                        invalid_cases=invalid,
                        interfaces=interfaces,
                        test_points=None,
                        batch_type=batch_type,
                        max_retries=self._max_validation_retries,
                    )
                    complete = valid + retry_valid

            all_complete.extend(complete)

            # Batch 间延迟（最后一个 batch 不需要等）
            if i < len(batches) - 1 and self._rate_limit_delay > 0:
                logger.info("Waiting %.1fs before next batch", self._rate_limit_delay)
                time.sleep(self._rate_limit_delay)

        logger.info("Assertion generation [%s]: %d cases completed", batch_type, len(all_complete))
        return all_complete

    # ------------------------------------------------------------------
    # Plugin execution
    # ------------------------------------------------------------------

    def _apply_plugin(
        self,
        plugin,
        cases: List[Dict],
        interfaces: List[Dict],
        api_summary: List[Dict],
        api_doc_text: str,
    ) -> List[Dict]:
        """Run a plugin across all cases, with batching and retry support."""
        decl = plugin.declaration
        batches = self._split_batches(cases)
        results: List[Dict] = []
        consecutive_failures = 0

        for i, batch in enumerate(batches):
            batch_ok = False
            for attempt in range(decl.max_retries):
                try:
                    updated = plugin.generate(
                        batch, interfaces, api_summary, api_doc_text
                    )
                    results.extend(updated)
                    batch_ok = True
                    break
                except Exception:
                    if attempt + 1 >= decl.max_retries:
                        if decl.error_strategy == "fail":
                            raise
                        elif decl.error_strategy == "warn":
                            logger.warning(
                                "Plugin '%s' failed on a batch after %d retries — keeping original cases",
                                decl.plugin_name, decl.max_retries,
                            )
                            results.extend(batch)
                        else:  # skip
                            results.extend(batch)
                    else:
                        logger.info(
                            "Plugin '%s' retry %d/%d",
                            decl.plugin_name, attempt + 1, decl.max_retries,
                        )

            if batch_ok:
                consecutive_failures = 0
            else:
                consecutive_failures += 1
                if self._check_consecutive_failures(consecutive_failures, f"plugin '{decl.plugin_name}'"):
                    break

            # Batch 间延迟
            if i < len(batches) - 1 and self._rate_limit_delay > 0:
                logger.info("Waiting %.1fs before next batch", self._rate_limit_delay)
                time.sleep(self._rate_limit_delay)

        logger.info(
            "Plugin '%s': processed %d cases", decl.plugin_name, len(results)
        )
        return results

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    def _check_consecutive_failures(self, consecutive: int, batch_type: str) -> bool:
        """Return True if batch processing should stop due to consecutive failures."""
        limit = self._consecutive_failure_limit
        if limit < 0:
            return False
        if consecutive >= limit:
            logger.warning(
                "Stopping [%s]: %d consecutive batch failures (limit=%d)",
                batch_type, consecutive, limit,
            )
            return True
        return False

    # ------------------------------------------------------------------
    # Code-based batch splitting
    # ------------------------------------------------------------------

    def _split_batches(self, items: List) -> List[List]:
        """Split items into batches by batch_size. -1 means no batching."""
        if self._batch_size == -1:
            return [items]
        return [items[i:i + self._batch_size] for i in range(0, len(items), self._batch_size)]
