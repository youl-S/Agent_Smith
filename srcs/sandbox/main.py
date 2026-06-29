from srcs.sandbox.sandbox import Sandbox
from fire import Fire


def main() -> None:
    """Build the Sandbox and expose its CLI through Fire."""
    sandbox = Sandbox()
    Fire(sandbox.cli)


if __name__ == "__main__":
    main()
