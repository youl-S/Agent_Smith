from mcp.server.fastmcp import FastMCP
import subprocess
import sys
import os
import shlex
from typing import Any

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
        input_data: str | None = None,
    ) -> dict[str, Any]:
        """Execute a command inside the managed Docker container.

        Args:
            cmd_exec: Command string to run inside the container.
            work_dir: Working directory inside the container.
            timeout: Timeout in seconds before the command is killed.
            input_data: Optional stdin data to pipe into the command.

        Returns:
            Dict with keys 'stdout', 'stderr', and 'exit_code'. On timeout,
            'exit_code' is -1 and 'stderr' is 'Command timed out'.
        """
        self.start_container()

        assert self.id_container is not None and self.id_container

        exec_bash = ["docker", "exec", "-w", work_dir]
        if input_data is not None:
            exec_bash.append("-i")
        exec_bash += [self.id_container, "bash", "-c", cmd_exec]
        try:
            container_exec = subprocess.run(
                exec_bash,
                input=input_data,
                capture_output=True,
                text=True,
                timeout=timeout,
            )
            return {
                "stdout": container_exec.stdout,
                "stderr": container_exec.stderr,
                "exit_code": container_exec.returncode,
            }
        except subprocess.TimeoutExpired:
            return {
                "stdout": "",
                "stderr": "Command timed out",
                "exit_code": -1,
            }

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
def read_file(
    filepath: str,
    start_line: int | None = 1,
    end_line: int | None = -1,
) -> str:
    """Read the content of a file with line numbers.

    Args:
        filepath: The absolute or relative path to the file.
        start_line: The line number to start reading from (1-indexed).
        end_line: The line number to stop reading at (-1 = end).

    Returns:
        File content formatted as '<line_number>: <line_content>'.
    """
    get_container = container_sandbox()
    if isinstance(get_container, str):
        return get_container

    out = get_container.exec(f"cat {shlex.quote(filepath)}")
    if out["exit_code"] != 0:
        return f"Error: {out['stderr'].strip()}"
    lines = out["stdout"].splitlines()
    total = len(lines)
    start = 1 if start_line is None else start_line
    end = -1 if end_line is None else end_line
    start_idx = max(0, start - 1)
    end_idx = total if end == -1 else min(end, total)
    chunk = [f"{i + 1}: {lines[i]}" for i in range(start_idx, end_idx)]
    return "\n".join(chunk) if chunk else "Error: No lines in range."


@mcp.tool()
def edit_file(filepath: str, old_str: str, new_str: str) -> str:
    """Replace an exact string in a file with a new string.

    Args:
        filepath: The path to the file to edit.
        old_str: The exact string to find and replace.
        new_str: The replacement string.

    Returns:
        A success message or an error if the string was not found.
    """
    get_container = container_sandbox()
    if isinstance(get_container, str):
        return get_container

    read = get_container.exec(f"cat {shlex.quote(filepath)}")
    if read["exit_code"] != 0:
        raise FileNotFoundError(
            f"edit_file made NO changes: file '{filepath}' not found."
        )
    content = read["stdout"]
    if old_str not in content:
        lines = content.splitlines()
        anchor = max(
            (ln.strip() for ln in old_str.splitlines()),
            key=len,
            default="",
        )[:40]
        hints: list[str] = []
        if anchor:
            for i, line in enumerate(lines, 1):
                if anchor in line:
                    window = lines[i - 1: i + 1]
                    hints.extend(
                        f"{i + off}: {w}" for off, w in enumerate(window)
                    )
        hint_text = "\n".join(hints[:12]) or "(no similar lines found)"
        raise ValueError(
            "edit_file made NO changes: 'old_str' was not found "
            "exactly. It must match the file byte-for-byte, including "
            "leading indentation and newlines (the target often spans "
            "several lines). Closest lines in the file:\n"
            f"{hint_text}\n"
            "Re-read these exact lines and copy them verbatim as "
            "old_str."
        )
    occurrences = content.count(old_str)
    new_content = content.replace(old_str, new_str)
    write = get_container.exec(
        f"cat > {shlex.quote(filepath)}", input_data=new_content
    )
    if write["exit_code"] != 0:
        raise IOError(f"edit_file failed to write: {write['stderr'].strip()}")

    return f"Success: Replaced {occurrences} occurrence(s)."


@mcp.tool()
def list_files(directory: str, pattern: str = "*") -> str:
    """List files in a directory matching a given pattern.

    Args:
        directory: The directory path to search in.
        pattern: Glob pattern to match (e.g., '*.py', '*test*').

    Returns:
        A list of matching file paths, one per line.
    """
    get_container = container_sandbox()
    if isinstance(get_container, str):
        return get_container

    out = get_container.exec(
        f"find {shlex.quote(directory)} -type f "
        f"-name {shlex.quote(pattern)}"
    )
    if out["exit_code"] != 0:
        return f"Error: {out['stderr'].strip()}"
    return out["stdout"].strip() or f"No files matching '{pattern}'."


