from mcp.server.fastmcp import FastMCP

# crée le server avec un nom
mcp = FastMCP("mbpp-tools", port=8080)


@mcp.tool()
def add(a: int, b: int) -> int:
    """Additionne deux nombres."""
    return a + b


@mcp.tool()
def read_file(filepath: str) -> str:
    """Lit le contenu d'un fichier."""
    with open(filepath, "r") as f:
        return f.read()


if __name__ == "__main__":
    import sys

    if "--http" in sys.argv:
        mcp.run(transport="streamable-http")
    else:
        mcp.run()
