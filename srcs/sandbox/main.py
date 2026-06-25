from srcs.sandbox.sandbox import Sandbox
from fire import Fire


def main():
    sandbox = Sandbox()
    Fire(sandbox.cli)


if __name__ == "__main__ ":
    main()
