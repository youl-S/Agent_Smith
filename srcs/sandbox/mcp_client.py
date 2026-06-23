import asyncio
from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client
from mcp.client.streamable_http import streamablehttp_client


class MCPConnection:
    def __init__(self):
        self.loop = asyncio.new_event_loop()
        self.session = None
        self._transport_cm = None
        self._session_cm = None


