import socket
import sys
from collections.abc import AsyncGenerator

import pytest
from httpx import ASGITransport, AsyncClient

# On Windows environments where loopback TCP handshakes are restricted or filtered,
# standard socket.socketpair hangs during accept(). Use a non-blocking UDP socketpair fallback.
if sys.platform == "win32":

    def _safe_socketpair(_family=socket.AF_INET, _type=socket.SOCK_STREAM, _proto=0):
        s1 = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s1.bind(("127.0.0.1", 0))
        s2 = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s2.bind(("127.0.0.1", 0))
        s1.connect(s2.getsockname())
        s2.connect(s1.getsockname())
        return s1, s2

    socket.socketpair = _safe_socketpair

from api.main import app


@pytest.fixture
async def async_client() -> AsyncGenerator[AsyncClient, None]:
    """Asynchronous test client fixture for FastAPI endpoint tests."""
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        yield client
