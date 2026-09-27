"""Server-Sent Events (SSE) Transport for MCP Server (T073).

Implements:
- GET /mcp/sse (and /api/v1/mcp/sse): SSE stream emitting endpoint event and message events
- POST /mcp/messages (and /api/v1/mcp/messages): JSON-RPC message ingestion endpoint
"""

import asyncio
import json
import logging
import uuid

from fastapi import APIRouter, Query, Request, Response
from fastapi.responses import JSONResponse, StreamingResponse

from open_skill_registry.server.mcp.handler import MCPHandler

logger = logging.getLogger(__name__)

router = APIRouter(tags=["mcp"])

# Global session registry mapping sessionId -> asyncio.Queue
_sessions: dict[str, asyncio.Queue] = {}


def get_sessions(request: Request) -> dict[str, asyncio.Queue]:
    """Retrieve or initialize the active MCP SSE sessions dict."""
    if not hasattr(request.app.state, "mcp_sessions"):
        request.app.state.mcp_sessions = _sessions
    return request.app.state.mcp_sessions


def get_mcp_handler(request: Request) -> MCPHandler:
    """Retrieve or instantiate an MCPHandler for the given request."""
    if hasattr(request.app.state, "mcp_handler") and request.app.state.mcp_handler:
        return request.app.state.mcp_handler

    storage = getattr(request.app.state, "storage", None)
    config = getattr(request.app.state, "config", None)
    handler = MCPHandler(storage=storage, config=config)
    request.app.state.mcp_handler = handler
    return handler


@router.get("/sse")
async def mcp_sse_endpoint(
    request: Request,
    sessionId: str | None = Query(None),
    max_events: int | None = Query(None),
    timeout: float | None = Query(None),
) -> StreamingResponse:
    """Initialize or resume an SSE connection for MCP transport."""
    sessions = get_sessions(request)

    if sessionId and sessionId in sessions:
        session_id = sessionId
        queue = sessions[session_id]
        is_new = False
    else:
        session_id = sessionId or str(uuid.uuid4())
        queue = asyncio.Queue()
        sessions[session_id] = queue
        is_new = True

    path = request.url.path
    if "/api/v1/mcp" in path:
        messages_endpoint = f"/api/v1/mcp/messages?sessionId={session_id}"
    else:
        messages_endpoint = f"/mcp/messages?sessionId={session_id}"

    async def event_generator():
        events_sent = 0
        if is_new:
            yield f"event: endpoint\ndata: {messages_endpoint}\n\n"
            events_sent += 1
            if max_events is not None and events_sent >= max_events:
                return

        try:
            while True:
                wait_time = timeout if timeout is not None else 1.0
                try:
                    msg = await asyncio.wait_for(queue.get(), timeout=wait_time)
                    yield msg
                    events_sent += 1
                    if max_events is not None and events_sent >= max_events:
                        break
                except TimeoutError:
                    if timeout is not None:
                        break
                    continue
        except (asyncio.CancelledError, GeneratorExit):
            pass
        finally:
            sessions.pop(session_id, None)
            _sessions.pop(session_id, None)

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )


@router.post("/messages")
async def mcp_messages_endpoint(
    request: Request,
    sessionId: str | None = Query(None),
) -> Response:
    """Accept MCP JSON-RPC requests."""
    try:
        body = await request.json()
    except Exception as exc:
        return JSONResponse(
            status_code=400,
            content={
                "jsonrpc": "2.0",
                "id": None,
                "error": {"code": -32700, "message": f"Parse error: {str(exc)}"},
            },
        )

    handler = get_mcp_handler(request)
    response = await handler.handle_request(body)

    if response is None:
        # Silent notification
        return Response(status_code=204)

    data = response.model_dump()
    if response.error is None and "error" in data:
        data.pop("error")
    if response.result is None and response.error is not None and "result" in data:
        data.pop("result")

    sessions = get_sessions(request)
    if sessionId and sessionId in sessions:
        queue = sessions[sessionId]
        sse_payload = f"event: message\ndata: {json.dumps(data)}\n\n"
        await queue.put(sse_payload)
        return JSONResponse(status_code=202, content={"status": "accepted"})

    # Direct response
    return JSONResponse(status_code=200, content=data)
