*This project has been created as part of the 42 curriculum by ysimonne, kkraft.*

# Agent Smith

An autonomous **code agent** framework. It gives an LLM a
**Thought → Code → Observation** loop: the model reasons, writes executable
Python, runs it in a secured sandbox, reads the result, and iterates until the
task is solved. Tools are served over the **Model Context Protocol (MCP)** and
called as plain Python functions from inside the sandbox.

## Description

The goal is to solve real coding tasks without a human in the loop, on two
benchmarks:

- **MBPP** — Mostly Basic Python Problems (algorithmic functions).
- **SWE-bench** — fixing real bugs in real repositories, inside Docker.

The same agent loop drives both benchmarks; only the prompt, the MCP tool
server, and the execution limits change. The framework also **benchmarks
multiple LLMs** across several providers to compare success rate and iteration
efficiency. The orchestration loop is written from scratch — no
LangGraph/CrewAI/smolagents-style library is used.

Key properties:

- Multi-provider, multi-key LLM layer with rotation, fallback and backoff.
- Format-agnostic code extraction (Python blocks, XML, JSON/Hermes, ReAct).
- A configurable sandbox that is the security boundary for untrusted code.
- MCP tool servers for MBPP and SWE-bench, callable over stdio or HTTP.

## Instructions

### Requirements

