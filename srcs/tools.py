# File System Tools ->
def read_file(filepath, start_line, end_line):
    """
    Read the content of a file with line numbers.
    """
    pass


def edit_file(filepath, old_str, new_str):
    """
    Replace an exact string in a file with a new string.
    """
    pass


def list_files(directory, pattern):
    """
    List files in a directory matching a given pattern.
    """
    pass


# Code Search Tools ->
def search_code(pattern, file_pattern):
    """
    Perform a grep-like search in the codebase.
    """
    pass


def search_function_or_class_definition_in_code(name):
    """
    Find the definition of a function or a class.
    """
    pass


def find_references(name, filepath, line):
    """
    Find all usages of a symbol (function or class).
    """
    pass


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
