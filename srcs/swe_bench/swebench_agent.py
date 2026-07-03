from srcs.models import SWEBenchTaskInput, SolutionOutput
from srcs.sandbox.sandbox import Sandbox
from dotenv import load_dotenv
from fire import Fire
from srcs.llm import (
    CodeExtractor,
    Orchestrator,
    ProviderTarget,
    LLMManager,
    LLMClient,
)
from pathlib import Path
import subprocess
import json
import os


def build_system_prompt(man_sandbox: str) -> str:
    return f"""You are an expert software engineer resolving codebase bugs \
through a Thought -> Code -> Observation loop.

# Response format
Each turn: write a brief Thought, then exactly ONE Python code block with
exactly ONE tool call, ending with <end_code>:

```python
# one tool call here
```
<end_code>

You MUST call every tool with KEYWORD arguments only (name=value), never
positional.
- Correct:   read_file(filepath="/testbed/x.py")
- Incorrect: read_file("/testbed/x.py")

The code runs in an isolated sandbox containing the repository at /testbed.
You then receive an Observation and continue.

# Sandbox manual
The following tools are available as Python functions inside the sandbox:

{man_sandbox}

# How to solve
1. Explore the codebase to locate and understand the bug.
2. Edit the files needed to fix it.
3. Run the tests to check your fix.
4. When the tests pass, call get_patch() to obtain your git diff, then
   call final_answer(code=<that diff>) so the patch is submitted.

# Example
Thought: I'll look for the faulty function first.
```python
search_code(pattern="def calculate_total", file_pattern="*.py")
```
<end_code>
"""


def build_task_message(task: SWEBenchTaskInput) -> str:
    """Build the user message describing the SWE-bench issue to fix."""
    parts = [
        "Resolve the following GitHub issue in the repository mounted at "
        "/testbed.",
    ]
    if task.repo:
        parts.append(f"Repository: {task.repo}")
    parts.append(f"\nIssue:\n{task.problem_statement}")

    if task.hints_text:
        truncated_hints = task.hints_text[:2000]
        parts.append(f"\nHints:\n{truncated_hints}\n... [TRUNCATED]")

    parts.append(
        "\nExplore the codebase with the available tools, edit the files "
        "needed to fix the issue, and run the tests to verify your fix. "
        "When the tests pass, call get_patch() to get your diff, then call "
        "final_answer with that diff as the code argument."
    )
    return "\n".join(parts)


def discover_key_vars() -> list[str]:
    """Return all env var names that look like API keys (contain API_KEY)."""
    load_dotenv()
    return sorted(
        name
        for name in os.environ
        if "API_KEY" in name and os.environ.get(name)
    )


def _cleanup(sandbox: Sandbox, docker_image: str) -> None:
    """Best-effort teardown: close the MCP client and remove containers."""
    try:
        sandbox.mcp_client.close()
    except Exception:
        pass
    try:
        subprocess.run(
            "docker ps -aq --filter "
            f"ancestor={docker_image} | xargs -r docker rm -f",
            shell=True,
            capture_output=True,
            text=True,
            timeout=60,
        )
    except Exception:
        pass


def run_swebench(
    task: SWEBenchTaskInput,
    model_name: str,
    provider_url: str,
) -> SolutionOutput:
    os.environ["SWE_DOCKER_IMG"] = task.docker_image
    os.environ["SWE_EVAL_SCRIPT"] = task.eval_script

    target = ProviderTarget(
        name="provider",
        base_url=provider_url,
        model=model_name,
        key_env_vars=discover_key_vars(),
    )
    manager = LLMManager(targets=[target], client=LLMClient(timeout_s=90.0))
    sandbox = Sandbox()
    sandbox._launch_server("stdio", "python mcp_tools_swebench.py")

    try:
        orchestrator = Orchestrator(
            manager=manager,
            extractor=CodeExtractor,
            sandbox=sandbox,
            system_prompt=build_system_prompt(sandbox.get_man()),
            stop_sequences=["<end_code>"],
            max_iterations=30,
            max_input_tokens=300000,
            max_output_tokens=10000,
            max_time_seconds=900,
        )
        return orchestrator.run(
            task_id=str(task.instance_id),
            benchmark="swebench",
            task_message=build_task_message(task),
            max_tokens=10000,
        )
    finally:
        _cleanup(sandbox, task.docker_image)


def run_swebench_cli(
    task_file: str = None,
    output: str = None,
    model_name: str = None,
    provider_url: str = None,
) -> None:
    data: dict = {}
    try:
        with open(task_file, "r") as f:
            data = json.loads(f.read())
        parse_task = SWEBenchTaskInput.model_validate(data)
        solution_output = run_swebench(
            parse_task, model_name=model_name, provider_url=provider_url
        )
    except FileNotFoundError:
        solution_output = SolutionOutput(
            task_id=str(data.get("instance_id", "unknown")),
            benchmark="swebench",
            success=False,
            solution="",
            iterations=0,
            total_requests=0,
            total_input_tokens=0,
            total_output_tokens=0,
            total_time_seconds=0.0,
            error="task file not found",
        )
    except Exception as e:
        solution_output = SolutionOutput(
            task_id=str(data.get("instance_id", "unknown")),
            benchmark="swebench",
            success=False,
            solution="",
            iterations=0,
            total_requests=0,
            total_input_tokens=0,
            total_output_tokens=0,
            total_time_seconds=0.0,
            error=f"agent crashed: {type(e).__name__}: {e}",
        )

    if output:
        path = Path(output)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(solution_output.model_dump_json(indent=4))
    else:
        print("WTF")


def main() -> None:
    Fire(run_swebench_cli)


if __name__ == "__main__":
    try:
        main()
    except Exception as e:
        print(f"Error {e}")
