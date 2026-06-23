from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from rich.console import Console

from src.config import LiteratureSurveyConfig
from src.literature_survey import (
    collect_papers,
    generate_related_work,
    run_literature_survey_mode,
)
from src.project_input import load_project_input


class LiteratureSurveyTests(unittest.TestCase):
    def test_survey_collects_deduplicates_and_writes_structured_outputs(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            project_dir = root / "projects" / "survey_demo"
            run_dir = project_dir / "runs" / "run-1" / "round_01"
            run_dir.mkdir(parents=True)
            (project_dir / "task.md").write_text(
                """# Memory-Agent Literature Survey

| Title | Authors | Year | Venue | Topics | Methods | Benchmarks | Datasets | Limitations | Future Work | URL |
|---|---|---:|---|---|---|---|---|---|---|---|
| MemGPT: Towards LLMs as Operating Systems | Packer et al. | 2023 | arXiv | memory; agent | retrieval; prompting | human evaluation | | Context-window pressure remains a limitation | Better long-horizon benchmarks | https://arxiv.org/abs/2310.08560 |
| Privacy Attacks for Long-Term Agent Memory | Doe and Roe | 2025 | Workshop | privacy; memory | simulation; differential privacy | attack success rate; F1 | Persona-Chat | Synthetic users may miss real preference drift | Open problem: realistic longitudinal data |
""",
                encoding="utf-8",
            )
            (project_dir / "memory.md").write_text(
                """## References

- [MemGPT: Towards LLMs as Operating Systems](https://arxiv.org/abs/2310.08560) (2023).
- Shokri et al. (2017). Membership Inference Attacks Against Machine Learning Models. IEEE S&P. https://example.org/membership-inference
""",
                encoding="utf-8",
            )
            (run_dir / "03_revised.md").write_text(
                """Title: MemoryAgentBench: Evaluating Long-Term Agent Memory
Authors: Example Author
Year: 2024
Venue: Benchmark Track
Topics: memory, evaluation, agent
Methods: simulation, retrieval
Benchmarks: F1, human evaluation
Datasets: DailyDialog
Limitations: Limited multilingual coverage
Future Work: Add privacy stress tests
""",
                encoding="utf-8",
            )

            project_input = load_project_input(
                root=root,
                project_name="survey_demo",
                explicit_project=True,
            )
            result = run_literature_survey_mode(
                console=Console(),
                project_input=project_input,
                config=LiteratureSurveyConfig(),
            )

            self.assertEqual(len(result.papers), 4)
            self.assertTrue(result.report_path.exists())
            self.assertTrue(result.metadata_path.exists())
            self.assertTrue(result.related_work_path.exists())
            self.assertTrue(result.manifest_path.exists())

            report = result.report_path.read_text(encoding="utf-8")
            self.assertIn("## Executive Summary", report)
            self.assertIn("## Metadata Quality", report)
            self.assertIn("## Research Landscape", report)
            self.assertIn("## Major Themes", report)
            self.assertIn("## Comparison Tables", report)
            self.assertIn("## Research Gaps", report)
            self.assertIn("## Future Directions", report)
            self.assertIn("## Related Work Draft", report)

            metadata = json.loads(result.metadata_path.read_text(encoding="utf-8"))
            self.assertEqual(metadata["paper_count"], 4)
            self.assertIn("metadata_quality", metadata)
            self.assertIn("representative_groups", metadata)
            titles = {paper["title"] for paper in metadata["papers"]}
            self.assertIn("MemoryAgentBench: Evaluating Long-Term Agent Memory", titles)
            self.assertIn("Membership Inference Attacks Against Machine Learning Models", titles)

            manifest = json.loads(result.manifest_path.read_text(encoding="utf-8"))
            self.assertIn("source_summary", manifest)
            self.assertIn("metadata_quality", manifest)

    def test_collection_respects_configured_limits_and_related_work_fallback(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            project_dir = root / "projects" / "empty"
            project_dir.mkdir(parents=True)
            (project_dir / "task.md").write_text(
                "# Empty Survey\nNo papers yet.\n", encoding="utf-8"
            )

            papers, source_files = collect_papers(
                project_dir,
                LiteratureSurveyConfig(max_source_files=1, max_papers=1),
            )

            self.assertEqual(source_files, [(project_dir / "task.md").resolve()])
            self.assertEqual(papers, [])
            self.assertIn("no paper metadata", generate_related_work(papers).lower())

    def test_reference_metadata_and_identifier_aliases_are_normalized(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            project_dir = root / "projects" / "survey_demo"
            run_dir = project_dir / "runs" / "run-1" / "round_01"
            run_dir.mkdir(parents=True)
            (project_dir / "task.md").write_text(
                """# Survey

| Title | Authors | Topics |
|---|---|---|
| Duplicate Systems Paper | Example Team | memory; evaluation |
""",
                encoding="utf-8",
            )
            (project_dir / "memory.md").write_text(
                """## References

- Example Team (2024). Duplicate Systems Paper. ICML. doi:10.1145/1234567.1234568
- Other et al. (2025). Versioned ArXiv Paper. arXiv:2401.12345v2.
""",
                encoding="utf-8",
            )
            (run_dir / "03_revised.md").write_text(
                """Title: Versioned ArXiv Paper
Authors: Other et al.
Year: 2025
Venue: arXiv
arXiv: https://arxiv.org/abs/2401.12345v1
Topics: agent memory
""",
                encoding="utf-8",
            )

            project_input = load_project_input(
                root=root,
                project_name="survey_demo",
                explicit_project=True,
            )
            result = run_literature_survey_mode(
                console=Console(),
                project_input=project_input,
                config=LiteratureSurveyConfig(),
            )

            metadata = json.loads(result.metadata_path.read_text(encoding="utf-8"))
            self.assertEqual(metadata["paper_count"], 2)
            papers = {paper["title"]: paper for paper in metadata["papers"]}

            duplicate = papers["Duplicate Systems Paper"]
            self.assertEqual(duplicate["doi"], "10.1145/1234567.1234568")
            self.assertEqual(duplicate["year"], 2024)
            self.assertEqual(duplicate["venue"], "ICML")
            self.assertEqual(duplicate["authors"], ["Example Team"])

            arxiv = papers["Versioned ArXiv Paper"]
            self.assertEqual(arxiv["arxiv_id"], "2401.12345")
            self.assertEqual(arxiv["year"], 2025)
            self.assertGreaterEqual(len(arxiv["source_paths"]), 2)

            quality = metadata["metadata_quality"]
            self.assertEqual(quality["paper_count"], 2)
            self.assertEqual(quality["missing_year_count"], 0)
            self.assertEqual(quality["missing_url_or_identifier_count"], 0)

            manifest = json.loads(result.manifest_path.read_text(encoding="utf-8"))
            self.assertEqual(manifest["source_summary"]["by_kind"]["run_output"], 1)
            self.assertTrue(manifest["representative_groups"])


if __name__ == "__main__":
    unittest.main()
