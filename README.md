# Agent Smith — an autonomous code agent

> A framework that gives an LLM a **Thought → Code → Observation** loop: the model
> reasons, writes executable Python, runs it in a **home-made security sandbox**, reads
> the result, and iterates until the task is solved. Tools are served over the
> **Model Context Protocol (MCP)** and called as plain Python functions from inside
> the sandbox. The orchestration loop is written from scratch — **no LangGraph /
> CrewAI / smolagents-style dependency**.

It solves real coding tasks with no human in the loop, on two benchmarks — **MBPP**
(algorithmic Python problems) and **SWE-bench** (fixing real bugs in real repositories,
inside Docker) — and **benchmarks 8 LLMs across 3 providers** to compare solve rate,
token cost and reliability.

**Stack:** Python 3.10 (type-hinted) · `mcp` / FastMCP · Pydantic v2 · OpenAI-compatible
providers (Groq, OpenRouter, Mistral) · Docker · `multiprocessing` + `ast` for
isolation · `uv`.

---

## Authors & contributions

Built by a team of two over the 42 curriculum.

### Youl Simonnet — [@youl-S](https://github.com/youl-S)
**Execution security & the MCP client.**
- **Sandbox** ([srcs/sandbox/sandbox.py](srcs/sandbox/sandbox.py), ) — the
  security boundary that runs untrusted, model-generated code. Subprocess isolation,
  AST-level `__dunder__` blocking, import/filesystem allowlists, network kill switch,
  `RLIMIT_AS` memory cap, timeout enforcement, and `final_answer()` as a `BaseException`
  the model's `except Exception` cannot swallow.
- **MCP client** ([srcs/sandbox/mcp_client.py](srcs/sandbox/mcp_client.py)) — a
  synchronous wrapper over the async MCP SDK; drives **stdio** and **streamable HTTP**
  transports and performs **dynamic tool discovery** so any MCP server plugs in with no
  code change.

### Kévin Kraft — [@Kevin-Krt](https://github.com/Kevin-Krt/Kevin-Krt)
**Agent loop, LLM layer, MCP tool servers & the agents.**
- **Agent orchestration loop** ([srcs/llm/orchestrator.py](srcs/llm/orchestrator.py)) —
  the Thought → Code → Observation loop and its iteration / token / time budgets.
- **LLM layer** ([srcs/llm/](srcs/llm/)) — `LLMClient` / `LLMManager` (multi-provider,
  multi-key rotation, fallback and backoff) and the format-agnostic `CodeExtractor`
  ([srcs/llm/code_extractor.py](srcs/llm/code_extractor.py)).
- **MCP tool servers** — [mcp_tools_swebench.py](mcp_tools_swebench.py) (Docker-executed
  file/search/edit/test tools) and [mcp_tools_mbpp.py](mcp_tools_mbpp.py).
- **Agent entry points** ([srcs/mbpp/](srcs/mbpp/), [srcs/agent_swebench/](srcs/agent_swebench/)).

### Together
The overall **decoupled architecture** and the **benchmark study** — methodology, model
selection and analysis across 8 LLMs.

---

## Architecture

Every layer is decoupled: the orchestrator does not know which benchmark it runs, the
sandbox does not know about the LLM, and the tools live in a separate MCP process.

```
task ──► Orchestrator (agent loop, benchmark-agnostic)
             │  messages
             ▼
        LLMManager ──► LLMClient ──► provider (OpenAI-compatible API)
             │  key rotation + fallback + backoff
             ▼  raw text
        CodeExtractor ──► extracts ONE code block (python / xml / json / react)
             │  code
             ▼
        Sandbox.run(code) ──► isolated subprocess
             │                   │  tool call (stub)
             │                   ▼
             │              McpClient ──► MCP server (mcp_tools_*.py)
             ▼
        result dict {final_answer | success | error}
             │
             ▼
        SolutionOutput ──► solution.json
```

| Layer | Location | Responsibility |
|-------|----------|----------------|
| Orchestrator | [srcs/llm/orchestrator.py](srcs/llm/orchestrator.py) | The agent loop; enforces iteration / token / time budgets |
| LLM layer | [srcs/llm/](srcs/llm/) | `LLMClient`, `LLMManager`, `CodeExtractor`, provider abstraction |
| Sandbox | [srcs/sandbox/](srcs/sandbox/) | Isolated execution + security + MCP bridge + dynamic manual |
| MCP tools | [mcp_tools_mbpp.py](mcp_tools_mbpp.py), [mcp_tools_swebench.py](mcp_tools_swebench.py) | Tools exposed to the agent, served over MCP |
| Data models | [srcs/models.py](srcs/models.py) | Pydantic contracts (`SandboxConfig`, task inputs, `StepMetrics`, `SolutionOutput`) |
| Entry points | [srcs/mbpp/agent_mbpp.py](srcs/mbpp/agent_mbpp.py), [srcs/agent_swebench/agent_swebench.py](srcs/agent_swebench/agent_swebench.py) | Wire the pieces together and expose the CLI |

## The agent loop

Implemented in [srcs/llm/orchestrator.py](srcs/llm/orchestrator.py). Each iteration:

1. **Budget check** — stop early if wall-clock time, or the *projected* cumulative
   input/output tokens, would exceed the limit.
2. **Thought + Code** — the LLM generates text; `CodeExtractor` pulls out a single code
   block. Generation stops on `<end_code>` so the model cannot hallucinate its own
   observation.
3. **Observation** — the code runs in the sandbox and the result (stdout + traceback) is
   fed back as the next user message.
4. **Termination** — ends when the sandbox reports `final_answer`, a limit is reached, or
   the LLM layer fails.

