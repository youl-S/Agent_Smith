from srcs.sandbox.sandbox import Sandbox
from fire import Fire


def main() -> None:
    """Build the Sandbox and expose its CLI through Fire."""
    try:
        sandbox = Sandbox()
        Fire(sandbox.cli)
    except Exception as e:
        print(f"Error: {e}")


if __name__ == "__main__":
    main()
