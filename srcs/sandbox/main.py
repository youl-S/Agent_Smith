from srcs.sandbox.sandbox import Sandbox
from srcs.sandbox.sandbox_cli import SandboxCli
from fire import Fire


def main():
    sandbox = Sandbox()
    Fire(sandbox.cli)


if __name__ == "__main__ ":
    main()
