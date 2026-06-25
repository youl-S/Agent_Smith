from srcs.models import SandboxConfig
from srcs.sandbox.mcp_client import McpClient
import multiprocessing
import builtins
import queue
import ast
from pathlib import Path
import io
import sys
import traceback
import time
import resource


class Sandbox:
    def __init__(self):
        self._config = SandboxConfig()
        self.mcp_client = McpClient()

    def _subprocess(self, code_to_test: str, q_call, q_answer, q_result):
        def make_stub(tool_name, q_call, q_answer):
            def stub(**kwargs):
                q_call.put({"tool": tool_name, "args": kwargs})
                result = q_answer.get()
                return result

            return stub

        def safe_open(file, *args, **kwargs):
            if isinstance(file, int):
                if isinstance(file, int):
                    raise PermissionError("fd not allowed")
            target = Path(file).resolve()
            if not any(
                target.is_relative_to(allowed) for allowed in allowed_paths
            ):
                raise PermissionError(f"{file} outside authorized paths")

            return real_open(file, *args, **kwargs)

        def safe_import(name, *args, **kwargs):
            if name not in self._config.authorized_imports:
                raise ImportError(f"Import {name} not allowed")
            return builtins.__import__(name, *args, **kwargs)

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
            }
            for tool in self.mcp_client.list_tools().tools:
                namespace[tool.name] = make_stub(tool.name, q_call, q_answer)

            exec(code_to_test, namespace)
            q_result.put(
                {
                    "type": "success",
                    "stdout": stdout_capture.getvalue(),
                }
            )
        except (KeyboardInterrupt, SystemExit):
            raise
        except Exception:
            q_result.put(
                {
                    "type": "error",
                    "traceback": traceback.format_exc(),
                    "stdout": stdout_capture.getvalue(),
                }
            )

    def _launch_server(self, protocol, arg, language="python"):
        if protocol == "http":
            self.mcp_client.http_client(arg)
        else:
            self.mcp_client.stdio_client(language, arg)

    def run(
        self,
        code_to_test: str,
    ):

        q_call = multiprocessing.Queue()
        q_answer = multiprocessing.Queue()
        q_result = multiprocessing.Queue()
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
                output = (
                    f"Timeout after {elapsed_time} seconds, execution stopped"
                )
                process.kill()
                kill = True
                print(output)
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
        print(f"\n\noutput:\n{output}\n")

    def cli(
        self,
        config_file: str = None,
        mcp_stdio: str = None,
        mcp_server: str = None,
    ):
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
                mcp_stdio = input("Path to the MCP server script: ")
        print("Paste the code to evaluate, then press Ctrl-D:")
        code_to_test = sys.stdin.read()
        if mcp_stdio:
            print(mcp_server)
            self._launch_server("stdio", mcp_stdio)
        elif mcp_server:
            self._launch_server("http", mcp_server)
        self.run(code_to_test)
