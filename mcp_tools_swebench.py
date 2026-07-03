from mcp.server.fastmcp import FastMCP
import subprocess
import sys
import os
import re
import base64

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
        """Start the Docker container if not already running.

        Launches a detached container from the task image that sleeps
        forever, so commands can be run with `docker exec`. Raises
        RuntimeError if the container cannot be started.
        """
        if self.id_container:
            return

        try:
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
        except subprocess.CalledProcessError as e:
            raise RuntimeError(f"docker run failed: {e.stderr.strip()}") from e
        except FileNotFoundError as e:
            raise RuntimeError("docker not found on PATH") from e

        self.id_container = run_docker.stdout.strip()

    def exec(
        self,
        cmd_exec: str,
        work_dir: str = TESTBED,
        timeout: int = 300,
    ):
        """Execute a command inside the managed Docker container.

        Args:
            cmd_exec: Command string to run inside the container.
            work_dir: Working directory inside the container.
            timeout: Optional timeout in seconds for the command.

        Returns:
            The completed subprocess result or a mock timeout object.
        """
        self.start_container()

        assert self.id_container is not None and self.id_container

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
            exec_bash,
            capture_output=True,
            text=True,
            timeout=timeout,
        )
        return container_exec

    def clean_container(self) -> None:
        """Remove the managed Docker container if one exists.

        The container is removed forcefully to ensure the sandbox is cleaned
        up even if the container is still running.
        """
        if self.id_container:
            subprocess.run(["docker", "rm", "-f", self.id_container])


def container_sandbox() -> DockerExec | str:
    """Return the shared sandbox, or a FAIL message if config is missing."""
    global execute_container
    if execute_container is not None:
        return execute_container
    try:
        task_image, evaluation_script = load_config()
    except ValueError as e:
        return f"FAIL sandbox init: {e}"
    execute_container = DockerExec(task_image, evaluation_script)
    return execute_container


@mcp.tool()
def read_file(filepath: str, start_line: int = 1, end_line: int = -1):
    """Read a file from the sandbox container and return requested lines.

    Args:
        filepath: Path to the file inside the sandbox container.
        start_line: First line number to include, 1-based.
        end_line: Last line number to include, or -1 for all lines.

    Returns:
        Numbered file contents (like `cat -n`) or a FAIL message.
    """
    get_container = container_sandbox()
    if isinstance(get_container, str):
        return get_container

    try:
        res = get_container.exec(f"cat {filepath}")
    except subprocess.TimeoutExpired:
        return f"FAIL reading {filepath}: timed out"
    except Exception as e:
        return f"FAIL reading {filepath}: {type(e).__name__}: {e}"

    if res.returncode != 0:
        return f"FAIL {res.stderr.strip()}"

    all_lines = res.stdout.splitlines()
    total = len(all_lines)

    start_idx = max(0, start_line - 1)
    end_idx = total if end_line == -1 else min(end_line, total)

    selected = all_lines[start_idx:end_idx]
    if not selected:
        return f"FAIL no lines in range {start_line}-{end_line} ({filepath})"

    return "\n".join(
        f"{n}: {line}" for n, line in enumerate(selected, start=start_line)
    )


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

    if isinstance(get_container, str):
        return get_container

    try:
        res = get_container.exec(f"cat {filepath}")
        if res.returncode != 0:
            return f"FAIL {res.stderr.strip()}"

    except Exception as e:
        return f"FAIL reading {filepath}: {type(e).__name__}: {e}"

    content = res.stdout

    if old_str not in content:
        return f"FAIL {old_str} not found in {filepath}"
    content = content.replace(old_str, new_str, 1)

    encoded = base64.b64encode(content.encode()).decode()
    try:
        res = get_container.exec(f"echo '{encoded}' | base64 -d > {filepath}")
        if res.returncode != 0:
            return f"FAIL writing {filepath}: {res.stderr.strip()}"

    except Exception as e:
        return f"FAIL writing {filepath}: {type(e).__name__}: {e}"

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

    if isinstance(get_container, str):
        return get_container

    try:
        res = get_container.exec(
            f"find '{directory}' -type f -name '{pattern}'"
        )
        if res.returncode != 0:
            return f"FAIL {res.stderr.strip()}"
    except Exception as e:
        return f"FAIL listing {directory}: {type(e).__name__}: {e}"

    result = res.stdout

    if not result.strip():
        return f"FAIL in {directory}: no files with the pattern {pattern}"
    return result


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

    if isinstance(get_container, str):
        return get_container

    try:
        res = get_container.exec(
            f"grep -rn --include='{file_pattern}' -- '{pattern}' {TESTBED}"
        )

        if res.returncode == 1:
            ERROR_MSG = f"FAIL no matches found for pattern '{pattern}'"
            ERROR_MSG += f"(file_pattern='{file_pattern}') in {TESTBED}"
            return ERROR_MSG

        if res.returncode != 0:
            return f"FAIL {res.stderr.strip()}"
    except Exception as e:
        return f"FAIL searching '{pattern}': {type(e).__name__}: {e}"

    search_code = res.stdout.strip()
    return search_code


