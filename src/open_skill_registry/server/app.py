import uuid
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException

from open_skill_registry.config import RegistryConfig
from open_skill_registry.server.db.session import close_db, init_db
from open_skill_registry.server.routes import health
from open_skill_registry.server.services.cache_service import CacheService


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup
    await init_db()
    # Assuming config is in app.state
    cache_config = getattr(app.state.config, "cache", None) if hasattr(app.state, "config") else None
    
    app.state.cache_service = CacheService(config=cache_config)
    yield
    # Shutdown
    await close_db()

def create_app(config: RegistryConfig | None = None) -> FastAPI:
    if config is None:
        config = RegistryConfig.load()

    app = FastAPI(
        title="Open Skill Registry",
        lifespan=lifespan
    )
    
    app.state.config = config

    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    @app.middleware("http")
    async def request_id_middleware(request: Request, call_next):
        request_id = request.headers.get("X-Request-Id") or str(uuid.uuid4())
        response = await call_next(request)
        response.headers["X-Request-Id"] = request_id
        return response

    @app.exception_handler(StarletteHTTPException)
    async def http_exception_handler(request: Request, exc: StarletteHTTPException):
        return JSONResponse(
            status_code=exc.status_code,
            content={
                "code": exc.status_code,
                "error": str(exc.detail),
                "data": None
            }
        )

    @app.exception_handler(RequestValidationError)
    async def validation_exception_handler(request: Request, exc: RequestValidationError):
        return JSONResponse(
            status_code=422,
            content={
                "code": 422,
                "error": "Validation error",
                "data": {"errors": exc.errors()}
            }
        )

    @app.exception_handler(Exception)
    async def generic_exception_handler(request: Request, exc: Exception):
        return JSONResponse(
            status_code=500,
            content={
                "code": 500,
                "error": "Internal server error",
                "data": None
            }
        )

    app.include_router(health.router)
    app.include_router(health.router, prefix="/api/v1")

    return app
