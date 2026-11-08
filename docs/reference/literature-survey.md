# Literature Survey Mode

Literature Survey Mode turns a project folder into a local research-survey workspace. It scans
existing project inputs and saved workflow outputs, extracts paper metadata, deduplicates papers,
groups them into themes, and writes survey artifacts without calling Ollama or Gemini.

## Run It

```bash
make survey
```

Useful overrides:

```bash
make survey ARGS="--project my_project"
make survey ARGS="--project my_project --survey-output custom_survey.md"
```

Relative `--survey-output` paths are resolved under `projects/<project>/`. By default, outputs are
written to `projects/<project>/survey/`.

## Source Formats

Survey mode reads existing markdown and text sources under the selected project. It supports:

- `task.md` and optional `memory.md`
- top-level project markdown files
- saved round outputs under `runs/**/*.md`
- configured extra globs such as `outputs/**/*.md` and `artifacts/**/*.md`
- markdown tables with columns like `Title`, `Authors`, `Year`, `Venue`, `Topics`,
  `Methods`, `Benchmarks`, `Datasets`, `Limitations`, `Future Work`, and `URL`
- `Title: ...` metadata blocks
- `## References` or `## Bibliography` lists with years or URLs
- simple frontmatter-like `---` metadata blocks
- DOI and arXiv identifiers in tables, metadata blocks, links, or reference text

## Outputs

The workflow writes:

- `survey_report.md`: structured survey report
- `paper_metadata.json`: normalized paper metadata, quality counts, and representative groups
- `related_work.md`: publication-style related work draft
- `survey_manifest.json`: run metadata, config, source summaries, quality counts, and output paths

The report contains:

- Executive Summary
- Metadata Quality
- Research Landscape
- Major Themes
- Representative Papers
- Comparison Tables
- Research Gaps
- Future Directions
- Related Work Draft
- References

## Configuration

`config.yaml` can include:

```yaml
literature_survey:
  include_task: true
  include_memory: true
  include_project_markdown: true
  include_run_outputs: true
  source_globs:
    - "outputs/**/*.md"
    - "artifacts/**/*.md"
  max_source_files: 80
  max_papers: 200
  output_dir: survey
```

## Architecture Summary

The implementation is deliberately modular:

- `src.cli` adds `--survey` and dispatches before provider validation, so no model or API key is
  required.
- `src.config` validates a strict `literature_survey` block and keeps defaults compatible.
- `src.literature_survey` owns collection, parsing, metadata normalization, deduplication, theme
  extraction, gap extraction, report rendering, and artifact writing.
- Existing iterative workflows remain untouched: `run`, `diagnostic`, `continuous`, `session`, and
  `resume` still use the Draft -> Review -> Revise -> Judge loop.

## Limitations

This MVP is deterministic and metadata-driven. It does not search the web, download papers, read
PDFs, or use an LLM to rewrite prose. Better metadata in project files produces better survey
reports. Add paper tables, references, and explicit limitation/future-work notes for stronger
results. The metadata-quality section highlights missing authors, years, venues, and durable
identifiers so incomplete local sources can be repaired incrementally.

See `docs/examples/literature_survey_example.md` for a generated-style example.
