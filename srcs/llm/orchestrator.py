import time

from ..models import StepMetrics, SolutionOutput
from .manager import LLMManager
from .code_extractor import CodeExtractor


class Orchestrator:
    """The agent loop. Benchmark-agnostic."""

    def __init__(
        self,
        manager: LLMManager,
        extractor: type[CodeExtractor],
        sandbox: object,
        system_prompt: str,
        stop_sequences: list[str] | None = None,
        max_iterations: int = 10,
    ) -> None:
        self._manager: LLMManager = manager
        self._extractor: type[CodeExtractor] = extractor
        self._sandbox: object = sandbox
        self._system_prompt: str = system_prompt
        self._stop: list[str] = stop_sequences or ["<end_code>"]
        self._max_iter: int = max_iterations

    def run(
        self,
        task_id: str,
        benchmark: str,
        task_message: str,
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

        for i in range(1, self._max_iter + 1):
            llm = self._manager.generate(messages, stop_sequences=self._stop)
            if not llm.success:
                error = f"LLM failed: {llm.error}"
                break

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
                result = self._sandbox.execute(code)  # type: ignore[attr-defined]
                observation = result.observation
                if result.is_final:
                    solution = result.final_answer or ""
                    success = True

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
