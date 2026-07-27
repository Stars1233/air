import sys
from functools import wraps
from inspect import iscoroutinefunction
from typing import TYPE_CHECKING, Final, cast

from starlette.requests import Request
from starlette.responses import Response
from starlette.types import ASGIApp, HTTPExceptionHandler, Receive, Scope, Send

from .exceptions import HTTPException
from .layouts import mvpcss
from .responses import AirResponse
from .tags import H1, P, Title

if TYPE_CHECKING:
    from collections.abc import Callable


def default_404_router_handler(router_name: str) -> ASGIApp:
    """Build an ASGI app that delegates the 404 to the default_404_exception_handler.

    Returns:
        An ASGI application that handles 404 errors.

    Example:

        import air

        app = air.Air()
        router = air.AirRouter()


        @router.get("/example")
        def index() -> air.AirResponse:
            return air.AirResponse(air.P("I am an example route."), status_code=404)


        app.include_router(router)
    """

    async def app(scope: Scope, receive: Receive, send: Send) -> None:
        # Create a Request so router handler can render URL and other context.
        request: Request = Request(scope, receive=receive)

        # Use a concrete HTTPException (status 404). Your handler accepts Exception.
        exc: HTTPException = HTTPException(
            status_code=404,
            detail=f"Not Found in router '{router_name}'",
        )

        # Delegate to the project's default 404 renderer (AirResponse).
        response = default_404_exception_handler(request, exc)

        # AirResponse is a Starlette-compatible Response, so call it as ASGI.
        await response(scope, receive, send)

    return app


def default_404_exception_handler(request: Request, exc: Exception) -> AirResponse:
    """Default 404 exception handler. Can be overloaded.

    Returns:
        An AirResponse with a 404 status code and error page.

    Example:

        import air

        app = air.Air()


        @app.get("/")
        def index() -> air.AirResponse:
            return air.AirResponse(air.P("404 Not Found"), status_code=404)
    """
    return AirResponse(
        mvpcss(
            Title("404 Not Found"),
            H1("404 Not Found"),
            P("The requested resource was not found on this server."),
            P(f"URL: {request.url}"),
        ),
        status_code=404,
    )


def default_500_exception_handler(request: Request, exc: Exception) -> AirResponse:
    """Default 500 exception handler. Can be overloaded.

    Returns:
        An AirResponse with a 500 status code and error page.

    Example:

        import air

        app = air.Air()


        @app.get("/")
        def index() -> air.AirResponse:
            return air.AirResponse(air.P("500 Internal Server Error"), status_code=500)
    """
    return AirResponse(
        mvpcss(
            Title("500 Internal Server Error"),
            H1("500 Internal Server Error"),
            P("An internal server error occurred."),
        ),
        status_code=500,
    )


def _threads_available() -> bool:
    """Return whether exception handlers can be dispatched to worker threads."""
    return sys.platform != "emscripten"


def adapt_exception_handler(handler: HTTPExceptionHandler) -> HTTPExceptionHandler:
    """Wrap a synchronous handler for runtimes without worker threads."""
    if _threads_available() or iscoroutinefunction(handler) or iscoroutinefunction(handler.__call__):
        return handler

    sync_handler = cast("Callable[[Request, Exception], Response]", handler)

    @wraps(sync_handler)
    async def async_handler(request: Request, exc: Exception) -> Response:
        return sync_handler(request, exc)

    return async_handler


def adapt_exception_handlers[Key](
    handlers: dict[Key, HTTPExceptionHandler],
) -> dict[Key, HTTPExceptionHandler]:
    """Adapt each handler without capturing a loop variable in its wrapper."""
    return {
        key: adapt_exception_handler(handler)
        for key, handler in handlers.items()
    }


type ExceptionHandlersType = dict[int | type[Exception], HTTPExceptionHandler]
DEFAULT_EXCEPTION_HANDLERS: Final[ExceptionHandlersType] = {
    404: default_404_exception_handler,
    500: default_500_exception_handler,
}