@mcp.tool()
def search_function_or_class_definition_in_code(name: str):
    """Search Python files for a function or class definition by name.

    Returns the first matching line with file path and line number.
    """
    get_container = container_sandbox()

    if isinstance(get_container, str):
        return get_container

    escaped_name = re.escape(name)
    grep_pattern = rf"^[[:space:]]*(def|class)[[:space:]]+{escaped_name}\b"

    try:
        res = get_container.exec(
            f"grep -rnE --include='*.py' -- '{grep_pattern}' {TESTBED}"
        )

        if res.returncode == 1:
            return f"FAIL no functions or class name {name}"

        if res.returncode != 0:
            return f"FAIL {res.stderr.strip()}"
    except Exception as e:
        return f"FAIL searching definition '{name}': {type(e).__name__}: {e}"

    lines = res.stdout.strip().splitlines()
    if not lines:
        return f"FAIL no definition found for {name}"

    first_match = lines[0]
    return first_match


@mcp.tool()
def find_references(name: str, filepath: str, line: str):
    """Find all usages of a symbol (function or class).

    Args:
        name: The symbol name to find references for.
        filepath: Path of the file where the symbol appears.
        line: Line number where the symbol appears (as a string).

    Returns:
        Matching lines with file paths and line numbers (same format as
        search_code), or a FAIL message if none are found.
    """
    get_container = container_sandbox()
    if isinstance(get_container, str):
        return get_container

    escaped_name = re.escape(name)
    grep_pattern = rf"\b{escaped_name}\b"

    try:
        res = get_container.exec(
            f"grep -rnE --include='*.py' -- '{grep_pattern}' {TESTBED}"
        )

        if res.returncode == 1:
            return f"FAIL no references found for {name}"

        if res.returncode != 0:
            return f"FAIL {res.stderr.strip()}"
    except Exception as e:
        return f"FAIL finding references '{name}': {type(e).__name__}: {e}"

    references = res.stdout.strip()

    MAX_CHARS = 10000
    if len(references) > MAX_CHARS:
        references = references[:MAX_CHARS] + "\n[truncated]"
    return references


@mcp.tool()
def run_tests():
    """Run the evaluation test suite and return its raw output.

    No arguments. Read the output to see which tests pass or fail, then
    keep editing until they pass. A non-zero exit code is normal when tests
    fail; output is returned either way. Long output is truncated.
    """
    get_container = container_sandbox()
    if isinstance(get_container, str):
        return get_container

    try:
        _, eval_script = load_config()
    except ValueError as e:
        return f"FAIL loading config: {e}"

    try:
        res = get_container.exec(f"bash {eval_script}", timeout=900)
    except subprocess.TimeoutExpired:
        return "FAIL tests timed out after 900s"
    except Exception as e:
        return f"FAIL could not run tests: {type(e).__name__}: {e}"
    output = []
    if res.stdout:
        output.append(res.stdout.strip())
    if res.stderr:
        output.append(res.stderr.strip())
    run_output = "\n.\n".join(output) if output else "(no test output)"

    MAX_CHARS = 15000
    if len(run_output) > MAX_CHARS:
        run_output = "[output truncated]\n" + run_output[-MAX_CHARS:]
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

    if isinstance(get_container, str):
        return get_container

    try:
        res = get_container.exec("git -c core.fileMode=false diff")
        if res.returncode != 0:
            return f"FAIL {res.stderr.strip()}"
    except Exception as e:
        return f"FAIL getting patch: {type(e).__name__}: {e}"

    patch = res.stdout.strip()
    if not patch:
        return "FAIL No modifications in the git repository."
    return patch


@mcp.tool()
def run_command(command: str, workdir: str = TESTBED):
    """Execute a shell command inside the sandbox container.

    Args:
        command: Command string to execute.
        workdir: Working directory path inside the sandbox container.

    Returns:
        A text report with stdout, stderr and the exit code, or a FAIL
        string if the command could not be run.
    """
    get_container = container_sandbox()
    if isinstance(get_container, str):
        return get_container

    try:
        res = get_container.exec(command, workdir)
    except subprocess.TimeoutExpired:
        return "FAIL command timed out"
    except Exception as e:
        return f"FAIL running command: {type(e).__name__}: {e}"

    return (
        f"exit_code: {res.returncode}\n"
        f"stdout:\n{res.stdout.strip()}\n"
        f"stderr:\n{res.stderr.strip()}"
    )


def main():
    if "--http" in sys.argv:
        mcp.run(transport="streamable-http")
    else:
        mcp.run(transport="stdio")


if __name__ == "__main__":
    main()
