import os
import json

from fire import Fire

from dotenv import load_dotenv

from srcs.models import MBPPTaskInput, SolutionOutput
from srcs.sandbox.sandbox import Sandbox
from srcs.llm import (
    LLMClient,
    LLMManager,
    ProviderTarget,
    CodeExtractor,
    Orchestrator,
)

# Provisional manual
SANDBOX_MANUAL = (
    "- run_tests(code, test_list, test_imports): run candidate code "
    "against the given asserts; returns a PASS/FAIL report.\n"
    "- final_answer(code): submit the final solution code and end the task."
)


def build_system_prompt(sandbox_manual: str) -> str:
    """Return the full system prompt with the sandbox manual injected."""
    return f"""You are a coding agent that solves Python problems through a \
Thought -> Code -> Observation loop.

# Response format
Each turn: write a brief Thought, then exactly ONE Python code block with
exactly ONE tool call (either run_tests OR final_answer, never both),
ending with <end_code>.

You MUST call every tool with KEYWORD arguments only (name=value).
Never use positional arguments.
- Correct:   run_tests(code=code, test_list=tests, test_imports=[])
- Incorrect: run_tests(code, tests, [])

You will NOT see the result of run_tests if you call final_answer in the
same block. You MUST wait for the run_tests Observation in the NEXT turn
before calling final_answer.

The code runs in a sandbox. You then receive an Observation and continue.

# Sandbox manual
The following tools are available as Python functions inside the sandbox:

{sandbox_manual}

# How to solve
1. Write the solution function.
2. You MUST call run_tests(...) at least once and see it PASS before
   submitting. Never call final_answer without having run run_tests first.
3. Once run_tests reports PASS, call final_answer(...) with the complete
   solution.

# Example
Thought: I write the function, then verify it with run_tests before submitting.
```python
code = "def add(a, b):\\n    return a + b"
run_tests(code=code, test_list=["assert add(2, 3) == 5"], test_imports=[])
```
<end_code>

(After observing PASS)
Thought: Tests pass, I submit.
```python
final_answer(code="def add(a, b):\\n    return a + b")
```
<end_code>
"""


def build_task_message(task: MBPPTaskInput) -> str:
    """Build the user message describing the MBPP task."""
    tests = "\n".join(task.test_list)
    return (
        f"Problem: {task.task_definition}\n\n"
        f"Function signature:\n{task.function_definition}\n\n"
        f"Your solution must pass these tests:\n{tests}\n\n"
        f"Write the function and submit it with final_answer."
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

    orchestrator = Orchestrator(
        manager=manager,
        extractor=CodeExtractor,
        sandbox=sandbox,
        system_prompt=build_system_prompt(SANDBOX_MANUAL),
        stop_sequences=["<end_code>"],
        max_iterations=10,
    )
    return orchestrator.run(
        task_id=str(task.task_id),
        benchmark="mbpp",
        task_message=build_task_message(task),
    )


def run_mbpp_cli(
    task_file: str = None,
    output: str = None,
    model_name: str = None,
    provider_url: str = None,
) -> None:
    try:
        with open(task_file, "r") as f:
            file_content = f.read()

        data = json.loads(file_content)
        task_input = MBPPTaskInput.model_validate(data)

        solution_output = run_mbpp(task_input, model_name, provider_url)

        print(json.dumps(solution_output.model_dump(), indent=4))

        os.makedirs(os.path.dirname(output), exist_ok=True)
        with open(output, "w") as f:
            f.write(solution_output.model_dump_json(indent=4))
    except Exception as e:
        print(f"Error {e}")


def main() -> None:
    Fire(run_mbpp_cli)


if __name__ == "__main__":
    main()
