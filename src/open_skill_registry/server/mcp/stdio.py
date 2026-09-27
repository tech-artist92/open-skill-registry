"""Stdio Transport for MCP Server (T072).

Processes line-delimited JSON-RPC 2.0 messages from standard input (or any stream)
and outputs responses to standard output.
"""

import inspect
import json
import logging
import sys
from typing import Any

from open_skill_registry.server.mcp.handler import MCPHandler

logger = logging.getLogger(__name__)


async def run_stdio_server(
    handler: MCPHandler,
    reader: Any | None = None,
    writer: Any | None = None,
) -> None:
    """Run line-delimited JSON-RPC loop over reader and writer streams.

    Args:
        handler: MCPHandler instance to process requests.
        reader: Input stream or reader object (defaults to sys.stdin).
        writer: Output stream or writer object (defaults to sys.stdout).
    """
    if reader is None:
        reader = sys.stdin
    if writer is None:
        writer = sys.stdout

    while True:
        try:
            line_or_coro = reader.readline()
            if inspect.isawaitable(line_or_coro):
                line = await line_or_coro
            else:
                line = line_or_coro

            if not line:
                # EOF reached
                break

            if isinstance(line, bytes):
                line = line.decode("utf-8")

            line_str = line.strip()
            if not line_str:
                continue

            response = await handler.handle_raw(line_str)
            if response is None:
                # Silent notification
                continue

            data = response.model_dump()
            if response.error is None and "error" in data:
                data.pop("error")
            if response.result is None and response.error is not None and "result" in data:
                data.pop("result")

            out_text = json.dumps(data) + "\n"

            write_res = writer.write(out_text)
            if inspect.isawaitable(write_res):
                await write_res

            if hasattr(writer, "flush"):
                flush_res = writer.flush()
                if inspect.isawaitable(flush_res):
                    await flush_res

            if hasattr(writer, "drain"):
                drain_res = writer.drain()
                if inspect.isawaitable(drain_res):
                    await drain_res

        except (KeyboardInterrupt, SystemExit):
            break
        except Exception as exc:
            logger.exception("Error in stdio server loop: %s", exc)
