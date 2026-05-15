# PAMA — Privacy-Aware Memory Adapter for Personal AI Agents

## Project Goal

Design and evaluate a privacy-first hybrid cloud-edge memory framework for Personal AI Agents.

The system should:
1. Detect sensitive PII locally
2. Transform memory into privacy-reduced semantic representations
3. Preserve downstream retrieval + reasoning utility
4. Reduce raw PII leakage during cloud interaction

Core idea:
Raw personal memory NEVER directly reaches the cloud.

---

# Main Research Questions

## RQ1
Can type-aware privacy transformation preserve more long-horizon reasoning capability than uniform anonymization?

## RQ2
Can a cloud-edge memory pipeline achieve a better privacy-utility trade-off than:
- cloud-only systems
- local-only systems

## RQ3
Do different PII categories require different transformation strengths?

Example categories:
- identity
- health
- location
- behavioral preference

---

# System Architecture

## Local Edge Layer
Responsibilities:
- memory ingestion
- vector embedding
- PII detection
- memory transformation
- local vector storage

Candidate tools:
- MLX
- Presidio
- local embedding model
- SQLite / ChromaDB / FAISS

## Cloud Layer
Responsibilities:
- retrieval reasoning
- QA generation
- stateless inference

Candidate models:
- GPT-4o
- DeepSeek
- Qwen
- Claude
- local vLLM deployment

---

# Required Deliverables

## D1 — Literature Collection
Collect and summarize papers related to:
- privacy-preserving RAG
- memory systems for agents
- de-identification
- dynamic anonymization
- hybrid cloud-edge AI
- long-term memory QA

Output:
- annotated bibliography
- citation table
- gap analysis

Priority references:
- CloneMem
- According to Me
- Dynamic Anonymization Framework
- Privacy-Preserving RAG
- Memory for Autonomous Agents

---

## D2 — Dataset Pipeline

Target benchmark:
- CLONEMEM

Tasks:
1. download dataset
2. inspect structure
3. identify memory formats
4. classify PII distributions
5. build preprocessing scripts

Output:
- dataset report
- preprocessing code
- PII statistics

---

## D3 — PII Taxonomy

Construct a type-aware PII hierarchy.

Initial categories:
- identity
- location
- organization
- health
- temporal
- preference
- relationship

For each type:
- define sensitivity level
- define transformation strategy
- define utility importance

Output:
- pii_taxonomy.json
- transformation policy config

---

## D4 — Transformation Engine

Implement:
T(m) -> m'

Then extend into:
T(m) = { T_t(m_t) }

Transformation strategies:
- masking
- tokenization
- semantic abstraction
- hierarchical generalization
- synthetic substitution

Example:
"Johns Hopkins Hospital"
-> [Medical_Institution]

"123 Main Street"
-> [City_Level_Location]

Output:
- modular transformation pipeline
- configurable policies
- evaluation-ready transformed dataset

---

## D5 — Retrieval Pipeline

Build:
memory -> embedding -> retrieval -> QA

Need support for:
- raw retrieval
- transformed retrieval
- hybrid retrieval

Measure:
- retrieval recall
- semantic similarity
- answer quality

Output:
- retrieval benchmark scripts
- evaluation harness

---

## D6 — Cloud-Edge Hybrid Prototype

Implement:
local preprocessing + cloud reasoning pipeline.

Requirements:
- local-only sensitive memory
- sanitized cloud prompt generation
- optional encrypted retrieval layer

Need:
- API orchestration
- latency logging
- configurable privacy modes

Output:
- runnable prototype
- architecture diagram
- inference logs

---

## D7 — Evaluation Framework

Metrics:

### Privacy
- PII leakage rate
- re-identification success rate

### Utility
- QA F1
- answer consistency
- retrieval accuracy

### Efficiency
- latency
- memory usage
- token cost

Need comparisons:

| Setting | Description |
|---|---|
| Cloud-only | Raw memory to cloud |
| Local-only | Entirely local reasoning |
| Uniform anonymization | Same transformation for all PII |
| Type-aware PAMA | Proposed system |

Output:
- benchmark scripts
- tables
- visualization figures

---

# Immediate Engineering Tasks

## Phase 1
- setup repository structure
- setup experiment configs
- setup dataset loader
- integrate Presidio
- test local embeddings

## Phase 2
- implement baseline masking
- implement type-aware transformation
- build retrieval benchmark

## Phase 3
- integrate cloud LLM
- implement hybrid inference
- run evaluation

## Phase 4
- analyze results
- generate plots
- draft paper sections

---

# Suggested Repository Structure

projects/pama/
├── task.md
├── papers/
├── notes/
├── configs/
├── datasets/
├── src/
│   ├── pii/
│   ├── transform/
│   ├── retrieval/
│   ├── evaluation/
│   ├── cloud/
│   └── local/
├── experiments/
├── outputs/
├── figures/
└── logs/

---

# Agent Instructions

When conducting research:
1. prioritize recent 2025-2026 papers
2. prefer arXiv + top conference sources
3. extract:
   - methodology
   - datasets
   - metrics
   - limitations
4. identify weaknesses exploitable by PAMA
5. continuously update literature matrix

When coding:
1. prioritize modular design
2. avoid hardcoded transformation rules
3. support configurable privacy policies
4. preserve reproducibility

When evaluating:
1. compare against multiple baselines
2. log every experiment
3. preserve prompts + outputs
4. measure both utility AND privacy

---

# Long-Term Goal

Produce:
1. research prototype
2. publishable experimental results
3. conference paper draft
4. reusable privacy-memory framework for future agent systems