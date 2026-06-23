# Literature Survey Report

- project: survey_demo
- title: Memory-Agent Literature Survey
- generated_at: 2026-06-17T00:00:00
- source_files_scanned: 3
- unique_papers: 4

## Executive Summary

This survey collected 4 unique papers from existing project files and organized them into 5 research
themes. Dominant themes include memory, agent, privacy, evaluation, and benchmark. Recurring methods
include retrieval, prompting, simulation, and differential privacy. Common evaluation signals include
human evaluation, F1, attack success rate, Persona-Chat, and DailyDialog.

## Research Landscape

- memory: 3 paper(s); representative work includes MemGPT, MemoryAgentBench, and a privacy-memory benchmark paper.
- privacy: 2 paper(s); representative work includes privacy attacks for long-term memory and membership inference.
- evaluation: 1 paper(s); representative work includes MemoryAgentBench.

## Major Themes

### memory

- papers: 3
- recurring methods: retrieval, prompting, simulation
- datasets: DailyDialog
- evaluation approaches: human evaluation, F1

### privacy

- papers: 2
- recurring methods: simulation, differential privacy
- datasets: Persona-Chat
- evaluation approaches: attack success rate, F1

## Representative Papers

- **MemoryAgentBench: Evaluating Long-Term Agent Memory (2024), Benchmark Track**:
  metadata-only record. Methods: simulation, retrieval. Evaluation: F1, human evaluation,
  DailyDialog.
- **MemGPT: Towards LLMs as Operating Systems (2023), arXiv**:
  metadata-only record. Methods: retrieval, prompting. Evaluation: human evaluation.
- **Privacy Attacks for Long-Term Agent Memory (2025), Workshop**:
  metadata-only record. Methods: simulation, differential privacy. Evaluation: attack success rate,
  F1, Persona-Chat.

## Comparison Tables

| Paper | Year | Themes | Methods | Benchmarks/Datasets | Limitations |
|---|---:|---|---|---|---|
| Privacy Attacks for Long-Term Agent Memory (2025), Workshop | 2025 | privacy, memory | simulation, differential privacy | attack success rate, F1, Persona-Chat | Synthetic users may miss real preference drift |
| MemoryAgentBench: Evaluating Long-Term Agent Memory (2024), Benchmark Track | 2024 | memory, evaluation, agent | simulation, retrieval | F1, human evaluation, DailyDialog | Limited multilingual coverage |
| MemGPT: Towards LLMs as Operating Systems (2023), arXiv | 2023 | memory, agent | retrieval, prompting | human evaluation | Context-window pressure remains a limitation |

## Research Gaps

- Synthetic users may miss real preference drift.
- Limited multilingual coverage.
- Context-window pressure remains a limitation.

## Future Directions

- Open problem: realistic longitudinal data.
- Add privacy stress tests.
- Better long-horizon benchmarks.

## Related Work Draft

Work on memory is represented by MemoryAgentBench: Evaluating Long-Term Agent Memory (2024),
MemGPT: Towards LLMs as Operating Systems (2023), and Privacy Attacks for Long-Term Agent Memory
(2025). Across this cluster, recurring methods include retrieval, simulation, prompting, and
differential privacy. Evaluation commonly relies on human evaluation, F1, DailyDialog, and
Persona-Chat.

Work on privacy is represented by Privacy Attacks for Long-Term Agent Memory (2025) and Membership
Inference Attacks Against Machine Learning Models (2017). Across this cluster, recurring methods
include simulation and differential privacy. Evaluation commonly relies on attack success rate and
F1.

## References

1. Doe and Roe. 2025. Privacy Attacks for Long-Term Agent Memory. Workshop.
2. Example Author. 2024. MemoryAgentBench: Evaluating Long-Term Agent Memory. Benchmark Track.
3. Packer et al. 2023. MemGPT: Towards LLMs as Operating Systems. arXiv.
4. Shokri et al. 2017. Membership Inference Attacks Against Machine Learning Models. IEEE S&P.