@mcp.tool()
def search_code(pattern: str, file_pattern: str = "*.py") -> str:
    """Search for a regex pattern across the testbed.

    Args:
        pattern: Regular expression to search for.
        file_pattern: Glob pattern to filter files (e.g., '*.py').

    Returns:
        Matching lines formatted as '/path:line content', capped
        at 100 results.
    """
    get_container = container_sandbox()
    if isinstance(get_container, str):
        return get_container

    out = get_container.exec(
        f"grep -rEn --include={shlex.quote(file_pattern)} "
        f"-e {shlex.quote(pattern)} {TESTBED}"
    )
    if out["exit_code"] not in (0, 1):
        return f"Error: {out['stderr'].strip()}"
    lines = out["stdout"].splitlines()
    if not lines:
        return f"No matches found for '{pattern}'."
    formatted = []
    for ln in lines[:100]:
        parts = ln.split(":", 2)
        formatted.append(
            f"{parts[0]}:{parts[1]} {parts[2]}" if len(parts) == 3 else ln
        )
    if len(lines) > 100:
        formatted.append(
            f"...and {len(lines) - 100} more. Refine your search."
        )
    return "\n".join(formatted)


@mcp.tool()
def search_function_or_class_definition_in_code(name: str) -> str:
    """Find a function or class definition by name.

    Args:
        name: The function or class name to search for.

    Returns:
        Matching definition lines from the testbed.
    """
    return search_code(f"(def|class) {name}")


@mcp.tool()
def find_references(
    name: str,
    filepath: str | None = None,
    line: int | None = None,
) -> str:
    """Find all usages of a symbol (function or class) in the testbed.

    The symbol is matched as a whole word (``\\bname\\b``) so that
    ``foo`` does not also match ``foobar``. The optional ``filepath``
    and ``line`` arguments narrow the search to disambiguate a symbol:
    ``filepath`` restricts results to a single file, and ``line``
    filters them to that exact line (useful to pinpoint one definition
    among several identically-named symbols).

    Args:
        name: Symbol name to search for.
        filepath: Optional file to restrict the search to.
        line: Optional line number to keep only matches on that line.

    Returns:
        Matching lines in search_code format ('/path:line content'),
        or a message if nothing matched.
    """
    results = search_code(rf"\b{name}\b")
    if filepath is None and line is None:
        return results
    if results.startswith(("No matches", "Error:")):
        return results
    target = os.path.basename(filepath) if filepath else None
    kept = []
    for ln in results.splitlines():
        loc = ln.split(" ", 1)[0]  # '/path:line'
        path, _, lineno = loc.rpartition(":")
        if target is not None and os.path.basename(path) != target:
            continue
        if line is not None and lineno != str(line):
            continue
        kept.append(ln)
    return "\n".join(kept) if kept else f"No references to '{name}' found."


@mcp.tool()
def run_command(command: str, workdir: str = TESTBED) -> str:
    """Run an arbitrary bash command in the Docker container.

    Args:
        command: Command to execute.
        workdir: Working directory inside the container.

    Returns:
        Formatted string with stdout, stderr, and exit code.
    """
    get_container = container_sandbox()
    if isinstance(get_container, str):
        return get_container

    out = get_container.exec(command, workdir)
    return (
        f"STDOUT:\n{out['stdout']}\n\nSTDERR:\n{out['stderr']}"
        f"\n\nEXIT_CODE:\n{out['exit_code']}"
    )


@mcp.tool()
def get_patch() -> str:
    """Return the current git diff from the testbed.

    Returns:
        Unified diff string of all uncommitted changes.
    """
    get_container = container_sandbox()
    if isinstance(get_container, str):
        return get_container

    out = get_container.exec("git -c core.fileMode=false diff")
    return str(out["stdout"])


@mcp.tool()
def run_tests() -> str:
    """Run the evaluation script inside the Docker container.

    Returns:
        Formatted string with stdout, stderr, and exit code.
    """
    get_container = container_sandbox()
    if isinstance(get_container, str):
        return get_container

    out = get_container.exec(get_container.eval_script, timeout=900)
    return (
        f"STDOUT:\n{out['stdout']}\n\nSTDERR:\n{out['stderr']}"
        f"\n\nEXIT_CODE:\n{out['exit_code']}"
    )


def main():
    if "--http" in sys.argv:
        mcp.run(transport="streamable-http")
    else:
        mcp.run(transport="stdio")


if __name__ == "__main__":
    main()
