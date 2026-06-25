import asyncio
from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client
from mcp.client.streamable_http import streamable_http_client


class McpClient:
    def __init__(self):
        self.loop = asyncio.new_event_loop()
        self.session = None
        self._transport_cm = None
        self._session_cm = None

    def _open_session(self, read, write):
        self._session_cm = ClientSession(read, write)
        self.session = self.loop.run_until_complete(
            self._session_cm.__aenter__()
        )
        self.loop.run_until_complete(self.session.initialize())

    def stdio_client(self, command, args):
        self._transport_cm = stdio_client(
            StdioServerParameters(command=command, args=[args])
        )
        read, write = self.loop.run_until_complete(
            self._transport_cm.__aenter__()
        )
        self._open_session(read, write)

    def http_client(self, connect_adress="http://localhost:8080/mcp"):

        self._transport_cm = streamable_http_client(connect_adress)
        read, write, _ = self.loop.run_until_complete(
            self._transport_cm.__aenter__()
        )
        self._open_session(read, write)

    def list_tools(self):
        return self.loop.run_until_complete(self.session.list_tools())

    def call_tool(self, name, args):
        return self.loop.run_until_complete(self.session.call_tool(name, args))

    def close(self):
        self.loop.run_until_complete(
            self._session_cm.__aexit__(None, None, None)
        )
        self.loop.run_until_complete(
            self._transport_cm.__aexit__(None, None, None)
        )
        self.loop.close()