- **Python 3.10** (see [.python-version](.python-version))
- **[uv](https://docs.astral.sh/uv/)** as package manager
- **Docker** (SWE-bench only — tasks run inside their official images)

### Install

```bash
uv sync
```

### API keys

Keys are loaded from a `.env` file (or the environment) — **never hardcoded**.
Any variable whose name contains `API_KEY` is auto-discovered and used, and
**several keys per provider are rotated** to survive rate limits:

```dotenv
GROQ_API_KEY_1=...
GROQ_API_KEY_2=...
OPENROUTER_API_KEY=...
```

### Run the agents

The CLI matches the evaluation interface (`--model-name`, `--provider-url`).

```bash
# MBPP
uv run python -m agent_mbpp \
  --task-file cache/mbpp_task.json \
  --output cache/mbpp_solution.json \
  --model-name "llama-3.3-70b-versatile" \
  --provider-url "https://api.groq.com/openai/v1"

# SWE-bench
uv run python -m agent_swebench \
  --task-file cache/swebench_task.json \
  --output cache/swebench_solution.json \
  --model-name "meta-llama/llama-4-scout-17b-16e-instruct" \
  --provider-url "https://api.groq.com/openai/v1"
```

Each run writes a `solution.json` (`SolutionOutput`) holding the final solution
and, for every step, the raw LLM output, the code sent to the sandbox, the
execution result and token/latency metrics.

### Run the sandbox alone

```bash
uv run sandbox                                              # interactive, prompts for transport
uv run sandbox --mcp-stdio "python mcp_tools_mbpp.py" \
               --config-file srcs/sandbox/config_file.json  # stdio + custom config
uv run sandbox --mcp-server <URL>                           # streamable HTTP
```

### Run an MCP tool server alone

```bash
uv run python mcp_tools_mbpp.py            # stdio (default)
uv run python mcp_tools_mbpp.py --http     # streamable HTTP
uv run python mcp_tools_swebench.py        # SWE-bench tools
```

### Tests

```bash
uv run pytest
```

## System architecture

Every layer is decoupled: the orchestrator does not know which benchmark it
runs, the sandbox does not know about the LLM, and the tools live in a separate
MCP process.

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
| Orchestrator | [srcs/llm/orchestrator.py](srcs/llm/orchestrator.py) | The agent loop; enforces iteration/token/time budgets |
| LLM layer | [srcs/llm/](srcs/llm/) | `LLMClient`, `LLMManager`, `CodeExtractor`, provider abstraction |
| Sandbox | [srcs/sandbox/](srcs/sandbox/) | Isolated execution + security + MCP bridge + dynamic manual |
| MCP tools | [mcp_tools_mbpp.py](mcp_tools_mbpp.py), [mcp_tools_swebench.py](mcp_tools_swebench.py) | Tools exposed to the agent, served over MCP |
| Data models | [srcs/models.py](srcs/models.py) | Pydantic contracts (`SandboxConfig`, task inputs, `StepMetrics`, `SolutionOutput`) |
| Entry points | [srcs/mbpp/agent_mbpp.py](srcs/mbpp/agent_mbpp.py), [srcs/swe_bench/swebench_agent.py](srcs/swe_bench/swebench_agent.py) | Wire the pieces together and expose the CLI |

## Agent loop

Implemented in [srcs/llm/orchestrator.py](srcs/llm/orchestrator.py). Each
iteration:

1. **Budget check** — stop early if the wall-clock time, or the projected
   cumulative input/output tokens, would exceed the limit.
2. **Thought + Code** — the LLM generates text; `CodeExtractor` pulls out a
   single code block. Generation stops on `<end_code>` so the model cannot
   hallucinate its own observation.
3. **Observation** — the code runs in the sandbox and the result (stdout +
   traceback) is fed back as the next user message.
4. **Termination** — the loop ends when the sandbox reports `final_answer`, a
   limit is reached, or the LLM layer fails.

The sandbox never fails silently — the LLM is always told what happened:
no code block found, timeout hit, output truncated, or an execution error.
Limits are parameters, so each benchmark passes its own:

| Metric | MBPP | SWE-bench |
|--------|------|-----------|
| Max iterations | 10 | 30 |
| Max input tokens (cumulative) | 6 000 | 300 000 |
| Max output tokens (cumulative) | 1 500 | 10 000 |
| Timeout | 120 s | 900 s |

For MBPP and SWE-bench alike, a `final_answer` is **re-validated in the
harness** against the real tests before being accepted; a failing patch is
rejected and the failure is sent back to the model to fix.

## Sandbox design

The sandbox ([srcs/sandbox/sandbox.py](srcs/sandbox/sandbox.py)) is the safety
boundary between autonomous code and the host. It runs untrusted code in a
**separate `multiprocessing` process** and enforces, using only the standard
library (no `RestrictedPython`):

- **Import allowlist** — only modules from `authorized_imports` can be imported.
- **Filesystem allowlist** — `open()` is restricted to `allowed_directories`
  (`/testbed`, `/tmp/agent`); file descriptors are refused.
- **No network** — `socket.socket` is replaced by a blocker.
- **No dunder access** — the AST is walked and `__…__` attribute access is
  rejected before execution.
- **Restricted builtins** — `eval`, `exec`, `compile`, `getattr`, `globals`,
  `input`, … are removed from the namespace.
- **Memory limit** — `RLIMIT_AS` caps RAM (default 512 MB).
- **Timeout** — the parent kills the child if a code block overruns
  (default 5 s). This applies only to sandboxed code; MCP tool actions
  (e.g. running tests in Docker) run outside the sandbox and are not bound by
  it.

`final_answer()` inherits from `BaseException`, so a bare `except Exception` in
the model's code cannot swallow it — it always reaches the loop.
`KeyboardInterrupt` and `SystemExit` are re-raised for a clean shutdown. Oversized
tool output is truncated with an explicit marker. Config is a Pydantic model
loadable from JSON (see [srcs/sandbox/config_file.json](srcs/sandbox/config_file.json)).

## Tool implementation details

Tools are exposed by an MCP server (`FastMCP`) and callable as Python functions
inside the sandbox. The sandbox discovers them **dynamically** from the
connected server and builds the manual injected into the system prompt, so an
**unknown MCP server** is supported without code changes. Both **stdio** and
**streamable HTTP** transports work. `final_answer` is provided by the sandbox
itself, not by any MCP server.

**MBPP** — [mcp_tools_mbpp.py](mcp_tools_mbpp.py):

- `run_tests(code, test_list, test_imports)` — runs the candidate against the
  assert-based tests and returns a `PASS`/`FAIL` report.

**SWE-bench** — [mcp_tools_swebench.py](mcp_tools_swebench.py), each call
executed inside the task's Docker container (network disabled, cleaned up after
the run):

| Tool | Purpose |
|------|---------|
| `read_file(filepath, start_line, end_line)` | Read a file with line numbers (`cat -n` style) |
| `edit_file(filepath, old_str, new_str)` | Exact-string replace, with hints when the anchor is not found |
| `list_files(directory, pattern)` | List files matching a glob |
| `search_code(pattern, file_pattern)` | grep-like search (`/path:line content`) |
| `search_function_or_class_definition_in_code(name)` | Locate a `def`/`class` |
| `find_references(name, filepath, line)` | Find usages of a symbol |
| `run_command(command, workdir)` | Run a shell command; returns stdout/stderr/exit code |
| `run_tests()` | Run the evaluation script |
| `get_patch()` | `git -c core.fileMode=false diff` of the changes |

## Benchmark results and analysis

