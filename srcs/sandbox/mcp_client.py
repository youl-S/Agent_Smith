import asyncio
from typing import Any

from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client
from mcp.client.streamable_http import streamable_http_client
from mcp.types import (
    CallToolResult,
    ListPromptsResult,
    ListResourcesResult,
    ListToolsResult,
)


class McpClient:
    """Synchronous wrapper around an MCP client session.

    The MCP SDK is asyncio-based; this class owns a private event loop and
    drives every coroutine with ``run_until_complete`` so the rest of the
    sandbox can talk to the server through plain blocking methods.
    """

    def __init__(self) -> None:
        """Create the event loop; the session is opened later on connect."""
        self.loop = asyncio.new_event_loop()
        self.session: ClientSession | None = None
        self._transport_cm: Any = None
        self._session_cm: ClientSession | None = None

    def _open_session(self, read: Any, write: Any) -> None:
        """Open an MCP session over an already-connected transport.

        ``read``/``write`` are the stream pair yielded by a transport
        context manager (stdio or streamable HTTP).
        """
        self._session_cm = ClientSession(read, write)
        self.session = self.loop.run_until_complete(
            self._session_cm.__aenter__()
        )
        self.loop.run_until_complete(self.session.initialize())

    def stdio_client(self, command: str, arg: str) -> None:
        """Spawn an MCP server as a subprocess and open a stdio session."""
        self._transport_cm = stdio_client(
            StdioServerParameters(command=command, args=[arg])
        )
        read, write = self.loop.run_until_complete(
            self._transport_cm.__aenter__()
        )
        self._open_session(read, write)

    def http_client(
        self, connect_adress: str = "http://localhost:8080/mcp"
    ) -> None:
        """Connect to a streamable-HTTP MCP server and open a session."""
        self._transport_cm = streamable_http_client(connect_adress)
        read, write, _ = self.loop.run_until_complete(
            self._transport_cm.__aenter__()
        )
        self._open_session(read, write)

    def list_tools(self) -> ListToolsResult:
        """Return the tools advertised by the connected MCP server."""
        assert self.session is not None
        return self.loop.run_until_complete(self.session.list_tools())

    def list_prompts(self) -> ListPromptsResult:
        """Return the prompts advertised by the connected MCP server."""
        assert self.session is not None
        return self.loop.run_until_complete(self.session.list_prompts())

    def list_resources(self) -> ListResourcesResult:
        """Return the resources advertised by the connected MCP server."""
        assert self.session is not None
        return self.loop.run_until_complete(self.session.list_resources())

    def call_tool(self, name: str, args: dict[str, Any]) -> CallToolResult:
        """Invoke a tool by name with kwargs and return its result."""
        assert self.session is not None
        return self.loop.run_until_complete(self.session.call_tool(name, args))

    def close(self) -> None:
        """Tear down the session, the transport and the event loop."""
        assert self._session_cm is not None
        self.loop.run_until_complete(
            self._session_cm.__aexit__(None, None, None)
        )
        self.loop.run_until_complete(
            self._transport_cm.__aexit__(None, None, None)
        )
        self.loop.close()
