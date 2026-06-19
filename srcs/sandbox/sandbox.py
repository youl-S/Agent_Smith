from srcs.models import SandboxConfig
import subprocess


class Sandbox:

    def python_subprocess(self, python_code_to_test: str):

        result = subprocess.Popen(
            ["python", python_code_to_test],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
        )
        output, errors = result.communicate()
        if result.returncode != 0:
            print(f"ca compile pas frero, stderr : {errors}")
        else:
            print(f"Ca marche, stdout :{output}")

    def run(self, file_to_test: str):
        if file_to_test.endswith(".py"):
            self.python_subprocess(file_to_test)
