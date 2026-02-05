from __future__ import annotations

from typing import TYPE_CHECKING, Any, Protocol

if TYPE_CHECKING:
    from fastapi import Request, Response


class TemplateContextProtocol(Protocol):
    request: "Request"

    def get_context_data(self, **kwargs: Any) -> dict[str, Any]: ...

    def render_to_response(
        self, context: dict[str, Any], **kwargs: Any
    ) -> "Response": ...
