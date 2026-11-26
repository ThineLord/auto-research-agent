from __future__ import annotations

import json
import os
import subprocess
import sys
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

EXAMPLE_DIR = Path(__file__).resolve().parents[2] / "example"
PUBLIC_EXAMPLE_TITLES = {
    "MemGPT: Towards LLMs as Operating Systems",
    "Privacy Attacks for Long-Term Agent Memory",
    "MemoryAgentBench: Evaluating Long-Term Agent Memory",
    "Membership Inference Attacks Against Machine Learning Models",
}


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

    def test_repeated_custom_survey_ignores_generated_artifacts(self) -> None:
        for layout in ("flat", "legacy"):
            with self.subTest(layout=layout):
                with tempfile.TemporaryDirectory() as tmp:
                    root = Path(tmp)
                    project_dir = _prepare_public_example(root, layout)
                    _write_paper_block(
                        project_dir / "custom_survey.md",
                        "Seeded Custom Survey Paper",
                    )
                    _write_paper_block(
                        project_dir / "related_work.md",
                        "Seeded Custom Related Work Paper",
                    )
                    _write_paper_block(
                        project_dir / "survey" / "survey_report.md",
                        "Seeded Default Survey Paper",
                    )
                    _write_paper_block(
                        project_dir / "survey" / "related_work.md",
                        "Seeded Default Related Work Paper",
                    )
                    project_input = load_project_input(
                        root=root,
                        project_name="example",
                        explicit_project=True,
                    )
                    snapshots = [
                        _survey_snapshot(
                            _run_custom_survey(project_input, project_dir / "custom_survey.md")
                        )
                        for _ in range(3)
                    ]

                    self.assertEqual(snapshots[0], snapshots[1])
                    self.assertEqual(snapshots[1], snapshots[2])
                    (
                        paper_count,
                        quality,
                        manifest_count,
                        manifest_quality,
                        sources,
                        paper_sources,
                    ) = snapshots[0]
                    self.assertEqual(paper_count, 4)
                    self.assertEqual(manifest_count, 4)
                    self.assertEqual(quality["paper_count"], 4)
                    self.assertEqual(manifest_quality, quality)
                    self.assertEqual(set(paper_sources), PUBLIC_EXAMPLE_TITLES)
                    prefix = "projects/example" if layout == "legacy" else "example"
                    self.assertEqual(
                        sources,
                        (
                            f"{prefix}/literature_survey_sources.md",
                            f"{prefix}/task.md",
                        ),
                    )
                    serialized = json.dumps(snapshots)
                    self.assertNotIn("Seeded Custom Survey Paper", serialized)
                    self.assertNotIn("Seeded Custom Related Work Paper", serialized)
                    self.assertNotIn("Seeded Default Survey Paper", serialized)
                    self.assertNotIn("Seeded Default Related Work Paper", serialized)
                    self.assertNotIn("custom_survey.md", serialized)
                    self.assertNotIn("related_work.md", serialized)
                    self.assertNotIn(str(root), serialized)

    def test_other_project_markdown_stays_a_source_across_repeated_surveys(self) -> None:
        for layout in ("flat", "legacy"):
            with self.subTest(layout=layout):
                with tempfile.TemporaryDirectory() as tmp:
                    root = Path(tmp)
                    project_dir = _prepare_public_example(root, layout)
                    _write_paper_block(project_dir / "field_notes.md", "Kept User Field Note")
                    project_input = load_project_input(
                        root=root,
                        project_name="example",
                        explicit_project=True,
                    )
                    snapshots = [
                        _survey_snapshot(
                            _run_custom_survey(project_input, project_dir / "custom_survey.md")
                        )
                        for _ in range(3)
                    ]

                    self.assertEqual(snapshots[0], snapshots[1])
                    self.assertEqual(snapshots[1], snapshots[2])
                    paper_count, quality, _manifest_count, manifest_quality, sources, titles = (
                        snapshots[0]
                    )
                    self.assertEqual(paper_count, 5)
                    self.assertEqual(quality, manifest_quality)
                    self.assertEqual(quality["paper_count"], 5)
                    self.assertIn("Kept User Field Note", titles)
                    prefix = "projects/example" if layout == "legacy" else "example"
                    self.assertEqual(
                        sources,
                        (
                            f"{prefix}/field_notes.md",
                            f"{prefix}/literature_survey_sources.md",
                            f"{prefix}/task.md",
                        ),
                    )

    def test_default_output_skips_survey_dir_and_keeps_user_related_work(self) -> None:
        for layout in ("flat", "legacy"):
            with self.subTest(layout=layout):
                with tempfile.TemporaryDirectory() as tmp:
                    root = Path(tmp)
                    project_dir = _prepare_public_example(root, layout)
                    _write_paper_block(project_dir / "related_work.md", "Kept User Related Work")
                    _write_paper_block(project_dir / "reading_list.md", "Kept User Reading List")
                    _write_paper_block(
                        project_dir / "survey" / "survey_report.md",
                        "Seeded Default Survey Paper",
                    )
                    _write_paper_block(
                        project_dir / "survey" / "related_work.md",
                        "Seeded Default Related Work Paper",
                    )
                    project_input = load_project_input(
                        root=root,
                        project_name="example",
                        explicit_project=True,
                    )
                    config = LiteratureSurveyConfig(source_globs=("**/*.md",))
                    snapshots = [
                        _survey_snapshot(
                            run_literature_survey_mode(
                                console=Console(),
                                project_input=project_input,
                                config=config,
                            )
                        )
                        for _ in range(3)
                    ]

                    self.assertEqual(snapshots[0], snapshots[1])
                    self.assertEqual(snapshots[1], snapshots[2])
                    paper_count, quality, _manifest_count, manifest_quality, sources, titles = (
                        snapshots[0]
                    )
                    self.assertEqual(paper_count, 6)
                    self.assertEqual(quality, manifest_quality)
                    self.assertIn("Kept User Related Work", titles)
                    self.assertIn("Kept User Reading List", titles)
                    self.assertNotIn("Seeded Default Survey Paper", titles)
                    self.assertNotIn("Seeded Default Related Work Paper", titles)
                    prefix = "projects/example" if layout == "legacy" else "example"
                    self.assertEqual(
                        sources,
                        (
                            f"{prefix}/literature_survey_sources.md",
                            f"{prefix}/reading_list.md",
                            f"{prefix}/related_work.md",
                            f"{prefix}/task.md",
                        ),
                    )
                    self.assertFalse(any("/survey/" in source for source in sources))

    def test_explicit_nested_report_skips_only_its_artifact_group(self) -> None:
        for layout in ("flat", "legacy"):
            with self.subTest(layout=layout):
                with tempfile.TemporaryDirectory() as tmp:
                    root = Path(tmp)
                    project_dir = _prepare_public_example(root, layout)
                    _write_paper_block(
                        project_dir / "outputs" / "kept_source.md",
                        "Kept Nested User Source",
                    )
                    _write_paper_block(
                        project_dir / "outputs" / "custom_survey.md",
                        "Seeded Nested Survey Paper",
                    )
                    _write_paper_block(
                        project_dir / "outputs" / "related_work.md",
                        "Seeded Nested Related Work Paper",
                    )
                    project_input = load_project_input(
                        root=root,
                        project_name="example",
                        explicit_project=True,
                    )
                    report_path = project_dir / "outputs" / "custom_survey.md"
                    snapshots = [
                        _survey_snapshot(_run_custom_survey(project_input, report_path))
                        for _ in range(3)
                    ]

                    self.assertEqual(snapshots[0], snapshots[1])
                    self.assertEqual(snapshots[1], snapshots[2])
                    paper_count, quality, _manifest_count, manifest_quality, sources, titles = (
                        snapshots[0]
                    )
                    self.assertEqual(paper_count, 5)
                    self.assertEqual(quality, manifest_quality)
                    self.assertIn("Kept Nested User Source", titles)
                    self.assertNotIn("Seeded Nested Survey Paper", titles)
                    self.assertNotIn("Seeded Nested Related Work Paper", titles)
                    prefix = "projects/example" if layout == "legacy" else "example"
                    self.assertEqual(
                        sources,
                        (
                            f"{prefix}/literature_survey_sources.md",
                            f"{prefix}/outputs/kept_source.md",
                            f"{prefix}/task.md",
                        ),
                    )

    def test_flat_and_legacy_source_paths_keep_run_directories(self) -> None:
        drafts = {
            "run-one": "Run One Distinct Draft Paper",
            "run-two": "Run Two Distinct Draft Paper",
        }
        for layout in ("flat", "legacy"):
            with self.subTest(layout=layout):
                with tempfile.TemporaryDirectory() as tmp:
                    root = Path(tmp)
                    project_dir = _project_dir(root, layout, "survey_demo")
                    project_dir.mkdir(parents=True)
                    (project_dir / "task.md").write_text("# Survey\n", encoding="utf-8")
                    for run_name, title in drafts.items():
                        draft = project_dir / "runs" / run_name / "round_01" / "01_draft.md"
                        _write_paper_block(draft, title)
                    project_input = load_project_input(
                        root=root,
                        project_name="survey_demo",
                        explicit_project=True,
                    )
                    snapshots = []
                    reports = []
                    consoles = []
                    for _ in range(2):
                        console = Console(record=True, width=200)
                        result = run_literature_survey_mode(
                            console=console,
                            project_input=project_input,
                            config=LiteratureSurveyConfig(),
                        )
                        snapshots.append(_survey_snapshot(result))
                        reports.append(result.report_path.read_text(encoding="utf-8"))
                        consoles.append(console.export_text(styles=False))

                    self.assertEqual(snapshots[0], snapshots[1])
                    metadata = json.loads(
                        (project_dir / "survey" / "paper_metadata.json").read_text(encoding="utf-8")
                    )
                    by_title = {
                        paper["title"]: paper["source_paths"] for paper in metadata["papers"]
                    }
                    prefix = "projects/survey_demo" if layout == "legacy" else "survey_demo"
                    expected = {
                        title: [f"{prefix}/runs/{run_name}/round_01/01_draft.md"]
                        for run_name, title in drafts.items()
                    }
                    self.assertEqual(
                        {title: by_title[title] for title in drafts.values()},
                        expected,
                    )
                    metadata_text = (project_dir / "survey" / "paper_metadata.json").read_text(
                        encoding="utf-8"
                    )
                    manifest_text = (project_dir / "survey" / "survey_manifest.json").read_text(
                        encoding="utf-8"
                    )
                    rendered = "\n".join(reports + consoles) + metadata_text + manifest_text
                    self.assertNotIn("<repo>/01_draft.md", rendered)
                    self.assertNotIn(str(root), rendered)
                    for run_name in drafts:
                        relative = f"{prefix}/runs/{run_name}/round_01/01_draft.md"
                        self.assertIn(relative, reports[0])
                        self.assertIn(relative, snapshots[0][4])

    def test_switched_output_locations_do_not_reread_generated_artifacts(self) -> None:
        reading_title = "Kept Reading Note"
        same_name_title = "Kept User Survey Report Note"
        plain_title = "Kept Plain Survey Note"
        expected_titles = PUBLIC_EXAMPLE_TITLES | {reading_title, same_name_title, plain_title}
        for layout in ("flat", "legacy"):
            with self.subTest(layout=layout):
                with tempfile.TemporaryDirectory() as tmp:
                    root = Path(tmp)
                    project_dir = _prepare_public_example(root, layout)
                    _write_paper_block(project_dir / "reading-notes.md", reading_title)
                    _write_paper_block(project_dir / "survey_report.md", same_name_title)
                    (project_dir / "survey_notes.md").write_text(
                        "# Literature Survey Report\n"
                        "\n"
                        "These are my own notes.\n"
                        f"Title: {plain_title}\n"
                        "Authors: Survey Fixture\n"
                        "Year: 2016\n"
                        "Venue: Fixture\n",
                        encoding="utf-8",
                    )
                    preserved = {
                        path: path.read_bytes()
                        for path in (
                            project_dir / "reading-notes.md",
                            project_dir / "survey_report.md",
                            project_dir / "survey_notes.md",
                            project_dir / "literature_survey_sources.md",
                            project_dir / "task.md",
                        )
                    }
                    project_input = load_project_input(
                        root=root,
                        project_name="example",
                        explicit_project=True,
                    )
                    report_one = project_dir / "report-one.md"
                    report_two = project_dir / "report-two.md"
                    default_report = project_dir / "survey" / "survey_report.md"
                    root_related = project_dir / "related_work.md"
                    outputs = (report_one, None, report_two, report_one)
                    snapshots = []
                    report_one_bytes = b""
                    report_two_bytes = b""
                    default_report_bytes = b""
                    root_related_bytes = b""
                    result = None
                    for index, output_path in enumerate(outputs):
                        result = run_literature_survey_mode(
                            console=Console(),
                            project_input=project_input,
                            config=LiteratureSurveyConfig(),
                            output_path=output_path,
                            workspace_root=root,
                        )
                        snapshots.append(_survey_snapshot(result))
                        if index == 0:
                            report_one_bytes = report_one.read_bytes()
                            root_related_bytes = root_related.read_bytes()
                        elif index == 1:
                            self.assertEqual(report_one.read_bytes(), report_one_bytes)
                            self.assertEqual(root_related.read_bytes(), root_related_bytes)
                            default_report_bytes = default_report.read_bytes()
                        elif index == 2:
                            self.assertEqual(report_one.read_bytes(), report_one_bytes)
                            self.assertEqual(default_report.read_bytes(), default_report_bytes)
                            report_two_bytes = report_two.read_bytes()
                        else:
                            self.assertEqual(report_two.read_bytes(), report_two_bytes)
                            self.assertEqual(default_report.read_bytes(), default_report_bytes)
                    self.assertEqual(snapshots[0], snapshots[1])
                    self.assertEqual(snapshots[1], snapshots[2])
                    self.assertEqual(snapshots[2], snapshots[3])
                    (
                        paper_count,
                        quality,
                        manifest_count,
                        manifest_quality,
                        sources,
                        titles,
                    ) = snapshots[-1]
                    self.assertEqual(paper_count, 7)
                    self.assertEqual(manifest_count, 7)
                    self.assertEqual(len(titles), 7)
                    self.assertEqual(quality["paper_count"], 7)
                    self.assertEqual(manifest_quality, quality)
                    self.assertEqual(set(titles), expected_titles)
                    prefix = "projects/example" if layout == "legacy" else "example"
                    self.assertEqual(
                        sources,
                        (
                            f"{prefix}/literature_survey_sources.md",
                            f"{prefix}/reading-notes.md",
                            f"{prefix}/survey_notes.md",
                            f"{prefix}/survey_report.md",
                            f"{prefix}/task.md",
                        ),
                    )
                    assert result is not None
                    metadata = json.loads(result.metadata_path.read_text(encoding="utf-8"))
                    by_title = {
                        paper["title"]: paper["source_paths"] for paper in metadata["papers"]
                    }
                    self.assertEqual(by_title[reading_title], [f"{prefix}/reading-notes.md"])
                    self.assertEqual(by_title[same_name_title], [f"{prefix}/survey_report.md"])
                    self.assertEqual(by_title[plain_title], [f"{prefix}/survey_notes.md"])
                    for paper in metadata["papers"]:
                        self.assertTrue(set(paper["source_paths"]).issubset(sources))
                    for path, content in preserved.items():
                        self.assertEqual(path.read_bytes(), content)

    def test_workspace_root_is_used_for_flat_and_legacy_paths(self) -> None:
        cases = {
            "flat": ("projects", "topic", "topic"),
            "legacy": ("workspace", "topic", "projects/topic"),
        }
        for layout, (workspace_name, project_name, prefix) in cases.items():
            with self.subTest(layout=layout):
                with tempfile.TemporaryDirectory() as tmp:
                    workspace = Path(tmp) / workspace_name
                    project_dir = _project_dir(workspace, layout, project_name)
                    project_dir.mkdir(parents=True)
                    (project_dir / "task.md").write_text("# Topic\n", encoding="utf-8")
                    draft = project_dir / "runs" / "run-one" / "round_01" / "01_draft.md"
                    _write_paper_block(draft, "Workspace Draft Paper")
                    project_input = load_project_input(
                        root=workspace,
                        project_name=project_name,
                        explicit_project=True,
                    )
                    self.assertEqual(project_input.project_dir.resolve(), project_dir.resolve())
                    result = run_literature_survey_mode(
                        console=Console(),
                        project_input=project_input,
                        config=LiteratureSurveyConfig(),
                        workspace_root=workspace,
                    )
                    manifest = json.loads(result.manifest_path.read_text(encoding="utf-8"))
                    metadata = json.loads(result.metadata_path.read_text(encoding="utf-8"))
                    report_rel = f"{prefix}/survey/survey_report.md"
                    draft_rel = f"{prefix}/runs/run-one/round_01/01_draft.md"
                    self.assertEqual(manifest["project"]["project_dir"], prefix)
                    self.assertEqual(manifest["outputs"]["report"], report_rel)
                    self.assertEqual(
                        manifest["source_files"],
                        [draft_rel, f"{prefix}/task.md"],
                    )
                    self.assertEqual(manifest["paper_count"], 1)
                    self.assertTrue((workspace / report_rel).is_file())
                    self.assertTrue((workspace / draft_rel).is_file())
                    self.assertEqual(metadata["papers"][0]["source_paths"], [draft_rel])
                    self.assertIn(f"- {draft_rel}", result.report_path.read_text(encoding="utf-8"))
                    if layout == "flat":
                        rendered = (
                            result.report_path.read_text(encoding="utf-8")
                            + json.dumps(manifest)
                            + json.dumps(metadata)
                        )
                        self.assertNotIn(f"projects/{project_name}/", rendered)
                        self.assertFalse((workspace / "projects" / project_name).exists())

    def test_cli_projects_workspace_keeps_flat_paths_across_output_switches(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            workspace = Path(tmp) / "projects"
            project_dir = _prepare_public_example(workspace, "flat")
            _write_paper_block(project_dir / "reading-notes.md", "Kept Reading Note")
            preserved = (project_dir / "reading-notes.md").read_bytes()
            app_dir = Path(__file__).resolve().parents[1]
            (workspace / "config.yaml").write_text(
                (app_dir / "config.example.yaml").read_text(encoding="utf-8"),
                encoding="utf-8",
            )
            commands = (
                ["--survey", "--survey-output", "report-one.md"],
                ["--survey"],
                ["--survey", "--survey-output", "report-two.md"],
                ["--survey", "--survey-output", "report-one.md"],
            )
            report_one_bytes = b""
            for index, args in enumerate(commands):
                completed = subprocess.run(
                    [
                        sys.executable,
                        "-m",
                        "src.main",
                        "--workspace",
                        str(workspace),
                        "--project",
                        "example",
                        *args,
                    ],
                    cwd=app_dir,
                    capture_output=True,
                    text=True,
                    timeout=40,
                    check=False,
                )
                self.assertEqual(completed.returncode, 0, completed.stdout + completed.stderr)
                if "--survey-output" in args:
                    manifest_path = project_dir / "survey_manifest.json"
                    report_rel = f"example/{args[-1]}"
                else:
                    manifest_path = project_dir / "survey" / "survey_manifest.json"
                    report_rel = "example/survey/survey_report.md"
                manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
                metadata = json.loads(
                    manifest_path.with_name("paper_metadata.json").read_text(encoding="utf-8")
                )
                self.assertEqual(manifest["project"]["project_dir"], "example")
                self.assertEqual(manifest["paper_count"], 5)
                self.assertEqual(metadata["paper_count"], 5)
                self.assertEqual(manifest["metadata_quality"]["paper_count"], 5)
                self.assertEqual(
                    manifest["source_files"],
                    [
                        "example/literature_survey_sources.md",
                        "example/reading-notes.md",
                        "example/task.md",
                    ],
                )
                self.assertEqual(
                    {paper["title"] for paper in metadata["papers"]},
                    PUBLIC_EXAMPLE_TITLES | {"Kept Reading Note"},
                )
                reading = next(
                    paper for paper in metadata["papers"] if paper["title"] == "Kept Reading Note"
                )
                self.assertEqual(reading["source_paths"], ["example/reading-notes.md"])
                self.assertEqual(manifest["outputs"]["report"], report_rel)
                self.assertTrue((workspace / report_rel).is_file())
                self.assertFalse((workspace / "projects" / "example").exists())
                if index == 0:
                    report_one_bytes = (project_dir / "report-one.md").read_bytes()
                elif index < 3:
                    self.assertEqual((project_dir / "report-one.md").read_bytes(), report_one_bytes)
            self.assertEqual((project_dir / "reading-notes.md").read_bytes(), preserved)


def _project_dir(root: Path, layout: str, name: str) -> Path:
    if layout == "legacy":
        return root / "projects" / name
    if layout == "flat":
        return root / name
    raise AssertionError(layout)


def _prepare_public_example(root: Path, layout: str) -> Path:
    project_dir = _project_dir(root, layout, "example")
    project_dir.mkdir(parents=True)
    for name in ("task.md", "literature_survey_sources.md"):
        (project_dir / name).write_text(
            (EXAMPLE_DIR / name).read_text(encoding="utf-8"),
            encoding="utf-8",
        )
    return project_dir


def _write_paper_block(path: Path, title: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        f"Title: {title}\nAuthors: Survey Fixture\nYear: 2016\nVenue: Fixture\n",
        encoding="utf-8",
    )


def _run_custom_survey(project_input, report_path: Path):
    return run_literature_survey_mode(
        console=Console(),
        project_input=project_input,
        config=LiteratureSurveyConfig(),
        output_path=report_path,
    )


def _survey_snapshot(result):
    metadata = json.loads(result.metadata_path.read_text(encoding="utf-8"))
    manifest = json.loads(result.manifest_path.read_text(encoding="utf-8"))
    titles = tuple(paper["title"] for paper in metadata["papers"])
    return (
        metadata["paper_count"],
        metadata["metadata_quality"],
        manifest["paper_count"],
        manifest["metadata_quality"],
        tuple(manifest["source_files"]),
        titles,
    )


if __name__ == "__main__":
    unittest.main()
