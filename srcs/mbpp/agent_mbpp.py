from fire import Fire
from dotenv import load_dotenv
from pathlib import Path
from srcs.models import MBPPTaskInput, SolutionOutput
from srcs.sandbox.sandbox import Sandbox
from srcs.llm import (
    LLMClient,
    LLMManager,
    ProviderTarget,
    CodeExtractor,
    Orchestrator,
)
import json
import os


def build_system_prompt(sandbox_manual: str) -> str:
    return f"""You are a coding agent that solves Python problems through a \
Thought -> Code -> Observation loop.

# Response format
Each turn: write a brief Thought, then exactly ONE Python code block ending \
with <end_code>:

```python
# your code here
```
<end_code>

The code runs in a sandbox. You then receive an Observation and continue.

# Calling tools
Call every tool with KEYWORD arguments only (name=value), never positional.
- Correct:   final_answer(code=my_code)
- Incorrect: final_answer(my_code)

# Sandbox manual
{sandbox_manual}

# How to solve
1. Write the solution function.
2. Optionally call run_tests(...) to check it before submitting. This is
   recommended but not required.
3. Call final_answer(code=...) with the complete solution to end the task.
   You may call it directly if you are confident the solution is correct.

# Example
Thought: Simple sum. I'm confident, so I submit directly.
```python
final_answer(code="def add(a, b):\\n    return a + b")
```
<end_code>
"""


def build_task_message(task: MBPPTaskInput) -> str:
    """User message. Gives the real tests as copyable literals so the model
    can pass them to run_tests if it chooses to."""
    test_list_lit = json.dumps(task.test_list)
    test_imports_lit = json.dumps(task.test_imports)
    return (
        f"Problem: {task.task_definition}\n\n"
        f"Function signature:\n{task.function_definition}\n\n"
        f"If you want to check your solution, call run_tests like this:\n"
        f"  run_tests(code=your_code, test_list={test_list_lit}, "
        f"test_imports={test_imports_lit})\n\n"
        f"When ready, call final_answer(code=your_code) with the working "
        f"function as a string."
    )


def discover_key_vars() -> list[str]:
    """Return all env var names that look like API keys (contain API_KEY)."""
    load_dotenv()
    return sorted(
        name
        for name in os.environ
        if "API_KEY" in name and os.environ.get(name)
    )


def run_mbpp(
    task: MBPPTaskInput,
    model_name: str,
    provider_url: str,
) -> SolutionOutput:
    """Run the MBPP agent on a single task and return its output."""
    target = ProviderTarget(
        name="provider",
        base_url=provider_url,
        model=model_name,
        key_env_vars=discover_key_vars(),
    )
    manager = LLMManager(
        targets=[target],
        client=LLMClient(timeout_s=60.0),
    )
    sandbox = Sandbox()
    sandbox._launch_server("stdio", "python mcp_tools_mbpp.py")

    try:
        orchestrator = Orchestrator(
            manager=manager,
            extractor=CodeExtractor,
            sandbox=sandbox,
            system_prompt=build_system_prompt(sandbox.get_man()),
            stop_sequences=["<end_code>"],
            max_iterations=10,
        )
        return orchestrator.run(
            task_id=str(task.task_id),
            benchmark="mbpp",
            task_message=build_task_message(task),
            max_tokens=1500,
        )
    finally:
        try:
            sandbox.mcp_client.close()
        except Exception:
            pass


def run_mbpp_cli(
    task_file: str = None,
    output: str = None,
    model_name: str = None,
    provider_url: str = None,
) -> None:
    try:
        with open(task_file, "r") as f:
            data = json.loads(f.read())
        task_input = MBPPTaskInput.model_validate(data)
        result = run_mbpp(task_input, model_name, provider_url)
    except Exception as e:
        result = SolutionOutput(
            task_id=(
                str(data.get("task_id", "unknown"))
                if "data" in dir()
                else "unknown"
            ),
            benchmark="mbpp",
            success=False,
            solution="",
            error=f"agent crashed: {type(e).__name__}: {e}",
        )

    if output:
        path = Path(output)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(result.model_dump_json(indent=4))


def main() -> None:
    Fire(run_mbpp_cli)


if __name__ == "__main__":
    main()
