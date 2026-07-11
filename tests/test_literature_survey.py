from __future__ import annotations

import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from rich.console import Console

import src.literature_survey as survey_module
from src.config import LiteratureSurveyConfig
from src.literature_survey import (
    collect_papers,
    generate_related_work,
    run_literature_survey_mode,
)
from src.project_input import load_project_input


class LiteratureSurveyTests(unittest.TestCase):
    @unittest.skipUnless(hasattr(Path, "symlink_to"), "symlinks are unavailable")
    def test_collection_rejects_project_ancestor_swap_after_boundary_registration(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            projects = root / "projects"
            project_dir = projects / "survey_demo"
            project_dir.mkdir(parents=True)
            (project_dir / "task.md").write_text("# Trusted task\n", encoding="utf-8")
            outside_project = root / "outside-projects" / "survey_demo"
            outside_project.mkdir(parents=True)
            (outside_project / "task.md").write_text(
                "| Title | Authors |\n|---|---|\n| Private Sentinel Study | External Author |\n",
                encoding="utf-8",
            )
            trusted_projects = root / "trusted-projects"
            original_preflight = survey_module.ensure_project_runtime_paths_safe

            def preflight_then_swap(path: Path) -> Path | None:
                result = original_preflight(path)
                projects.rename(trusted_projects)
                projects.symlink_to(root / "outside-projects", target_is_directory=True)
                return result

            with patch.object(
                survey_module,
                "ensure_project_runtime_paths_safe",
                side_effect=preflight_then_swap,
            ):
                with self.assertRaises(OSError):
                    collect_papers(
                        project_dir,
                        LiteratureSurveyConfig(max_source_files=1, max_papers=1),
                    )

    @unittest.skipUnless(hasattr(Path, "symlink_to"), "symlinks are unavailable")
    def test_automatic_nested_output_rejects_symlinked_component(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            project_dir = root / "projects" / "survey_demo"
            outside = root / "outside"
            project_dir.mkdir(parents=True)
            outside.mkdir()
            (project_dir / "task.md").write_text("# Survey\n", encoding="utf-8")
            (project_dir / "linked").symlink_to(outside, target_is_directory=True)
            project_input = load_project_input(
                root=root,
                project_name="survey_demo",
                explicit_project=True,
            )

            with self.assertRaises(OSError):
                run_literature_survey_mode(
                    console=Console(),
                    project_input=project_input,
                    config=LiteratureSurveyConfig(output_dir="linked/nested"),
                )

            self.assertFalse((outside / "nested").exists())

    @unittest.skipUnless(hasattr(Path, "symlink_to"), "symlinks are unavailable")
    def test_automatic_output_preflights_all_leaves_before_writing(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            project_dir = root / "projects" / "survey_demo"
            survey_dir = project_dir / "survey"
            survey_dir.mkdir(parents=True)
            (project_dir / "task.md").write_text("# Survey\n", encoding="utf-8")
            report_path = survey_dir / "survey_report.md"
            report_path.write_text("ORIGINAL_REPORT\n", encoding="utf-8")
            external_manifest = root / "external-manifest.json"
            external_manifest.write_text('{"private": true}\n', encoding="utf-8")
            (survey_dir / "survey_manifest.json").symlink_to(external_manifest)
            project_input = load_project_input(
                root=root,
                project_name="survey_demo",
                explicit_project=True,
            )

            with self.assertRaises(OSError):
                run_literature_survey_mode(
                    console=Console(),
                    project_input=project_input,
                    config=LiteratureSurveyConfig(),
                )

            self.assertEqual(report_path.read_text(encoding="utf-8"), "ORIGINAL_REPORT\n")
            self.assertEqual(
                external_manifest.read_text(encoding="utf-8"),
                '{"private": true}\n',
            )

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

            self.assertEqual(
                source_files,
                [Path(os.path.abspath(project_dir / "task.md"))],
            )
            self.assertEqual(papers, [])
            self.assertIn("no paper metadata", generate_related_work(papers).lower())

    def test_collection_preserves_lexical_sort_order_before_source_limit(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            project_dir = Path(tmp) / "projects" / "ordered"
            nested = project_dir / "a"
            nested.mkdir(parents=True)
            (project_dir / "a.md").write_text("# Root source\n", encoding="utf-8")
            (nested / "z.md").write_text("# Nested source\n", encoding="utf-8")

            _papers, source_files = collect_papers(
                project_dir,
                LiteratureSurveyConfig(
                    include_task=False,
                    include_memory=False,
                    include_project_markdown=False,
                    include_run_outputs=False,
                    source_globs=("**/*.md",),
                    max_source_files=1,
                ),
            )

            self.assertEqual(
                source_files,
                [Path(os.path.abspath(project_dir / "a.md"))],
            )

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

    def test_survey_outputs_mask_local_paths(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            project_dir = root / "projects" / "survey_demo"
            project_dir.mkdir(parents=True)
            (project_dir / "task.md").write_text(
                """# Survey

| Title | Authors | Year | URL |
|---|---|---:|---|
| Path Privacy Paper | Example Team | 2024 | https://example.org/path-privacy |
""",
                encoding="utf-8",
            )
            project_input = load_project_input(
                root=root,
                project_name="survey_demo",
                explicit_project=True,
            )
            console = Console(record=True, width=200)

            result = run_literature_survey_mode(
                console=console,
                project_input=project_input,
                config=LiteratureSurveyConfig(),
            )

            output = console.export_text(styles=False)
            metadata = json.loads(result.metadata_path.read_text(encoding="utf-8"))
            manifest = json.loads(result.manifest_path.read_text(encoding="utf-8"))
            serialized_artifacts = json.dumps(metadata) + json.dumps(manifest)
            raw_root = str(project_input.project_dir.parent.parent)

            self.assertIn(
                "Saved survey report: projects/survey_demo/survey/survey_report.md",
                output,
            )
            self.assertEqual(metadata["project"]["project_dir"], "projects/survey_demo")
            self.assertEqual(metadata["project"]["task_path"], "projects/survey_demo/task.md")
            self.assertEqual(
                metadata["papers"][0]["source_paths"],
                ["projects/survey_demo/task.md"],
            )
            self.assertEqual(manifest["source_files"], ["projects/survey_demo/task.md"])
            self.assertEqual(
                manifest["outputs"]["report"],
                "projects/survey_demo/survey/survey_report.md",
            )
            self.assertNotIn(raw_root, output)
            self.assertNotIn(raw_root, serialized_artifacts)


if __name__ == "__main__":
    unittest.main()
