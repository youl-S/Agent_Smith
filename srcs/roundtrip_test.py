from models import SolutionOutput


def test_solution_output_roundtrip():
    data = {
        "task_id": "django__django-11115",
        "benchmark": "swebench",
        "success": True,
        "solution": (
            "--- a/django/core/files/base.py\n+++ b/django/core/files/base.py"
            "\n@@ -1 +1 @@\n"
        ),
        "iterations": 3,
        "total_requests": 4,
        "total_input_tokens": 12500,
        "total_output_tokens": 850,
        "total_time_seconds": 32.5,
        "steps": [],
        "system_prompt": (
            "You are an autonomous AI agent tasked with solving "
            "SWE-bench issues."
        ),
        "error": None,
        "timestamp": "2026-06-19T14:44:01.123456",
    }

    solution = SolutionOutput.model_validate(data)

    roundtrip = solution.model_dump()

    assert data == roundtrip
