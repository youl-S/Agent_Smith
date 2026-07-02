from mcp.server.fastmcp import FastMCP
import subprocess
import os
import re

mcp = FastMCP("swebench-tools")
execute_container = None  # global mem (MCPToolSwe(id...))
TESTBED = "/testbed"  # code patch


# child (mcpswetoo) parent(agent-swe)
def load_config() -> tuple[str, str]:
    task_image = os.getenv("SWE_DOCKER_IMG")  # from agent set environ()
    if not task_image:
        raise ValueError("Error missing image docker")

    eval_script = os.getenv("SWE_EVAL_SCRIPT")
    if not eval_script:
        raise ValueError("Error missing script to evaluate")

    print(task_image, eval_script)
    return task_image, eval_script


class DockerExec:
    def __init__(self, task_image, eval_script) -> None:
        self.task_image = task_image
        self.eval_script = eval_script
        self.id_container: str | None = None  # remplir

    def start_container(self) -> None:
        if self.id_container:
            return  # pas de start si on a deja pull (Django..)
        # aucun reseau d arriere plan (None)

        run_docker = subprocess.run(
            [
                "docker",
                "run",
                "--network",
                "none",
                "-d",
                self.task_image,
                "sleep",
                "infinity",
            ],
            capture_output=True,  # catch
            text=True,
            check=True,
        )  # print

        if run_docker.returncode != 0:
            print("error")

        self.id_container = run_docker.stdout.strip("\n")

        # print(self.id_container)

    def exec(self, cmd_exec: str, work_dir: str = TESTBED):
        # for exec cmd tool
        self.start_container()  # si un container est present
        assert self.id_container is not None

        if not self.id_container:
            raise ValueError("Cannot find id_container")
        exec_bash = [
            "docker",
            "exec",
            "-w",
            work_dir,
            self.id_container,
            "bash",
            "-c",
            cmd_exec,
        ]
        container_exec = subprocess.run(
            exec_bash, capture_output=True, text=True
        )
        return container_exec

    def clean_container(self) -> None:
        if self.id_container:
            subprocess.run(["docker", "rm", "-f", self.id_container])


# read ... (exec avec docker chaques cmd dans un container)


# for execute into container
def container_sandbox():
    global execute_container
    try:
        if execute_container is None:
            task_image, evaluation_script = load_config()
            print(load_config)
            execute_container = DockerExec(task_image, evaluation_script)
            print(execute_container)
    except ValueError as e:
        print(e)
    return execute_container


@mcp.tool()
def read_file(filepath: str, start_line: int = 1, end_line: int = -1):
    execution_container = container_sandbox()
    if execution_container is None:
        return "FAIL init sandbox docker"

    cmd = execution_container.exec(f"cat {filepath}")
    if cmd.returncode != 0:
        return f"FAIL {cmd.stderr.strip()}"

    get_line = cmd.stdout.splitlines()
    lines_total = len(get_line)

    start_idx = max(0, start_line - 1)
    if end_line == -1:
        end_idx = lines_total
    else:
        end_idx = min(end_line, lines_total)

    format_output = []
    for numbers, lines in enumerate(
        get_line[start_idx:end_idx], start=start_line
    ):
        format_output.append(f"{numbers}: {lines}")
    if not format_output:
        return "FAIL File is empty"
    return "\n".join(format_output)


@mcp.tool()
def edit_file(filepath: str, old_str: str, new_str: str):
    execution_container = container_sandbox()
    if execution_container is None:
        return "FAIL init sandbox docker"

    cmd = execution_container.exec(f"cat {filepath}")
    if cmd.returncode != 0:
        return f"FAIL {cmd.stderr.strip()}"

    content = cmd.stdout.strip()

    if old_str not in content:
        return f"FAIL {old_str} not found in {filepath}"
    content = content.replace(old_str, new_str, 1)

    cmd = execution_container.exec(
        f"cat > {filepath} << 'EOF'\n{content}\nEOF"
    )
    if cmd.returncode != 0:
        return f"FAIL {cmd.stderr.strip()}"
    return "PASS"


@mcp.tool()
def list_files(directory: str, pattern: str = "*"):
    execution_container = container_sandbox()
    if execution_container is None:
        return "FAIL init sandbox docker"

    cmd = execution_container.exec(
        f"find '{directory}' -type f -name '{pattern}'"
    )
    if cmd.returncode != 0:
        return f"FAIL {cmd.stderr.strip()}"
    return cmd.stdout.strip()


@mcp.tool()
def search_code(pattern: str, file_pattern: str = "*"):
    execution_container = container_sandbox()
    if execution_container is None:
        return "FAIL init sandbox docker"

    cmd = execution_container.exec(
        f"grep -rn --include='{file_pattern}' -- '{pattern}' {TESTBED}"
    )

    if cmd.returncode == 1:
        return f"FAIL no matches found for pattern '{pattern}' (file_pattern='{file_pattern}') in {TESTBED}"

    if cmd.returncode != 0:
        return f"FAIL {cmd.stderr.strip()}"

    return cmd.stdout.strip()


@mcp.tool()
def search_function_or_class_definition_in_code(name: str):
    execution_container = container_sandbox()
    if execution_container is None:
        return "FAIL init sandbox docker"

    escaped_name = re.escape(name)
    grep_pattern = rf"^[[:space:]]*(def|class)[[:space:]]+{escaped_name}\b"

    cmd = execution_container.exec(
        f"grep -rnE --include='*.py' -- '{grep_pattern}' {TESTBED}"
    )

    if cmd.returncode == 1:
        return f"FAIL no functions or class name {name}"

    if cmd.returncode != 0:
        return f"FAIL {cmd.stderr.strip()}"

    first_match = cmd.stdout.strip().splitlines()[0]
    return first_match


@mcp.tool()
def find_references(name: str, filepath: str, line: str):
    pass


@mcp.tool()
def run_tests():
    pass


@mcp.tool()
def get_patch():
    pass


@mcp.tool()
def run_command(command: str, workdir: str = TESTBED):
    execution_container = container_sandbox()
    if execution_container is None:
        return "FAIL init sandbox docker"

    cmd = execution_container.exec(command, workdir)
    result = {
        "stdout": cmd.stdout.strip(),
        "stderr": cmd.stderr.strip(),
        "exit code": cmd.returncode,
    }
    return result


# git -c core.fileMode=false dif

if __name__ == "__main__":
    os.environ["SWE_DOCKER_IMG"] = (
        "swebench/sweb.eval.x86_64.sympy_1776_sympy-18189:latest"
    )
    os.environ["SWE_EVAL_SCRIPT"] = "/testbed/eval.sh"
    # try:
    exec_test = container_sandbox()
    tool_read = read_file("/testbed/sympy/__init__.py", 0, 10)
    print(tool_read)
    # testeur = DockerExec(test_img, eval_script="/testbed/eval.sh")
    # testeur.start_container()
    # show_img_on = subprocess.run(["docker", "images"],
    #                              capture_output=True, text=True)
    # print(show_img_on.stdout)
    # print()
    # print('exec create dir')
    # testeur.exec("mkdir theo")
    # ls = testeur.exec("ls -la")
    # print(ls.stdout)
    # print('')
    if exec_test is not None:
        print("clean container")
        exec_test.clean_container()
        print("clean Ok")
    # except subprocess.CalledProcessError as e:
    #     print(f"error {e.stderr}")
