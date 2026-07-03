from mcp.server.fastmcp import FastMCP
import subprocess
import sys
import os
import re

mcp = FastMCP("swebench-tools")
execute_container = None
TESTBED = "/testbed"


def load_config() -> tuple[str, str]:
    """Load required environment configuration for the Docker sandbox.

    Reads SWE_DOCKER_IMG and SWE_EVAL_SCRIPT from the environment and
    returns them as a tuple. Raises ValueError when either variable is missing.
    """
    task_image = os.getenv("SWE_DOCKER_IMG")
    if not task_image:
        raise ValueError("Error missing image docker")
    eval_script = os.getenv("SWE_EVAL_SCRIPT")
    if not eval_script:
        raise ValueError("Error missing script to evaluate")

    return task_image, eval_script


class DockerExec:
    """Manage execution of commands inside a Docker sandbox container.

    This class launches a detached Docker container from the configured task
    image and provides a simple interface for executing commands inside that
    container. It also offers cleanup of the container when no longer needed.
    """

    def __init__(self, task_image: str, eval_script: str) -> None:
        """Initialize the DockerExec manager.

        Args:
            task_image: Docker image name used to create the sandbox.
            eval_script: Path to the evaluation script inside the container.
        """
        self.task_image = task_image
        self.eval_script = eval_script
        self.id_container: str | None = None

    def start_container(self) -> None:
        """Start the Docker container if it is not already running.

        Uses the configured task image to launch a detached container
        that sleeps indefinitely, allowing subsequent
        command execution via docker exec.
        """
        if self.id_container:
            return

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
            capture_output=True,
            text=True,
            check=True,
        )

        if run_docker.returncode != 0:
            print(f"Error {run_docker.stderr.strip()}")

        self.id_container = run_docker.stdout.strip("\n")

    def exec(self, cmd_exec: str,
             work_dir: str = TESTBED,
             timeout: int | None = None):
        """Execute a command inside the managed Docker container.

        Args:
            cmd_exec: Command string to run inside the container.
            work_dir: Working directory inside the container.
            timeout: Optional timeout in seconds for the command.

        Returns:
            The completed subprocess result or a mock timeout object.
        """
        self.start_container()
        assert self.id_container is not None

        # if not self.id_container:
        #     raise ValueError("Cannot find id_container")
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
        try:
            container_exec = subprocess.run(
                exec_bash,
                capture_output=True,
                text=True,
                timeout=timeout,
            )
            return container_exec
        except subprocess.TimeoutError:

            class MokTimeOut:
                return_code_err = -1
                stdout = ""
                stderr = "time out Fail commande execution"

            return MokTimeOut()
        # ici les gars je simule une timeout Error pour que le llm le capte
        # que ca time out (run_tests)
        # pour pas faire crash le serv mcp\ et feedback au llm ce qui se passe
        # avec le log erreur pour son observation

        # courrage la correction appeler si besoin !!!!

    def clean_container(self) -> None:
        """Remove the managed Docker container if one exists.

        The container is removed forcefully to ensure the sandbox is cleaned
        up even if the container is still running.
        """
        if self.id_container:
            subprocess.run(["docker", "rm", "-f", self.id_container])


def container_sandbox():
    """Initialize and return the shared Docker sandbox instance.

    This helper creates a DockerExec object once and reuses it for subsequent
    calls. If the configuration cannot be loaded, it prints the error and
    returns None.
    """
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
    """Read a file from the sandbox container and return requested lines.

    Args:
        filepath: Path to the file inside the sandbox container.
        start_line: First line number to include, 1-based.
        end_line: Last line number to include, or -1 for all lines.

    Returns:
        Numbered file contents or an error message.
    """
    get_container = container_sandbox()
    if get_container is None:
        return "FAIL init sandbox docker"

    res = get_container.exec(f"cat {filepath}")
    if res.returncode != 0:
        return f"FAIL {res.stderr.strip()}"

    get_line = res.stdout.splitlines()
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
    """Replace the first occurrence of a string in a file inside the sandbox.

    Args:
        filepath: Path to the file inside the sandbox container.
        old_str: Text to replace.
        new_str: Replacement text.

    Returns:
        "PASS" on success, or an error string if the operation fails.
    """
    get_container = container_sandbox()
    if get_container is None:
        return "FAIL init sandbox docker"

    res = get_container.exec(f"cat {filepath}")
    if res.returncode != 0:
        return f"FAIL {res.stderr.strip()}"

    content = res.stdout.strip()

    if old_str not in content:
        return f"FAIL {old_str} not found in {filepath}"
    content = content.replace(old_str, new_str, 1)

    res = get_container.exec(f"cat > {filepath} << 'EOF'\n{content}\nEOF")
    if res.returncode != 0:
        return f"FAIL {res.stderr.strip()}"
    return "PASS"