8 models were compared on the **same 5 SWE-bench tasks** — `django__django-11066`,
`django__django-13109`, `pydata__xarray-4629`,
`scikit-learn__scikit-learn-13439`, `sympy__sympy-18189` — drawn from four
different repositories (Django, xarray, scikit-learn, SymPy) and spanning a
one-line fix to a large-context change, to avoid overfitting to one codebase or
one difficulty level. Raw per-run traces (`solution.json` + logs) are in
[benchmark/](benchmark/); the full write-up (per-`model×task` tokens/time,
provider reliability, intermediary metrics and an ablation) is in
[BENCHMARK_REPORT.md](BENCHMARK_REPORT.md).

| Model | Provider | 11066 | 13109 | xarray-4629 | scikit-13439 | sympy-18189 | Solved |
|-------|----------|:---:|:---:|:---:|:---:|:---:|:---:|
| meta-llama/llama-4-maverick:fre | OpenRouter | ✅ | ❌ | ✅ | ✅ | ✅ | **4/5** |
| meta-llama/llama-4-scout-17b | Groq | ✅ | ❌ | ✅ | ✅ | ✅ | **4/5** |
| mistral-large-latest | Mistral | ✅ | ✅ | ✅ | ❌ | ✅ | **4/5** |
| deepseek/deepseek-v4-flash | OpenRouter | ❌ | ❌ | ❌ | ✅ | ✅ | 2/5 |
| llama-3.3-70b-versatile | Groq | ✅ | ❌ | ✅ | ❌ | ❌ | 2/5 |
| llama-3.1-8b-instant | Groq | ❌ | ❌ | ❌ | ❌ | ❌ | 0/5 |
| mistral-medium-latest | Mistral | ❌ | ❌ | ❌ | ❌ | ❌ | 0/5 |
| qwen/qwen3.6-27b | Groq | ❌ | ❌ | ❌ | ❌ | ❌ | 0/5 |

**Analysis:**

- **llama-4-maverick and llama-4-scout** are the choice for the final pipeline:
  4/5 solved and **100 % availability** (their only misses are on the hardest
  task, `django-13109`, where maverick hit the 300k input-token ceiling and
  scout the 30-iteration cap — not a wrong fix). On the tasks they solve, maverick
  converges in ~5–6 iterations under ~20k input tokens, and scout is the fastest
  endpoint at ~700 ms/request.
- **mistral-large** also solves 4/5 and is the **only** model to crack the
  hardest task (`django-13109`), but it is the slowest endpoint (~6.3 s/request)
  and the most verbose — kept as a heavyweight fallback, not the default.
- **deepseek-v4-flash** is genuinely capable (it solved the two longest-context
  tasks at 20 iterations) but **3 of its 5 runs died to provider quota
  exhaustion** (`all targets exhausted`), so its 2/5 is a reliability artifact,
  not a reasoning verdict.
- **llama-3.1-8b, qwen3.6-27b and mistral-medium** are disregarded: 0/5. The two
  small Groq models never converged and were throttled into ~300 retries each;
  mistral-medium is the most token-hungry model (up to 200k input tokens on a
  *failed* task) yet solved nothing.

A recurring lesson: **the dominant failure mode was provider availability, not
reasoning** — 22 of 40 runs (55 %) ended in `all targets exhausted` (rate
limits / quota) versus only 2 that hit a token/iteration limit. This is exactly
what the `LLMManager` multi-key rotation + fallback + backoff is built to
absorb, and it moves the solve rate more than picking a marginally smarter model.

## Resources

Documentation and references used for the topic:

- Model Context Protocol — <https://modelcontextprotocol.io> and the Python SDK
  (`mcp` / `FastMCP`).
- SWE-bench — <https://www.swebench.com> (dataset and evaluation harness).
- MBPP dataset — <https://github.com/google-research/google-research/tree/master/mbpp>.
- Hugging Face *smolagents* write-ups on **code agents** (Thought → Code →
  Observation), used as conceptual inspiration only — not as a dependency.
- OpenAI-compatible chat completions API (used for every provider: Groq,
  OpenRouter, …).
- Pydantic v2 and `python-fire` documentation.

### Use of AI

AI assistants were used as a coding aid, reviewed and adapted by the team:

- **Docstrings and inline documentation** across `srcs/`, then proofread.
- **This README** — drafted from the codebase and edited for accuracy.
- **Debugging help** on the sandbox isolation and the SWE-bench Docker tools.
- **Prompt wording** for the MBPP and SWE-bench system prompts.

Core architecture, the agent loop, the sandbox security model and the MCP tools
were designed and implemented by the team. The benchmark data comes from real
runs, not from AI-generated numbers.
