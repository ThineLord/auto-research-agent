# auto-research-agent

Local-first iterative research agent pipeline for academic research using Ollama.

## Features

- Local LLM backend via Ollama.
- Default model: `llama3.1:8b`.
- Iterative loop: Draft -> Review -> Revise -> Judge.
- Per-round artifacts saved as markdown logs.
- Best judged output tracked and saved to `projects/pama/best_output.md`.
- Simple Python codebase without LangChain, easy to extend.

## Project Structure

```text
auto-research-agent/
  README.md
  .gitignore
  config.yaml
  requirements.txt
  prompts/
    draft.md
    review.md
    revise.md
    judge.md
  projects/
    pama/
      task.md
      memory.md
      best_output.md
      runs/
  src/
    __init__.py
    main.py
    llm.py
    agents.py
    storage.py
```

## Prerequisites

1. Python 3.10+ (recommended).
2. [Ollama](https://ollama.com/) installed and running locally.
3. Pull the default model:

```bash
ollama pull llama3.1:8b
```

## Setup

```bash
cd auto-research-agent
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

## Run

```bash
python -m src.main
```

The program reads configuration from `config.yaml`, then runs iterative rounds:

1. Draft
2. Review
3. Revise
4. Judge
5. Save logs
6. Repeat until `max_rounds` or no score improvement

## Outputs

- Round logs are saved under:
  - `projects/pama/runs/<timestamp>/round_XX/`
  - `01_draft.md`
  - `02_review.md`
  - `03_revised.md`
  - `04_judge.md`
- Best revised output is saved to:
  - `projects/pama/best_output.md`

## Configuration

Edit `config.yaml` to customize:

- `model`: Ollama model name
- `ollama_base_url`: Ollama endpoint
- `max_rounds`: loop limit
- `temperature`: sampling temperature
- `project_name`: project folder under `projects/`

## Notes

- Generated runs, virtual environments, `.env`, and PDFs are ignored by git.
- To extend agents, update prompts in `prompts/` or add new Python modules in `src/`.
