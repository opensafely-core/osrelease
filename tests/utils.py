import io
from datetime import datetime
from http.client import HTTPResponse


class UrlopenFixture:
    """Fixture for mocking urlopen."""

    request = None
    response = None

    class socket:
        """Minimal socket api as used by HTTPResponse"""

        def __init__(self, data):
            self.stream = io.BytesIO(data)

        def makefile(self, mode):
            return self.stream

    def set_response(self, status, headers={}, body=None):
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

        self.sock = self.socket(data)

    def urlopen(self, request):
        """Replacement urlopen function."""
        self.request = request
        self.response = HTTPResponse(self.sock, method=request.method)
        self.response.begin()
        return self.response
