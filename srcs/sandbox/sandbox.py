from srcs.models import SandboxConfig
from srcs.sandbox.mcp_client import McpClient
from pathlib import Path
from typing import Any, Callable
import multiprocessing
import builtins
import queue
import ast
import io
import sys
import traceback
import time
import resource
import socket


class FinalAnswer(BaseException):
    """Control-flow signal raised when the executed code calls final_answer().

    Inherits from BaseException (not Exception) so that a generic
    `except Exception` in the LLM-generated code cannot swallow it: the
    final answer must always propagate up to the sandbox handler, the same
    way KeyboardInterrupt and SystemExit are designed to bypass `except
    Exception`.

    """


class Sandbox:
    """Restricted Python execution environment backed by a subprocess."""

    def __init__(self) -> None:
        """Initialise the sandbox config and the MCP client wrapper."""
        self._config = SandboxConfig()
        self.mcp_client = McpClient()

    def _subprocess(
        self,
        code_to_test: str,
        q_call: "multiprocessing.Queue[Any]",
        q_answer: "multiprocessing.Queue[Any]",
        q_result: "multiprocessing.Queue[Any]",
    ) -> None:
        """Run untrusted code in the child process under restrictions.

        Executed inside a ``multiprocessing.Process``: captures
        stdout/stderr, enforces a memory limit, rejects dunder access,
        installs an import/open allowlist, disables the network and
        exposes the MCP tools as stub functions. The outcome (success,
        ``final_answer`` or error) is pushed onto ``q_result``; tool
        calls round-trip through ``q_call``/``q_answer``.
        """

        def make_stub(
            tool_name: str,
            q_call: "multiprocessing.Queue[Any]",
            q_answer: "multiprocessing.Queue[Any]",
        ) -> Callable[..., Any]:
            """Build a proxy that forwards a tool call to the parent."""

            def stub(**kwargs: Any) -> Any:
                q_call.put({"tool": tool_name, "args": kwargs})
                result = q_answer.get()
                result_str = result.content[0].text
                if result_str.startswith("FAIL"):
                    print(result_str)
                    # raise RuntimeError(result_str)
                return result_str

            return stub

        def safe_open(file: Any, *args: Any, **kwargs: Any) -> Any:
            """open() replacement restricted to the allowed directories."""
            if isinstance(file, int):
                raise PermissionError("fd not allowed")
            target = Path(file).resolve()
            if not any(
                target.is_relative_to(allowed) for allowed in allowed_paths
            ):
                raise PermissionError(f"{file} outside authorized paths")

            return real_open(file, *args, **kwargs)

        def safe_import(name: str, *args: Any, **kwargs: Any) -> Any:
            """__import__ replacement enforcing the import allowlist."""
            if name not in self._config.authorized_imports:
                raise ImportError(f"Import {name} not allowed")
            return builtins.__import__(name, *args, **kwargs)

        def final_answer(code: str) -> None:
            """Stop execution and submit ``code`` as the final answer."""
            if not code:
                raise ValueError("Not any code provided in final answer")
            else:
                raise FinalAnswer(code)

        def block_net(*args: Any, **kwargs: Any) -> Any:
            """Reject any attempt to create a network socket."""
            raise PermissionError("Network disabled")

        try:
            stdout_capture = io.StringIO()
            stderr_capture = io.StringIO()
            sys.stdout = stdout_capture
            sys.stderr = stderr_capture
            resource.setrlimit(
                resource.RLIMIT_AS,
                (
                    self._config.max_memory_mb * 1024 * 1024 - 160,
                    self._config.max_memory_mb * 1024 * 1024,
                ),
            )
            tree = ast.parse(code_to_test)
            for node in ast.walk(tree):
                if isinstance(node, ast.Attribute):
                    if node.attr.startswith("__") and node.attr.endswith("__"):
                        raise ValueError(
                            f"dunder access not allowed {node.attr}"
                        )
            real_open = builtins.open
            allowed_paths = [
                Path(path).resolve()
                for path in self._config.allowed_directories
            ]
            custom_builtins = dict(vars(builtins))
            custom_builtins["__import__"] = safe_import
            custom_builtins["open"] = safe_open
            for dangerous in [
                "eval",
                "exec",
                "compile",
                "input",
                "breakpoint",
                "globals",
                "locals",
                "vars",
                "getattr",
                "setattr",
                "delattr",
                "exit",
                "quit",
            ]:
                custom_builtins.pop(dangerous, None)
            namespace = {
                "__builtins__": custom_builtins,
                "final_answer": final_answer,
            }
            for tool in self.mcp_client.list_tools().tools:
                namespace[tool.name] = make_stub(tool.name, q_call, q_answer)
            socket.socket = block_net  # type: ignore[assignment, misc]
            exec(code_to_test, namespace)
            q_result.put(
                {
                    "type": "execution succeed",
                    "stdout": stdout_capture.getvalue(),
                    "stderr": stderr_capture.getvalue(),
                }
            )
        except (KeyboardInterrupt, SystemExit):
            raise

        except FinalAnswer as answer:
            q_result.put(
                {
                    "type": "final_answer",
                    "answer": answer.args[0],
                }
            )
        except Exception:
            q_result.put(
                {
                    "type": "execution failed",
                    "traceback": traceback.format_exc(),
                    "stdout": stdout_capture.getvalue(),
                    "stderr": stderr_capture.getvalue(),
                }
            )

    def _launch_server(self, protocol: str, args: str) -> None:
        """Connect the MCP client using the chosen transport.

        ``protocol`` is ``"http"`` or ``"stdio"``; ``args`` is the URL for
        HTTP, or a ``"<command> <script_path>"`` pair for stdio.
        """
        if protocol == "http":
            self.mcp_client.http_client(args)
        else:
            try:
                command, arg = args.split()
            except ValueError:
                raise ValueError(
                    "Too many arguments\n Usage: "
                    'uv run sandbox --mcp-stdio "<command> <script_path>"'
                )
            self.mcp_client.stdio_client(command, arg)

    def run(
        self,
        code_to_test: str,
    ) -> Any:
        """Execute ``code_to_test`` in a child process; return its result.

        Spawns the subprocess, services MCP tool calls while it runs and
        enforces the wall-clock timeout (killing the process on overrun).
        Returns the timeout message on overrun, otherwise the payload
        pushed by the subprocess.
        """
        q_call: "multiprocessing.Queue[Any]" = multiprocessing.Queue()
        q_answer: "multiprocessing.Queue[Any]" = multiprocessing.Queue()
        q_result: "multiprocessing.Queue[Any]" = multiprocessing.Queue()
        process = multiprocessing.Process(
            target=self._subprocess,
            args=(code_to_test, q_call, q_answer, q_result),
        )
        start_time = time.monotonic()
        process.start()
        kill = False
        while process.is_alive():
            elapsed_time = time.monotonic() - start_time
            if elapsed_time >= self._config.max_execution_time_seconds:
                output = {
                    "type": "error",
                    "traceback": "Timeout after {elapsed_time} seconds, "
                    "execution stopped",
                }

                process.kill()
                kill = True
                break
            try:
                request = q_call.get(timeout=0.1)
            except queue.Empty:
                continue
            tool_result = self.mcp_client.call_tool(
                request["tool"], request["args"]
            )
            q_answer.put(tool_result)
        process.join()
        if not kill:
            output = q_result.get()
        return output

    def cli(
        self,
        config_file: str | None = None,
        mcp_stdio: str | None = None,
        mcp_server: str | None = None,
    ) -> None:
        """Interactive CLI entry point driven by Fire.

        Optionally loads a JSON config, selects the MCP transport
        (prompting when neither flag is given), reads the code from stdin,
        connects the server, prints the manual and runs the code.
        ``--mcp-stdio`` and ``--mcp-server`` are mutually exclusive.
        """
        if config_file:
            self._config = SandboxConfig.model_validate_json(
                Path(config_file).read_text()
            )

        if mcp_stdio and mcp_server:
            raise ValueError(
                "--mcp-stdio and --mcp-server are mutually exclusive"
            )
        print("Agent Smith Sandbox\n")
        if not mcp_stdio and not mcp_server:
            answer = str()
            while answer not in ["http", "stdio"]:
                answer = input("Select MCP transport ['http', 'stdio']: ")
            if answer == "http":
                mcp_server = input("MCP server URL: ")
            elif answer == "stdio":
                mcp_stdio = input(
                    "Command and Path to launch the MCP server script: "
                )
        print("Write or paste the code to evaluate, then press Ctrl-D:")
        code_to_test = sys.stdin.read()
        if mcp_stdio:
            self._launch_server("stdio", mcp_stdio)
        elif mcp_server:
            self._launch_server("http", mcp_server)
        self.run(code_to_test)

    def get_man(self) -> str:
        """Render the sandbox manual with config and MCP metadata."""
        template = """\
Isolated Python subprocess, fresh namespace each step (nothing persists).
Only stdout is returned — print() what you need, or the value is lost.

## final_answer(answer)
Always available (not an MCP tool); stops execution and submits. Never catch
it with a bare `except`.
- MBPP: final_answer(solution_code_str)
- SWE-bench: final_answer(get_patch())

## MCP tools
Plain Python functions — call and print, e.g. print(search_code("x", "*.py")).
They run outside the sandbox, so the limits below don't apply to them.

## Restrictions
- NameError builtins: eval, exec, compile, input, breakpoint, globals,
  locals, vars, getattr, setattr, delattr, exit, quit.
- open(): allowed dirs only, no file descriptors → PermissionError.
- import: allowlist only → ImportError.
- Dunder access (__class__, __globals__, …) → ValueError.
- Network disabled (socket/HTTP/DNS → error).

## Config
- Imports: {{AUTHORIZED_IMPORTS}}
- Directories: {{ALLOWED_DIRECTORIES}}
- Memory: {{MAX_MEMORY_MB}} MB / Time: {{MAX_EXECUTION_TIME}} s per block
  (exceed → process killed)

## MCP server
- Tools: {{TOOLS}}
- Prompts: {{PROMPTS}}
- Resources: {{RESOURCES}}
"""

        prompts = self.mcp_client.list_prompts()
        resources = self.mcp_client.list_resources()
        template = template.replace(
            "{{AUTHORIZED_IMPORTS}}",
            ", ".join(self._config.authorized_imports),
        )
        template = template.replace(
            "{{ALLOWED_DIRECTORIES}}",
            ", ".join(self._config.allowed_directories),
        )
        template = template.replace(
            "{{MAX_MEMORY_MB}}", str(self._config.max_memory_mb)
        )
        template = template.replace(
            "{{MAX_EXECUTION_TIME}}",
            str(self._config.max_execution_time_seconds),
        )
        template = template.replace(
            "{{TOOLS}}", str(self.mcp_client.list_tools().tools)
        )
        template = template.replace("{{PROMPTS}}", str(prompts))
        template = template.replace("{{RESOURCES}}", str(resources))
        print(template)
        return template
