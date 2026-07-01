from mcp.server.fastmcp import FastMCP
import subprocess
import os

mcp = FastMCP("swebench-tools")
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


class McpToolSwe:
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
                                    text=True)  # print

        self.id_containeur = run_docker.stdout.strip("\n")
        print(self.id_containeur)

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
# @mcp.tool()


# git -c core.fileMode=false dif
