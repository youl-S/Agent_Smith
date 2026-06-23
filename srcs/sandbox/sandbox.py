from srcs.models import SandboxConfig
from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client
from mcp.client.streamable_http import streamablehttp_client
import multiprocessing
import builtins
import asyncio


class Sandbox:
    def __init__(self):
        self._config = SandboxConfig()
        self._mcp_stdio: str = None
        self._mcp_server: str = None

    async def _stdio_client(self):
        parameters  = StdioServerParameters(command="python", args=["./srcs/sandbox/mbpp_test.py"])
        async with stdio_client(parameters) as (read,write):
            async with ClientSession(read, write) as session:
                await session.initialize()
                tools = await session.list_tools()
                result = await session.call_tool("add", {"a": 3, "b":4})
                print(f"read\n{read}\n")
                print(f"write\n{write}\n")
                print(f"result\n{result}\n")

    async def _http_client(self):
        async with streamablehttp_client("http://localhost:8080/mcp") as (read, write, _):
            async with ClientSession(read,write) as session:
                await session.initialize()
                tools = await session.list_tools()
                result = await session.call_tool("add", {"a": 3, "b":4})
                print(result.content)




    def _subprocess(self, code_to_test: str):
        def safe_import(name, *args, **kwargs):
            if name not in self._config.authorized_imports:
                raise ImportError(f"Import {name} not allowed")
            return __import__(name, *args, **kwargs)

        namespace = {
            "__builtins__": builtins,  # a voir ce quon restreint
            "__import__": safe_import,
        }
        exec(code_to_test, namespace)

    def run(self, code_to_test: str, time_out_seconds: int):
        asyncio.run(self._http_client())
        process = multiprocessing.Process(
            target=self._subprocess, args=(code_to_test,)
        )
        result = "suceed"
        try:
            process.start()
            process.join(timeout=time_out_seconds)
            if process.is_alive():
                process.kill()
                raise TimeoutError(
                    f"runtime exceed {time_out_seconds} seconds"
                )
        except (
            TimeoutError,
            ImportError,
        ) as e:
            result = e
        except Exception as e:
            result = f"An error occured details :{e}"
        print(result)

    def cli(
        self,
        _config_file: str = None,
        _mcp_stdio: str = None,
        _mcp_server: str = None,
    ):
        if _config_file:
            # changer la _config
            pass
        if _mcp_stdio and _mcp_server:
            raise ValueError(
                "--mcp-stdio and --mcp-server are mutually exclusive"
            )
        code_to_test = input("Write code to test: ")
        self.run(code_to_test, 10)
