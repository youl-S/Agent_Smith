from srcs.models import SWEBenchTaskInput, SolutionOutput
from fire import Fire
import subprocess

from srcs.llm import (
    CodeExtractor,
)

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

def run_swebench_cli() -> None:
    pass

def main() -> None:
    Fire(run_mbpp_cli)

if __name__ == "__main__":
    main()