The sandbox **never fails silently** — the LLM is always told what happened (no code
block, timeout, truncated output, execution error). Limits are parameters, so each
benchmark passes its own:

| Metric | MBPP | SWE-bench |
|--------|------|-----------|
| Max iterations | 10 | 30 |
| Max input tokens (cumulative) | 6 000 | 300 000 |
| Max output tokens (cumulative) | 1 500 | 10 000 |
| Timeout | 120 s | 900 s |

A `final_answer` is **re-validated against the real tests** before being accepted (a
`validate_answer` check re-runs the task's tests); a failing solution is rejected and its
failure is sent back to the model to fix instead of being trusted on the model's word.

## Sandbox design — the security boundary

The sandbox ([srcs/sandbox/sandbox.py](srcs/sandbox/sandbox.py)) runs untrusted code in a
**separate `multiprocessing` process** and enforces, using **only the standard library**
(no `RestrictedPython`):

- **Import allowlist** — only modules in `authorized_imports` can be imported.
- **Filesystem allowlist** — `open()` is restricted to `allowed_directories`; file
  descriptors are refused.
- **No network** — `socket.socket` is replaced by a blocker.
- **No dunder access** — the AST is walked and `__…__` attribute access is rejected
  before execution.
- **Restricted builtins** — `eval`, `exec`, `compile`, `getattr`, `globals`, `input`, …
  are removed from the namespace.
- **Memory & time caps** — `RLIMIT_AS` bounds RAM (default 512 MB); the parent kills a
  child that overruns the timeout.


## MCP tools

Tools are exposed by a FastMCP server and callable as plain Python functions inside the
sandbox. The sandbox **discovers them dynamically** and builds the manual injected into
the system prompt, so an unknown MCP server works with no code change.
`final_answer` is provided by the sandbox itself, not by any server.

- **MBPP** ([mcp_tools_mbpp.py](mcp_tools_mbpp.py)): `run_tests` runs the candidate
  against assert-based tests and returns a `PASS`/`FAIL` report.
- **SWE-bench** ([mcp_tools_swebench.py](mcp_tools_swebench.py)): each call runs **inside
  the task's Docker container** (network disabled) — `read_file`, `edit_file`,
  `list_files`, `search_code`, `search_function_or_class_definition_in_code`,
  `find_references`, `run_command`, `run_tests`, `get_patch`.

## Benchmark results

8 models were compared on the **same 5 SWE-bench tasks** drawn from 4 repositories
(Django, xarray, scikit-learn, SymPy), from a one-line fix to a large-context change.
Raw traces are in [benchmark/](benchmark/); the full write-up is in
[BENCHMARK_REPORT.md](BENCHMARK_REPORT.md).

| Model | Provider | Solved |
|-------|----------|:---:|
| meta-llama/llama-4-maverick | OpenRouter | **4/5** |
| meta-llama/llama-4-scout-17b | Groq | **4/5** |
| mistral-large-latest | Mistral | **4/5** |
| deepseek/deepseek-v4-flash | OpenRouter | 2/5 |
| llama-3.3-70b-versatile | Groq | 2/5 |
| llama-3.1-8b-instant / qwen3.6-27b / mistral-medium | Groq / Mistral | 0/5 |

**Key finding:** the dominant failure mode was **provider availability, not reasoning** —
22 of 40 runs (55 %) ended in `all targets exhausted` (rate limits / quota) versus only 2
that hit a token/iteration limit. This is exactly what the `LLMManager` multi-key
rotation + fallback + backoff absorbs, and it moves the solve rate more than picking a
marginally smarter model. `llama-4-maverick` and `llama-4-scout` (4/5 at 100 %
availability) were chosen for the final pipeline, with `mistral-large` as a heavyweight
fallback.

## Quickstart

**Requirements:** Python 3.10 · [uv](https://docs.astral.sh/uv/) · Docker (SWE-bench only).

```bash
uv sync
```

API keys are loaded from `.env`. Any variable whose name contains
`API_KEY` is auto-discovered, and **several keys per provider are rotated** to survive
rate limits:

```dotenv
GROQ_API_KEY_1=...
GROQ_API_KEY_2=...
OPENROUTER_API_KEY=...
```

Run the agents (the CLI matches the evaluation interface):

```bash
# MBPP
uv run python -m agent_mbpp \
  --task-file cache/mbpp_task.json --output cache/mbpp_solution.json \
  --model-name "llama-3.3-70b-versatile" \
  --provider-url "https://api.groq.com/openai/v1"

# SWE-bench
uv run python -m agent_swebench \
  --task-file cache/swebench_task.json --output cache/swebench_solution.json \
  --model-name "meta-llama/llama-4-scout-17b-16e-instruct" \
  --provider-url "https://api.groq.com/openai/v1"
```

Each run writes a `solution.json` holding the final solution and, per step, the raw LLM
output, the code sent to the sandbox, the execution result and token/latency metrics.

Run the sandbox standalone against a tool server. Over **stdio** the sandbox spawns
the server itself:

```bash
uv run sandbox --mcp-stdio "python mcp_tools_mbpp.py" --config-file sandbox_template.json
```

Over **streamable HTTP**, start the server first, then point the sandbox at the URL it
prints on startup (default `http://127.0.0.1:8000/mcp`):

```bash
uv run python mcp_tools_swebench.py --http                # terminal 1 — start the tool server
uv run sandbox --mcp-server "http://127.0.0.1:8000/mcp"   # terminal 2 — connect the sandbox
```

<sub>Created as part of the 42 curriculum by <a href="https://github.com/youl-S">ysimonne</a> and <a href="https://github.com/Sacrifist13">kkraft</a>.</sub>
