from srcs.models import SWEBenchTaskInput, SolutionOutput
from srcs.sandbox.sandbox import Sandbox
from json import JSONDecodeError
from dotenv import load_dotenv
from fire import Fire
from srcs.llm import (
    CodeExtractor,
    Orchestrator,
    ProviderTarget,
    LLMManager,
    LLMClient
)
import json
import os

SANDBOX_MANUAL = (
    "- execute_bash(cmd): Runs a shell command inside the repository root (/testbed).\n"
    "  Use this to apply patches, run pytest/unittest, or grep files.\n"
    "- read_file(path): Reads the contents of a file relative to the repository root.\n"
    "- run_evaluation(): Runs the official SWE-bench evaluation script to check if the repository bug is fully resolved.\n"
    "- final_answer(code): Submit the task once you verify your patch works. Here, 'code' can be the git diff patch string."
)


def build_system_prompt(man_sandbox: str = SANDBOX_MANUAL) -> str:
    return f"""You are an expert software engineer resolving enterprise codebase bugs through a Thought -> Code -> Observation loop.

# Response format
Each turn: write a brief Thought, then exactly ONE Python code block with
exactly ONE tool call ending with <end_code>.

You MUST call every tool with KEYWORD arguments only (name=value).
Never use positional arguments.
- Correct:   execute_bash(cmd="pytest")
- Incorrect: execute_bash("pytest")

The code runs in an isolated sandbox containing the codebase repository (mounted at /testbed). 
You then receive an Observation and continue.

# Sandbox manual
The following tools are available as Python functions inside your sandbox:

{man_sandbox}

# How to solve SWE-bench issues
1. Use `execute_bash` or `read_file` to inspect files and reproduce the issue described.
2. Edit files or apply a git patch/diff to fix the bug via `execute_bash`.
3. Test your modifications to ensure everything builds and passes tests.
4. Call `run_evaluation()` to guarantee the issue is officially validated as resolved.
5. Once confident, call `final_answer(...)` with a summary of your resolution.

# Example
Thought: I will search for the faulty method in the codebase.
```python
execute_bash(cmd="grep -rn 'def calculate_total' src/")"""

def build_task_message(task: SWEBenchTaskInput) -> str:
    pass

def discover_key_vars() -> list[str]:
    """Return all env var names that look like API keys (contain API_KEY)."""
    load_dotenv()
    return sorted(
        name
        for name in os.environ
        if "API_KEY" in name and os.environ.get(name)
    )

def run_swebench (
        task: SWEBenchTaskInput,
        model_name: str,
        provider_url: str,
) -> SolutionOutput:
    pass
    # var set ----> child (subprocess) pour run le docker
    os.environ["SWE_DOCKER_IMG"] = task.docker_image
    os.environ["SWE_EVAL_SCRIPT"] = task.eval_script


    target = ProviderTarget(
        name="provider",
        base_url=provider_url,
        model=model_name,
        key_env_vars=discover_key_vars()
    )
    manager = LLMManager(
        target=[target],
        client=LLMClient(timeout_s=90.0)
    )
    sandbox = Sandbox()
    sandbox._launch_server("stdio", "python mcp_tools_swebench.py")

    orchestrator = Orchestrator(
            manager=manager,
            extractor=CodeExtractor,
            sandbox=sandbox,
            system_prompt=build_system_prompt(SANDBOX_MANUAL),
            stop_sequences=["<end_code>"],
            max_iterations=30,
            max_input_tokens=300000,
            max_output_tokens=10000,
            max_time_seconds=900
    )
    return orchestrator.run(
            task_id=str(task.task_id),
            benchmark="swebench",
            task_message=build_task_message(task),
        )

def run_swebench_cli(
        task_file: str = None,
        output: str = None,
        model_name: str = None,
        provider_url: str = None,
) -> None:
    try:
        with open(task_file, "r") as f:
            content = f.read()

        data = json.loads(content)
        parse_task = SWEBenchTaskInput.model_validate(data)

        solution_output = run_swebench(parse_task, model_name=model_name, provider_url=provider_url)

        os.makedirs(os.path.dirname(output), exist_ok=True)
        with open(output, "w") as f:
            f.write(solution_output.model_dump_json(indent=4))

    except FileNotFoundError:
        print('Error file not found')
    except JSONDecodeError as e:
        print(f"[Error] {e}")
    except Exception as e:
        print(f'[Error] {e}')

def main() -> None:
    Fire(run_swebench_cli)


if __name__ == "__main__":
    main()
