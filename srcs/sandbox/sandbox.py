from srcs.models import SandboxConfig
import multiprocessing
import builtins


class Sandbox:
    def __init__(self):
        config = SandboxConfig()
        mcp_stdio: str = None
        mcp_server: str = None

    def subprocess(self, code_to_test: str):
        def safe_import(name, *args, **kwargs):
            if name not in self.config.authorized_imports:
                raise ImportError(f"Import {name} not allowed")
            return __import__(name, *args, **kwargs)

        namespace = {
            "__builtins__": builtins,  # a voir ce quon restreint
            "__import__": safe_import,
        }
        exec(code_to_test, namespace)

    def run(self, code_to_test: str, time_out_seconds: int):
        process = multiprocessing.Process(
            target=self.subprocess, args=(code_to_test,)
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
        config_file: str = None,
        mcp_stdio: str = None,
        mcp_server: str = None,
    ):
        if config_file:
            # changer la config
            pass
        if mcp_stdio and mcp_server:
            raise ValueError(
                "--mcp-stdio and --mcp-server are mutually exclusive"
            )
        code_to_test = input("Write code to test: ")
        self.run(code_to_test, 10)
