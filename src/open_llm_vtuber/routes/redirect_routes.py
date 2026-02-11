"""Redirect routes for web tool paths."""

from fastapi import APIRouter, Response


def init_redirect_routes() -> APIRouter:
    """
    Create routes for handling web tool redirects.

    Returns:
        APIRouter: Router with redirect endpoints.
    """
    router = APIRouter()

    @router.get("/web-tool")
    async def web_tool_redirect():
        """Redirect /web-tool to /web-tool/index.html"""
        return Response(status_code=302, headers={"Location": "/web-tool/index.html"})

    @router.get("/web_tool")
    async def web_tool_redirect_alt():
        """Redirect /web_tool to /web-tool/index.html"""
        return Response(status_code=302, headers={"Location": "/web-tool/index.html"})

    return router
