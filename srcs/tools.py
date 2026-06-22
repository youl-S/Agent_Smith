import re
import jedi
from pathlib import Path
from jedi.api.classes import Name


# File System Tools ->
def read_file(filepath, start_line, end_line):
    """
    Read the content of a file with line numbers.
    """
    try:
        with open(filepath, "r") as f:
            lines = f.readlines()

            for i, line in enumerate(lines, start=1):
                if start_line <= i <= end_line:
                    print(f"{i}: {line}", end="")
    except Exception as e:
        print(f"Error reading {filepath}: {e}")


def edit_file(filepath, old_str, new_str):
    """
    Replace an exact string in a file with a new string.
    """
    try:
        with open(filepath, "r") as f:
            content = f.read()

            if old_str not in content:
                print(f"{old_str} not found in {filepath}")
                return

        with open(filepath, "w") as f:
            content = content.replace(old_str, new_str, 1)
            f.write(content)

    except Exception as e:
        print(f"Error reading and writing {filepath}: {e}")


def list_files(directory, pattern):
    """
    List files in a directory matching a given pattern.
    """

    directory_path = Path(directory)

    if not directory_path.is_dir():
        return

    for file in directory_path.glob(pattern):
        print(file)


# Code Search Tools ->
def search_code(pattern, file_pattern):
    """
    Perform a grep-like search in the codebase.
    """
    directory = Path("/testbed")

    for file in directory.rglob(file_pattern):
        try:
            with open(file, "r") as f:
                for i, line in enumerate(f, start=1):
                    if pattern in line:
                        print(f"{file.resolve()}:{i} {line.rstrip()}")
        except Exception:
            pass


def search_function_or_class_definition_in_code(name):
    """
    Find the definition of a function or a class.
    """
    directory = Path("/testbed")
    pattern = re.compile(rf"^\s*(def|class)\s+{re.escape(name)}\b")

    for file in directory.rglob("*.py"):
        try:
            with open(file, "r") as f:
                for i, line in enumerate(f, start=1):
                    if pattern.search(line):
                        print(f"{file.resolve()}:{i} {line.rstrip()}")
        except Exception:
            pass


def find_references(name, filepath, line):
    """
    Find all usages of a symbol (function or class).
    """
    project = jedi.Project(path="/testbed")

    try:
        with open(filepath, "r") as f:
            source = f.read()
            script = jedi.Script(code=source, path=filepath, project=project)

            lines = source.splitlines()
            target_line = lines[line - 1]
            column = target_line.find(name)

            if column == -1:
                print(f"{name} not found in {filepath}")
                return

            references = script.get_references(
                line, column, include_builtins=False
            )
        for ref in references:
            if isinstance(ref, Name):
                path = ref.module_path
                if path is None:
                    continue
                line_n = ref.line

                with open(path) as f:
                    content = f.readlines()[line_n - 1]
                print(f"{path}:{line_n} {content}", end="")

    except Exception as e:
        print(f"Error finding references for {name} in {filepath}: {e}")


# Execution Tools ->
def run_tests():
    """
    Execute the evaluation script.
    """
    pass


def get_patch():
    """
    Retrieve the unified git diff of all changes made to the repository,
    depending on the implementation.
    """
    pass


def run_command(command, workdir):
    """
    Execute a shell command in the specified working directory.
    Returns the command's stdout, stderr, and exit code.
    """
    pass
