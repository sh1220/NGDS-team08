"""차분시 MCP 서버 (FastMCP, Streamable HTTP). /mcp 로 붙고, /metrics 는 Prometheus 수집용."""
from fastmcp import FastMCP
from prometheus_client import Counter, start_http_server

mcp = FastMCP("chabunsi")
CALLS = Counter("chabunsi_tool_calls_total", "MCP 도구 호출 수", ["tool"])


@mcp.tool
def ping(message: str = "ping") -> str:
    """연결 확인용 예시 도구. 실제 도구는 여기에 추가한다."""
    CALLS.labels("ping").inc()
    return f"pong: {message}"


if __name__ == "__main__":
    start_http_server(9000)  # /metrics
    mcp.run(transport="http", host="0.0.0.0", port=8000)
