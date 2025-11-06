# Pet Video Generator

AI-first pipeline for long, coherent pet videos from photos + a story prompt, orchestrated with LangGraph.

PetVideoGenerator (PVGen) is a LangGraph-powered, node-based agent that takes one or more pet reference photos plus a story prompt and produces a 30 s+ fantasy video with strong across-shot consistency (character identity, style, and scene continuity). The project ships with deterministic mock clients so it can run end-to-end without external APIs, while preserving hooks for real Qwen-VL, DeepSeek, and Volcengine (即梦) services.

Looking for Chinese docs? See `README.zh-CN.md`.

## Highlights

- Long-form consistency: style bible + storyboard + shot graph keep identity and visual style consistent across shots and over time.
- LangGraph orchestration: explicit DAG of nodes enables retries, branching, limited parallelism, and clear observability of each step.
- Mock-first, production-ready: run locally without network using deterministic mocks; flip a flag to call real services.
- Inspectable runs: every step logs prompts, responses, and artefacts to `runs/` and caches media under `assets/` for reproducibility.
- Pluggable providers: Qwen‑VL (perception), DeepSeek/OpenAI‑compatible (reasoning), Volcengine 即梦 (video). Swap in your own with the same interfaces.
- Simple CLI + tests: one‑line command to generate a video; unit tests validate core pipeline in mock mode.

## Prerequisites

- Python 3.10 or newer (Python 3.9 lacks `dataclasses` slots support used in the pipeline)
- macOS or Linux shell with `bash`
- Optional libraries for real API calls:
  - `langgraph`, `langchain-core`
  - `dashscope` (Qwen-VL)
  - `openai` (DeepSeek-compatible client)
  - `volcengine-python-sdk`, `requests` (即梦)

> **Tip:** The default run configuration enables mock generation, so you can skip the optional dependencies until you are ready to integrate live services.

## Environment Setup

```bash
python3 -m venv .venv
source .venv/bin/activate

# Install project dependencies (only stdlib is required for mock mode).
# Install optional packages if you plan to call real services:
pip install langgraph langchain-core dashscope openai volcengine-python-sdk requests
```

Ensure you are using Python 3.10+. On macOS you can install a newer interpreter via Homebrew (`brew install python@3.11`) and point the virtual environment at it.

## Running the Pipeline

The repository exposes a Python CLI entry point:

```bash
python run.py "让宠物在魔法森林完成奇幻冒险" /path/to/pet1.png [/path/to/pet2.png ...] --duration 30 --fps 24
```

### Execution modes

- **Mock mode (default):** When `PVGEN_ENABLE_MOCKS=true` (default) the pipeline uses local mock clients that create `.txt` artefacts. No external network calls are made.
- **Live mode:** Set `PVGEN_ENABLE_MOCKS=false` and provide credentials for the upstream services:

  ```bash
  export PVGEN_ENABLE_MOCKS=false
  export QWEN_API_KEY=...
  export DEEPSEEK_API_KEY=...
  export JIMENG_API_KEY=...        # Accepts AK:SK or set JIMENG_API_SECRET separately
  python run.py "prompt" /path/image.png
  ```

During a run each node prints compact JSON snapshots to stdout and writes prompt/response logs under `runs/<run_id>/`. Generated assets cache under `assets/`, while the final manifest and report live in `outputs/`.

With LangGraph enabled, nodes execute according to the defined graph, improving stability and making longer, coherent videos easier to achieve. When LangGraph is not available, the pipeline falls back to a sequential executor.

## Testing

The unit tests rely on the mock mode and expect Python 3.10+:

```bash
python -m unittest discover -s tests
```

If you encounter `TypeError: dataclass() got an unexpected keyword argument 'slots'`, upgrade Python to meet the minimum version.

## Project Structure

- `run.py` – CLI entry point
- `pvgen/pipeline.py` – orchestrator that builds a LangGraph graph when available or falls back to sequential execution
- `pvgen/nodes/` – individual pipeline steps (ingest, describe pet, style bible, storyboard, keyframes, video generation, QC, assembly, report)
- `pvgen/services/` – client wrappers for Qwen, DeepSeek, 即梦 (each with mock fallbacks)
- `pvgen/utils/` – shared helpers for prompt loading, logging, and file IO
- `tests/` – regression suite using mock backends
- `flow.md`, `agent.md` – detailed design documents describing the overall process

## Live API Checklist

1. Collect credentials: Qwen-VL (`QWEN_API_KEY`), DeepSeek (`DEEPSEEK_API_KEY`), 即梦 (`JIMENG_API_KEY` and optionally `JIMENG_API_SECRET`).
2. Install the optional dependencies listed in *Prerequisites*.
3. Export `PVGEN_ASSETS_DIR` / `PVGEN_RUNS_DIR` if you want custom cache locations.
4. Run `python run.py` with `PVGEN_ENABLE_MOCKS=false`.
5. Inspect `outputs/<run_id>-final.txt` for the final manifest and the `assets/` folder for generated media.

With these steps you can develop against the mock pipeline locally and switch to real services once credentials and network access are available.
