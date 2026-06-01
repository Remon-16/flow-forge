"""PipelineOrchestrator — two-phase pipeline: plan → confirm → excel."""

import logging
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional

from .state import PipelineState
from agents.api_parser import ApiParser
from agents.base import ConvergenceError
from agents.case_generator import CaseGenerator
from agents.excel_writer import ExcelWriter
from agents.plan_generator import PlanGenerator
from agents.plan_parser import PlanParser
from agents.requirement_analyzer import RequirementAnalyzer
from config.settings import Settings
from doc_parser.pdf_parser import PdfParser
from knowledge.rag import RAGKnowledgeBase

logger = logging.getLogger(__name__)


class PipelineOrchestrator:
    """Orchestrates the two-phase test case generation pipeline.

    Phase 1: Read docs → analyze → generate plan.md
    (User reviews and confirms the plan)
    Phase 2: Parse plan → generate cases → write Excel
    """

    def __init__(self, settings: Settings):
        self._settings = settings
        self._rag = RAGKnowledgeBase(settings.knowledge_db_path)
        self._rag.initialize()

    def run_phase1(
        self, requirement_paths: List[str], api_path: str
    ) -> PipelineState:
        """Phase 1: generate test plan from requirements + API docs.

        Returns PipelineState with plan_md filled.
        """
        state = PipelineState(
            phase="plan_generation",
            requirement_paths=requirement_paths,
            api_path=api_path,
        )

        try:
            # 1. Parse requirement documents
            state.requirement_text = self._read_requirements(requirement_paths)
            logger.info("Read %d chars of requirement text", len(state.requirement_text))

            # 2. Parse API documentation
            state.interfaces = ApiParser.parse(api_path)
            logger.info("Parsed %d interface definitions", len(state.interfaces))

            # 3. Analyze requirements
            analyzer = RequirementAnalyzer(self._settings, self._rag)
            state.requirement_analysis = analyzer.analyze(state.requirement_text)

            # 4. Generate test plan
            generator = PlanGenerator(self._settings, self._rag)
            state.plan_md = generator.generate(
                state.requirement_analysis, state.interfaces
            )

            # 5. Save plan to file
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            plan_path = f"plan_{timestamp}.md"
            with open(plan_path, "w", encoding="utf-8") as f:
                f.write(state.plan_md)
            state.plan_md_path = plan_path
            state.phase = "plan_generated"

            logger.info("Phase 1 complete. Plan saved to %s", plan_path)

        except Exception as e:
            state.add_error(f"Phase 1 error: {e}")
            logger.exception("Phase 1 failed")

        return state

    def run_phase2(self, plan_md: str, api_path: str) -> PipelineState:
        """Phase 2: generate Excel from confirmed plan.

        Accepts either a path to plan.md or the plan content directly.
        """
        state = PipelineState(
            phase="case_generation",
            api_path=api_path,
        )

        try:
            # Read plan if given a file path
            plan_path = Path(plan_md)
            if plan_path.exists() and plan_path.is_file():
                with open(plan_path, "r", encoding="utf-8") as f:
                    state.plan_md = f.read()
                state.plan_md_path = str(plan_path)
            else:
                state.plan_md = plan_md

            # 1. Parse API docs
            state.interfaces = ApiParser.parse(api_path)
            logger.info("Parsed %d interface definitions", len(state.interfaces))

            # 2. Parse plan into structured TestPlan
            parser = PlanParser(self._settings)
            test_plan = parser.parse(state.plan_md)
            logger.info("Parsed test plan from markdown")

            # 3. Generate concrete test cases
            case_gen = CaseGenerator(self._settings, self._rag)
            cases = case_gen.generate(test_plan, state.interfaces)
            state.single_cases = cases["single_cases"]
            state.biz_flows = cases["biz_flows"]

            state.phase = "cases_generated"
            logger.info("Phase 2 complete")

        except Exception as e:
            state.add_error(f"Phase 2 error: {e}")
            logger.exception("Phase 2 failed")

        return state

    def run_full(
        self,
        requirement_paths: List[str],
        api_path: str,
        output_path: str,
    ) -> PipelineState:
        """Full pipeline: requirement → plan → cases → Excel (no confirmation step)."""
        # Phase 1
        state = self.run_phase1(requirement_paths, api_path)
        if state.errors:
            return state

        # Phase 2
        state2 = self.run_phase2(state.plan_md, api_path)
        state.single_cases = state2.single_cases
        state.biz_flows = state2.biz_flows
        state.errors.extend(state2.errors)
        state.phase = "cases_generated"

        if state.errors:
            return state

        # Write Excel
        try:
            ExcelWriter.write(
                state.interfaces,
                state.single_cases,
                state.biz_flows,
                output_path,
            )
            state.excel_path = output_path
            state.converged = True
            logger.info("Full pipeline complete. Output: %s", output_path)
        except Exception as e:
            state.add_error(f"Excel write error: {e}")
            logger.exception("Excel write failed")

        return state

    @staticmethod
    def _read_requirements(paths: List[str]) -> str:
        """Read requirement documents from multiple paths.

        Supports .txt, .md, .pdf files.
        """
        texts = []
        for path in paths:
            p = Path(path)
            if not p.exists():
                logger.warning("Requirement file not found: %s", path)
                continue

            files = []
            if p.is_dir():
                for ext in ("*.txt", "*.md", "*.pdf"):
                    files.extend(p.glob(ext))
            else:
                files = [p]

            for f in files:
                suffix = f.suffix.lower()
                if suffix == ".pdf":
                    texts.append(PdfParser.parse(str(f)))
                else:
                    with open(f, "r", encoding="utf-8") as fh:
                        texts.append(fh.read())

        return "\n\n".join(texts)
