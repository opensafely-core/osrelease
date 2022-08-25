import io
from collections import deque
from datetime import datetime
from http.client import HTTPResponse


class UrlopenFixture:
    """Fixture for mocking urlopen."""

    def __init__(self):
        self.requests = []
        self.responses = deque()

    class socket:
        """Minimal socket api as used by HTTPResponse"""

        def __init__(self, data):
            self.stream = io.BytesIO(data)

        def makefile(self, mode):
            return self.stream

    def add_response(self, status, headers={}, body=None):
        """Create a HTTP response byte-stream to be parsed by HTTPResponse."""
        lines = [f"HTTP/1.1 {status.value} {status.phrase}"]
        lines.append(f"Date: {datetime.utcnow().strftime('%a, %d %b %Y %H:%M:%S')}")
        lines.append("Server: TestServer/1.0")
        for name, value in headers.items():
            lines.append(f"{name}: {value}")

        if body:
            lines.append(f"Content-Length: {len(body)}")
            lines.append("")
            lines.append("")

        data = ("\r\n".join(lines)).encode("ascii")
        if body:
            data += body.encode("utf8")

        self.responses.append(self.socket(data))

    def urlopen(self, request):
        """Replacement urlopen function."""
        self.requests.append(request)
        try:
            socket = self.responses.popleft()
        except IndexError:
            raise AssertionError("No mocked urlopen responses left!")

        response = HTTPResponse(socket, method=request.method)
        response.begin()
        return response
