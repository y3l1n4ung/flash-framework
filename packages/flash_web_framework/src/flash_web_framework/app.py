from __future__ import annotations

from typing import TYPE_CHECKING, Any, Callable, Iterable, Sequence

from fastapi import FastAPI
from flash_html.template_manager import TemplateManager

if TYPE_CHECKING:
    from pathlib import Path

    from flash_html.views import View


class FlashApp(FastAPI):
    """
    Flash Framework application wrapper for FastAPI.

    Provides convenience helpers for template setup and class-based view routing
    so example apps can depend only on Flash packages.
    """

    def __init__(
        self,
        *,
        project_root: Path | str | None = None,
        template_directories: Sequence[Path | str] | None = None,
        template_context: dict[str, Any] | None = None,
        template_functions: dict[str, Callable] | None = None,
        **kwargs: Any,
    ) -> None:
        super().__init__(**kwargs)

        if (
            project_root
            or template_directories
            or template_context
            or template_functions
        ):
            self.configure_templates(
                project_root=project_root,
                template_directories=template_directories,
                template_context=template_context,
                template_functions=template_functions,
            )

    def configure_templates(
        self,
        *,
        project_root: Path | str | None = None,
        template_directories: Sequence[Path | str] | None = None,
        template_context: dict[str, Any] | None = None,
        template_functions: dict[str, Callable] | None = None,
    ) -> TemplateManager:
        manager = TemplateManager(
            project_root=project_root,
            extra_directories=template_directories,
            global_context=template_context,
            global_functions=template_functions,
        )
        self.state.template_manager = manager
        return manager

    def add_view(
        self,
        path: str,
        view: type[View],
        *,
        name: str | None = None,
        methods: Iterable[str] | None = None,
        **initkwargs: Any,
    ) -> None:
        resolved_methods = list(methods or self._resolve_view_methods(view))
        if not resolved_methods:
            msg = f"No HTTP methods declared for view {view.__name__}."
            raise ValueError(msg)
        for method in resolved_methods:
            handler = view.as_view(method=method, **initkwargs)
            route_name = f"{name}_{method.lower()}" if name else None
            self.add_api_route(path, handler, name=route_name, methods=[method])

    @staticmethod
    def _resolve_view_methods(view: type[View]) -> list[str]:
        resolved: list[str] = []
        for method_name in view.http_method_names:
            handler = getattr(view, method_name, None)
            if handler is None:
                continue
            if handler.__name__ == "http_method_not_allowed":
                continue
            resolved.append(method_name.upper())
        return resolved


__all__ = ["FlashApp"]
