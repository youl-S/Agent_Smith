from srcs.models import SWEBenchTaskInput, SolutionOutput
from srcs.sandbox.sandbox import Sandbox
from json import JSONDecodeError
from fire import Fire
from srcs.llm import (
    CodeExtractor,
)
import subprocess
import json
import os

SANDBOX_MANUAL = (
    "- run_tests(code, test_list, test_imports): run candidate code "
    "against the given asserts; returns a PASS/FAIL report.\n"
    "- final_answer(code): submit the final solution code and end the task."
)


def build_system_prompt(man_sandbox):
    # return f"" sys_prompt
    pass


def build_task_message(task: SWEBenchTaskInput) -> str:
    pass

def run_swebench (
        task: SWEBenchTaskInput,
        model_name: str,
        provider_url: str,
) -> SolutionOutput:
    pass
    # var set ----> child (subprocess) pour run le docker
    os.environ["SWE_DOCKER_IMG"] = task.docker_image
    os.environ["SWE_EVAL_SCRIPT"] = task.eval_script

    sandbox = Sandbox()

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
