from __future__ import annotations

import ipaddress
import socket
import time
import urllib.error
import urllib.parse
import urllib.request
from typing import Any

from .base import BaseTool, ToolMetadata, ToolResult


class SafeRedirectHandler(urllib.request.HTTPRedirectHandler):
    """Custom HTTP redirect handler enforcing SSRF checks on redirect Location headers."""

    def __init__(self, allow_localhost: bool = False) -> None:
        super().__init__()
        self.allow_localhost = allow_localhost

    def redirect_request(
        self, req: urllib.request.Request, fp: Any, code: int, msg: str, headers: Any, newurl: str
    ) -> urllib.request.Request | None:
        is_safe, error_msg = RealHTTPRetrievalTool.check_ssrf_safety(newurl, self.allow_localhost)
        if not is_safe:
            raise urllib.error.URLError(f"Redirect blocked by SSRF policy: {error_msg}")
        return super().redirect_request(req, fp, code, msg, headers, newurl)


class RealHTTPRetrievalTool(BaseTool):
    """Built-in tool for fetching web content using safe, SSRF-protected HTTP GET requests."""

    metadata = ToolMetadata(
        name="real_http_retrieval_tool",
        description="Fetches web page text content or REST API data using safe HTTP GET requests",
        category="web",
        parameters_schema={
            "required": ["url"],
            "properties": {
                "url": {"type": "string"},
                "method": {"type": "string", "default": "GET"},
                "timeout_seconds": {"type": "number", "default": 5.0},
            },
        },
        risk_level="reversible",
        requires_confirmation=False,
        read_only=True,
    )

    MAX_RESPONSE_BYTES = 1 * 1024 * 1024  # 1 MB limit
    DEFAULT_TIMEOUT_SEC = 5.0
    MAX_TIMEOUT_SEC = 10.0

    def __init__(self, allow_localhost: bool = False) -> None:
        self.allow_localhost = allow_localhost

    @classmethod
    def is_ip_blocked(cls, ip_str: str) -> bool:
        """Checks if an IP address string is loopback, private, link-local, or reserved."""
        try:
            ip = ipaddress.ip_address(ip_str)
        except ValueError:
            return False
        else:
            return (
                ip.is_loopback
                or ip.is_private
                or ip.is_link_local
                or ip.is_multicast
                or ip.is_unspecified
                or ip.is_reserved
            )

    @classmethod
    def check_ssrf_safety(cls, url_str: str, allow_localhost: bool = False) -> tuple[bool, str]:
        """Validates scheme, host, and IP addresses against SSRF attack vectors."""
        try:
            parsed = urllib.parse.urlparse(url_str)
        except Exception as exc:
            return False, f"Malformed URL '{url_str}': {exc}"

        scheme = (parsed.scheme or "").lower()
        if scheme not in ("http", "https"):
            return False, f"Unauthorized scheme '{scheme}'. Only http and https URLs are allowed."

        hostname = parsed.hostname
        if not hostname:
            return False, "Invalid URL: missing hostname."

        hostname_lower = hostname.lower().strip()

        if allow_localhost and hostname_lower in ("localhost", "127.0.0.1", "::1"):
            return True, "OK"

        if (
            hostname_lower in ("localhost", "0.0.0.0")
            or hostname_lower.endswith(".local")
            or hostname_lower.endswith(".internal")
        ):
            return False, f"Access to private hostname '{hostname}' is blocked by SSRF policy."

        try:
            ip_info = socket.getaddrinfo(hostname, None)
            for item in ip_info:
                sockaddr = item[4]
                ip_addr = str(sockaddr[0])
                if cls.is_ip_blocked(ip_addr) and not allow_localhost:
                    err_msg = (
                        f"Access to IP '{ip_addr}' (resolved from '{hostname}') "
                        f"is blocked by SSRF policy."
                    )
                    return False, err_msg
        except socket.gaierror:
            pass

        return True, "OK"

    def execute(
        self,
        url: str = "",
        method: str = "GET",
        timeout_seconds: float = DEFAULT_TIMEOUT_SEC,
        **kwargs: Any,
    ) -> ToolResult:
        t0 = time.perf_counter()

        if not url or not url.strip():
            return ToolResult(
                success=False,
                error="URL parameter cannot be empty",
                execution_time_ms=(time.perf_counter() - t0) * 1000,
            )

        norm_method = (method or "GET").upper().strip()
        if norm_method != "GET":
            return ToolResult(
                success=False,
                error=f"Unauthorized HTTP method '{method}'. Only GET requests are permitted.",
                execution_time_ms=(time.perf_counter() - t0) * 1000,
            )

        timeout = max(0.5, min(float(timeout_seconds), self.MAX_TIMEOUT_SEC))

        is_safe, error_msg = self.check_ssrf_safety(url, self.allow_localhost)
        if not is_safe:
            return ToolResult(
                success=False,
                error=f"SSRF Security Violation: {error_msg}",
                execution_time_ms=(time.perf_counter() - t0) * 1000,
            )

        try:
            req = urllib.request.Request(
                url=url,
                headers={"User-Agent": "AURA-Assistant/1.6 (Environment-Observation)"},
                method="GET",
            )

            opener = urllib.request.build_opener(SafeRedirectHandler(self.allow_localhost))

            with opener.open(req, timeout=timeout) as response:
                status_code = response.getcode()
                raw_headers = dict(response.headers)
                sanitized_headers = {str(k).lower(): str(v) for k, v in raw_headers.items()}

                chunks: list[bytes] = []
                total_bytes = 0
                chunk_size = 8192

                while True:
                    chunk = response.read(chunk_size)
                    if not chunk:
                        break
                    chunks.append(chunk)
                    total_bytes += len(chunk)
                    if total_bytes >= self.MAX_RESPONSE_BYTES:
                        break

                raw_bytes = b"".join(chunks)[: self.MAX_RESPONSE_BYTES]
                text_content = raw_bytes.decode("utf-8", errors="replace")

                elapsed = (time.perf_counter() - t0) * 1000
                return ToolResult(
                    success=True,
                    output={
                        "status_code": status_code,
                        "url": url,
                        "headers": sanitized_headers,
                        "content": text_content,
                        "bytes_read": len(raw_bytes),
                        "truncated": total_bytes >= self.MAX_RESPONSE_BYTES,
                    },
                    execution_time_ms=elapsed,
                )

        except urllib.error.HTTPError as http_err:
            elapsed = (time.perf_counter() - t0) * 1000
            return ToolResult(
                success=False,
                error=f"HTTP Error {http_err.code}: {http_err.reason}",
                execution_time_ms=elapsed,
            )

        except (urllib.error.URLError, TimeoutError) as net_err:
            elapsed = (time.perf_counter() - t0) * 1000
            error_text = str(net_err)
            if isinstance(net_err, socket.timeout) or "timed out" in error_text.lower():
                error_text = f"HTTP request to '{url}' timed out after {timeout} seconds"
            return ToolResult(
                success=False,
                error=f"Network error: {error_text}",
                execution_time_ms=elapsed,
            )

        except Exception as exc:
            elapsed = (time.perf_counter() - t0) * 1000
            return ToolResult(
                success=False,
                error=f"HTTP retrieval failed: {exc}",
                execution_time_ms=elapsed,
            )
