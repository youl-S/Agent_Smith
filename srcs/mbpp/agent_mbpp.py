import os

from dotenv import load_dotenv

from ..models import MBPPTaskInput, SolutionOutput
from sandbox.sandbox import Sandbox
from llm import (
    LLMClient,
    LLMManager,
    ProviderTarget,
    CodeExtractor,
    Orchestrator,
)

load_dotenv()


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
Each turn: write a brief Thought, then exactly ONE Python code block ending \
with <end_code>:

```python
# your code here
```
<end_code>

The code runs in a sandbox. You then receive an Observation and continue.

# Sandbox manual
The following tools are available as Python functions inside the sandbox:

{sandbox_manual}

# How to solve
1. Write the solution function.
2. Optionally call run_tests(...) to check it.
3. When confident, call final_answer(...) with the complete solution.

You may call final_answer directly if you are sure. Solve in few turns.

# Example
Thought: Simple sum, I submit directly.
```python
final_answer("def add(a, b):\\n    return a + b")
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


def main() -> None:
    """Quick end-to-end run on MBPP task 282 against the real provider."""
    task = MBPPTaskInput(
        task_id=282,
        task_definition="Write a function to subtract two lists "
        "element-wise using map and lambda.",
        function_definition="def sub_list(nums1, nums2):",
        test_imports=[],
        test_list=[
            "assert sub_list([1,2],[3,4])==[-2,-2]",
            "assert sub_list([90,120],[50,70])==[40,50]",
        ],
    )
    out = run_mbpp(
        task=task,
        model_name="llama-3.3-70b-versatile",
        provider_url="https://api.groq.com/openai/v1",
    )

    print("success    :", out.success)
    print("iterations :", out.iterations)
    print("solution   :", out.solution)
    print("requests   :", out.total_requests)
    print("in/out tok :", out.total_input_tokens, "/", out.total_output_tokens)
    print("time       :", round(out.total_time_seconds, 1), "s")
    print("error      :", out.error)
    print("\n--- per step ---")
    for s in out.steps:
        print(
            f"step {s.step}: out_tok={s.output_tokens} "
            f"obs={s.sandbox_output[:50]!r}"
        )


if __name__ == "__main__":
    main()
