from mcp.server.fastmcp import FastMCP
import subprocess
import os

mcp = FastMCP("swebench-tools")
execute_containeur = None  # global mem (MCPToolSwe(id...))
TESTBED = "/testbed"  # code patch


# child (mcpswetoo) parent(agent-swe)
def load_config() -> tuple[str, str]:
    task_image = os.getenv("SWE_DOCKER_IMG")  # from agent set environ()
    if not task_image:
        raise ValueError('Error missing image docker')

    eval_script = os.getenv("SWE_EVAL_SCRIPT")
    if not eval_script:
        raise ValueError('Error missing script to evaluate')

    print(task_image, eval_script)
    return task_image, eval_script


class DockerExec:
    def __init__(self, task_image, eval_script) -> None:
        self.task_image = task_image
        self.eval_script = eval_script
        self.id_containeur: str | None = None  # remplir

    def start_containeur(self) -> None:
        if self.id_containeur:
            return  # pas de start si on a deja pull (Django..)
        # aucun reseau d arriere plan (None)

        run_docker = subprocess.run(["docker", "run", "--network", "none",
                                     "-d", self.task_image,
                                     "sleep", "infinity"],
                                    capture_output=True,  # catch
                                    text=True,
                                    check=True)  # print

        if run_docker.returncode != 0:
            print('error')

        self.id_containeur = run_docker.stdout.strip("\n")
        # print(self.id_containeur)

    def exec(self, cmd_exec: str, work_dir: str = TESTBED):
        # for exec cmd tool
        self.start_containeur()  # si un containeur est present
        assert self.id_containeur is not None

        if not self.id_containeur:
            raise ValueError('Cannot find id_containeur')
        exec_bash = ["docker", "exec", "-w", work_dir, self.id_containeur,
                     "bash", "-c", cmd_exec]
        containeur_exec = subprocess.run(exec_bash,
                                         capture_output=True, text=True)
        return containeur_exec

    def clean_containeur(self) -> None:
        if self.id_containeur:
            subprocess.run(["docker", "rm", "-f", self.id_containeur])

# read ... (exec avec docker chaques cmd dans un containeur)


# for execute into containeur
def containeur_sandbox():
    global execute_containeur
    try:
        if execute_containeur is None:
            task_image, evaluation_script = load_config()
            print(load_config)
            execute_containeur = DockerExec(task_image, evaluation_script)
            print(execute_containeur)
    except ValueError as e:
        print(e)
    return execute_containeur


@mcp.tool()
def read_file(filepath: str, start_line: int = 1, end_line: int = -1):
    execution_containeur = containeur_sandbox()
    if execute_containeur is None:
        return "Error init sandbox docker"

    cmd = execution_containeur.exec(f"cat {filepath}")
    if cmd.returncode != 0:
        return f"Error {cmd.stderr.strip()}"

    get_line = cmd.stdout.splitlines()
    lines_total = len(get_line)

    start_idx = max(0, start_line - 1)
    if end_line == -1:
        end_idx = lines_total
    else:
        end_idx = min(end_line, lines_total)

    format_output = []
    for numbers, lines in enumerate(
            get_line[start_idx:end_idx],
            start=start_line
            ):
        format_output.append(f"{numbers}: {lines}")
    if not format_output:
        return "File is empty"
    return '\n'.join(format_output)


@mcp.tool()
def edit_file(filepath: str, old_str: str, new_str: str):
    pass


@mcp.tool()
def list_files(directory: str, pattern: str = "*"):
    execute_containeur = containeur_sandbox()
    cmd = execute_containeur.exec(f"find {directory} -type \
                                  f -name {pattern}")
    if cmd.returncode != 0:
        return f"Error {cmd.stderr.strip()}"
    return cmd.stdout.strip()


@mcp.tool()
def search_code(pattern: str, file_pattern: str = '*'):
    pass


@mcp.tool()
def search_function_or_class_definition_in_code(name: str):
    pass


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
    pass


# git -c core.fileMode=false dif

if __name__ == "__main__":
    os.environ["SWE_DOCKER_IMG"] = "swebench/sweb.eval.x86_64.sympy_1776_sympy-18189:latest"
    os.environ["SWE_EVAL_SCRIPT"] = "/testbed/eval.sh"
    # try:
    exec_test = containeur_sandbox()
    tool_read = read_file("/testbed/sympy/__init__.py", 0, 10)
    print(tool_read)
    # testeur = DockerExec(test_img, eval_script="/testbed/eval.sh")
    # testeur.start_containeur()
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
        print('clean containeur')
        exec_test.clean_containeur()
        print('clean Ok')
    # except subprocess.CalledProcessError as e:
    #     print(f"error {e.stderr}")
