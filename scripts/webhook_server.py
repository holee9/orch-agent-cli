"""GitHub Webhook receiver server for orch-agent-cli.

Receives GitHub webhook POST events, validates HMAC-SHA256 signatures,
and writes events to the local .orchestra/cache/webhook_events/ directory
for the Orchestrator to process.
"""

from __future__ import annotations

import hashlib
import hmac
import json
import logging
import os
import signal
import threading
from datetime import datetime, timezone
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

# Events that are persisted to disk; others are logged and ignored
SUPPORTED_EVENTS = {"issues", "issue_comment"}


class _WebhookHandler(BaseHTTPRequestHandler):
    """HTTP request handler for GitHub webhook POST requests.

    Bound to a WebhookServer instance via the ``server`` attribute so that
    signature validation and event persistence can delegate to it.
    """

    # Suppress default request-log output; we use our own logger.
    def log_message(self, format: str, *args: Any) -> None:  # noqa: A002
        logger.debug("HTTP %s", format % args)

    def do_POST(self) -> None:  # noqa: N802
        """Handle an incoming POST from GitHub."""
        content_length = int(self.headers.get("Content-Length", 0))
        raw_body = self.rfile.read(content_length)

        event_type = self.headers.get("X-GitHub-Event", "")
        signature = self.headers.get("X-Hub-Signature-256", "")

        # --- signature validation ---
        if not self.server.webhook_server._validate_signature(raw_body, signature):  # type: ignore[attr-defined]
            logger.warning("Invalid signature for event '%s'; rejecting.", event_type)
            self._respond(401, "Unauthorized")
            return

        # --- body parsing ---
        try:
            payload: dict[str, Any] = json.loads(raw_body)
        except json.JSONDecodeError as exc:
            logger.error("Failed to parse JSON body: %s", exc)
            self._respond(400, "Bad Request")
            return

        logger.info("Received GitHub event: %s", event_type)

        # --- dispatch ---
        if event_type in SUPPORTED_EVENTS:
            self.server.webhook_server._handle_event(event_type, payload)  # type: ignore[attr-defined]
        else:
            logger.info("Unsupported event type '%s'; skipping persistence.", event_type)

        self._respond(200, "OK")

    def _respond(self, code: int, message: str) -> None:
        body = message.encode()
        self.send_response(code)
        self.send_header("Content-Type", "text/plain")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)


class _BoundHTTPServer(HTTPServer):
    """HTTPServer subclass that holds a back-reference to WebhookServer."""

    def __init__(
        self,
        server_address: tuple[str, int],
        RequestHandlerClass: type,  # noqa: N803
        webhook_server: WebhookServer,
    ) -> None:
        super().__init__(server_address, RequestHandlerClass)
        self.webhook_server = webhook_server


class WebhookServer:
    """GitHub Webhook receiver that writes events to the orchestra state dir.

    Parameters
    ----------
    host:
        Interface to bind to (default ``"0.0.0.0"``).
    port:
        TCP port to listen on (default ``9000``).
    secret:
        Shared secret for HMAC-SHA256 validation.  When *None* all
        signatures are accepted (useful for local development).
    orchestra_dir:
        Root of the orchestra state directory.  Events are written to
        ``<orchestra_dir>/cache/webhook_events/``.
    """

    def __init__(
        self,
        host: str = "0.0.0.0",
        port: int = 9000,
        secret: str | None = None,
        orchestra_dir: str | Path = ".orchestra",
    ) -> None:
        self._host = host
        self._port = port
        self._secret = secret
        self._orchestra_dir = Path(orchestra_dir)
        self._events_dir = self._orchestra_dir / "cache" / "webhook_events"
        self._httpd: _BoundHTTPServer | None = None
        self._stop_event = threading.Event()

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def start(self) -> None:
        """Start the HTTP server (blocking).

        Installs SIGINT / SIGTERM handlers so the server shuts down
        gracefully when the process receives a stop signal.
        """
        self._events_dir.mkdir(parents=True, exist_ok=True)

        self._httpd = _BoundHTTPServer(
            (self._host, self._port),
            _WebhookHandler,
            webhook_server=self,
        )

        # Graceful shutdown on SIGINT / SIGTERM
        for sig in (signal.SIGINT, signal.SIGTERM):
            signal.signal(sig, self._handle_signal)

        logger.info(
            "Webhook server listening on %s:%d (orchestra_dir=%s)",
            self._host,
            self._port,
            self._orchestra_dir,
        )

        try:
            while not self._stop_event.is_set():
                self._httpd.handle_request()
        finally:
            self._httpd.server_close()
            logger.info("Webhook server stopped.")

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _validate_signature(self, payload: bytes, signature: str) -> bool:
        """Return True when the HMAC-SHA256 signature is valid.

        If no secret is configured every request is accepted so that
        local / test environments work without configuration.

        Parameters
        ----------
        payload:
            Raw request body bytes.
        signature:
            Value of the ``X-Hub-Signature-256`` header, e.g.
            ``"sha256=<hex>"`` or an empty string.
        """
        if self._secret is None:
            return True

        if not signature.startswith("sha256="):
            return False

        expected = hmac.new(
            self._secret.encode(),
            payload,
            hashlib.sha256,
        ).hexdigest()

        received = signature[len("sha256="):]
        return hmac.compare_digest(expected, received)

    def _handle_event(self, event_type: str, payload: dict[str, Any]) -> None:
        """Persist a webhook event to ``<orchestra_dir>/cache/webhook_events/``.

        The filename is ``{timestamp}_{event_type}.json`` where *timestamp*
        is an ISO-8601 UTC string with colons replaced by hyphens so it is
        safe to use in filenames on all platforms.

        Parameters
        ----------
        event_type:
            GitHub event name, e.g. ``"issues"`` or ``"issue_comment"``.
        payload:
            Parsed JSON payload dict from the request body.
        """
        self._events_dir.mkdir(parents=True, exist_ok=True)

        ts = datetime.now(tz=timezone.utc).strftime("%Y%m%dT%H%M%S%f")
        filename = f"{ts}_{event_type}.json"
        dest = self._events_dir / filename

        record = {"event_type": event_type, "payload": payload}
        dest.write_text(json.dumps(record, indent=2))

        logger.info("Event '%s' written to %s", event_type, dest)

    def _handle_signal(self, signum: int, _frame: object) -> None:
        """Signal handler: request a graceful shutdown."""
        logger.info("Received signal %d; shutting down…", signum)
        self._stop_event.set()


# ---------------------------------------------------------------------------
# CLI entry point
# ---------------------------------------------------------------------------

def _main() -> None:
    """Entry point when executed as ``python scripts/webhook_server.py``."""
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )

    secret = os.environ.get("GITHUB_WEBHOOK_SECRET")
    orchestra_dir = os.environ.get("ORCHESTRA_DIR", ".orchestra")
    host = os.environ.get("WEBHOOK_HOST", "0.0.0.0")
    port = int(os.environ.get("WEBHOOK_PORT", "9000"))

    server = WebhookServer(
        host=host,
        port=port,
        secret=secret,
        orchestra_dir=orchestra_dir,
    )
    server.start()


if __name__ == "__main__":
    _main()