@mcp.tool()
def list_files(directory: str, pattern: str = "*"):
    """List files under a directory matching a glob pattern.

    Args:
        directory: Directory to search.
        pattern: Filename glob pattern to match.

    Returns:
        A string with matching file paths separated by newlines, or an error.
    """
    get_container = container_sandbox()
    if get_container is None:
        return "FAIL init sandbox docker"

    res = get_container.exec(f"find '{directory}' -type f -name '{pattern}'")
    if res.returncode != 0:
        return f"FAIL {res.stderr.strip()}"

    list_files = res.stdout.strip()
    return list_files


@mcp.tool()
def search_code(pattern: str, file_pattern: str = "*"):
    """Search files in the testbed for a pattern.

    Args:
        pattern: The search string or regex to pass to grep.
        file_pattern: Glob pattern to limit which files are searched.

    Returns:
        Matching lines with file paths and line numbers, or an error message.
    """
    get_container = container_sandbox()
    if get_container is None:
        return "FAIL init sandbox docker"

    res = get_container.exec(
        f"grep -rn --include='{file_pattern}' -- '{pattern}' {TESTBED}"
    )

    if res.returncode == 1:
        ERROR_MSG = f"FAIL no matches found for pattern '{pattern}'"
        ERROR_MSG += f"(file_pattern='{file_pattern}') in {TESTBED}"
        return ERROR_MSG

    if res.returncode != 0:
        return f"FAIL {res.stderr.strip()}"

    search_code = res.stdout.strip()
    return search_code


@mcp.tool()
def search_function_or_class_definition_in_code(name: str):
    """Search Python files for a function or class definition by name.

    Returns the first matching line with file path and line number.
    """
    get_container = container_sandbox()
    if get_container is None:
        return "FAIL init sandbox docker"

    escaped_name = re.escape(name)
    grep_pattern = rf"^[[:space:]]*(def|class)[[:space:]]+{escaped_name}\b"

    res = get_container.exec(
        f"grep -rnE --include='*.py' -- '{grep_pattern}' {TESTBED}"
    )

    if res.returncode == 1:
        return f"FAIL no functions or class name {name}"

    if res.returncode != 0:
        return f"FAIL {res.stderr.strip()}"

    first_match = res.stdout.strip().splitlines()[0]
    return first_match


@mcp.tool()
def find_references(name: str, filepath: str, line: str):
    pass


@mcp.tool()
def run_tests():
    """Run the configured test script inside the sandbox container.

    Returns:
        The combined stdout/stderr output from the test execution, or an
        error string if sandbox initialization or configuration loading fails.
    """
    get_containeur = container_sandbox()
    if get_containeur is None:
        return "FAIL init sandbox docker "

    try:
        _, eval_script = load_config()
    except ValueError as e:
        return f"Error loading conf {e}"
    res = get_containeur.exec(f"bash {eval_script}", timeout=900)

    output = []
    if res.stdout:
        output.append(f"{res.stdout.strip()}")
    if res.stderr:
        output.append(f"{res.stderr.strip()}")
    run_output = "\n.\n".join(output)

    MAX_TOKEN = 15000
    if len(run_output) > MAX_TOKEN:
        run_output = "Truncate output limited" + run_output[-MAX_TOKEN:]
    return run_output


@mcp.tool()
def get_patch():
    """
    Get the current git diff patch from inside the sandbox container.

    Returns:
        The patch text if modifications exist.
        A message indicating no modifications if the repository is clean.
        An error string if sandbox initialization or git diff fails.
    """
    get_container = container_sandbox()
    if get_container is None:
        return "FAIL init sandbox docker"
    res = get_container.exec("git -c core.fileMode=false diff")
    if res.returncode != 0:
        return f"FAIL {res.stderr.strip()}"

    patch = res.stdout.strip()
    if not patch:
        return "No modifications in the git repository."
    return patch


@mcp.tool()
def run_command(command: str, workdir: str = TESTBED):
    """Execute a shell command inside the sandbox container.

    Args:
        command: Command string to execute.
        workdir: Working directory path inside the sandbox container.

    Returns:
        A dictionary containing stdout, stderr, and exit code.
    """
    execution_container = container_sandbox()
    if execution_container is None:
        return "FAIL init sandbox docker"

    res = execution_container.exec(command, workdir)
    result = {
        "stdout": res.stdout.strip(),
        "stderr": res.stderr.strip(),
        "exit code": res.returncode,
    }
    return result


def main():
    if '--http' in sys.argv:
        mcp.run(transport="streamable-http")
    else:
        mcp.run(transport="stdio")


if __name__ == "__main__":
    main()
