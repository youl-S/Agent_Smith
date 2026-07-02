import time

from srcs.models import StepMetrics, SolutionOutput
from srcs.llm.manager import LLMManager
from srcs.llm.code_extractor import CodeExtractor

"""
class SandboxResult:
    observation: str
    is_final: bool = False
    final_answer: str | None = None
"""


class Orchestrator:
    """The agent loop. Benchmark-agnostic.

    All limits are parameters so MBPP and SWE can pass their own values
    (MBPP: 6000/1500/120, SWE: 300000/10000/900).
    """

    def __init__(
        self,
        manager: LLMManager,
        extractor: type[CodeExtractor],
        sandbox: object,
        system_prompt: str,
        stop_sequences: list[str] | None = None,
        max_iterations: int = 10,
        max_input_tokens: int = 6000,
        max_output_tokens: int = 1500,
        max_time_seconds: float = 120.0,
        safety_margin: float = 0.9,
    ) -> None:
        self._manager: LLMManager = manager
        self._extractor: type[CodeExtractor] = extractor
        self._sandbox: object = sandbox
        self._system_prompt: str = system_prompt
        self._stop: list[str] = stop_sequences or ["<end_code>"]
        self._max_iter: int = max_iterations
        self._max_input: int = max_input_tokens
        self._max_output: int = max_output_tokens
        self._max_time: float = max_time_seconds
        self._margin: float = safety_margin

    def run(
        self,
        task_id: str,
        benchmark: str,
        task_message: str,
        input_prediction_factor: float = 1.4,
    ) -> SolutionOutput:
        start: float = time.perf_counter()

        messages: list[dict[str, str]] = [
            {"role": "system", "content": self._system_prompt},
            {"role": "user", "content": task_message},
        ]

        steps: list[StepMetrics] = []
        solution: str = ""
        success: bool = False
        error: str | None = None
        total_input: int = 0
        total_output: int = 0

        for i in range(1, self._max_iter + 1):
            elapsed = time.perf_counter() - start
            if elapsed >= self._max_time * self._margin:
                error = f"time limit ({self._max_time}s) reached"
                break
            if steps:
                if (
                    round(
                        total_input
                        + (steps[-1].input_tokens * input_prediction_factor)
                    )
                    >= self._max_input
                ):
                    error = f"input token limit ({self._max_input}) reached"
                    break
            if steps:
                if (
                    round(
                        total_output
                        + (steps[-1].output_tokens * input_prediction_factor)
                    )
                    >= self._max_output
                ):
                    error = f"output token limit ({self._max_output}) reached"
                    break

            llm = self._manager.generate(messages, stop_sequences=self._stop)
            if not llm.success:
                error = f"LLM failed: {llm.error}"
                break

            total_input += llm.input_tokens
            total_output += llm.output_tokens

            block = self._extractor.extract(llm.text)
            code: str | None = block.code_extracted

            observation: str
            sandbox_input: str
            if not code:
                observation = (
                    "No code block found. Respond with exactly one "
                    "```python ... ``` block ending with <end_code>."
                )
                sandbox_input = ""
            else:
                sandbox_input = code
                result = self._sandbox.run(code)

                if result["type"] == "final_answer":
                    solution = result["answer"]
                    observation = (
                        result.get("stdout", "") or "final_answer received"
                    )
                    success = True
                else:
                    parts = [
                        result.get("stdout", ""),
                        result.get("traceback", ""),
                    ]
                    observation = (
                        "\n".join(p for p in parts if p).strip() or ""
                    )

            steps.append(
                StepMetrics(
                    step=i,
                    input_tokens=llm.input_tokens,
                    output_tokens=llm.output_tokens,
                    request_time_ms=llm.request_time_ms,
                    api_url=llm.api_url,
                    model_name=llm.model_name,
                    llm_output=llm.text,
                    sandbox_input=sandbox_input,
                    sandbox_output=observation,
                    retries=llm.retries,
                )
            )

            if success:
                break

            messages.append({"role": "assistant", "content": llm.text})
            messages.append(
                {"role": "user", "content": f"Observation:\n{observation}"}
            )

        total_time: float = time.perf_counter() - start
        return SolutionOutput(
            task_id=task_id,
            benchmark=benchmark,
            success=success,
            solution=solution,
            system_prompt=self._system_prompt,
            iterations=len(steps),
            total_requests=sum(s.retries + 1 for s in steps),
            total_input_tokens=sum(s.input_tokens for s in steps),
            total_output_tokens=sum(s.output_tokens for s in steps),
            total_time_seconds=total_time,
            steps=steps,
            error=error,
        )
