from __future__ import annotations

import inspect
from typing import TYPE_CHECKING, Any, Awaitable, cast

from fastapi import Depends, Request, Response, status
from fastapi.responses import RedirectResponse

from flash_html.forms import BaseForm  # noqa: TC001

if TYPE_CHECKING:
    from flash_html.views.typing import TemplateContextProtocol


class FormMixin:
    """
    Form handling mixin for class-based views.

    This mixin is framework-agnostic and focuses on building, validating,
    and processing forms while leaving rendering to the view class.
    """

    form_class: type[BaseForm] | None = None
    success_url: str | None = None
    request: Request

    @classmethod
    def resolve_dependencies(
        cls,
        params: list[inspect.Parameter],
        **kwargs: Any,
    ) -> None:
        form_class = kwargs.get("form_class", cls.form_class)
        if form_class is not None and not any(p.name == "form" for p in params):
            params.insert(
                0,
                inspect.Parameter(
                    name="form",
                    kind=inspect.Parameter.POSITIONAL_OR_KEYWORD,
                    annotation=form_class,
                    default=Depends(form_class.as_form()),
                ),
            )

        super().resolve_dependencies(params, **kwargs)  # type: ignore[attr-defined]

    def get_form_class(self) -> type[BaseForm]:
        if self.form_class is None:
            msg = f"{self.__class__.__name__} is missing the required form_class."
            raise RuntimeError(msg)
        return self.form_class

    def get_initial(self) -> dict[str, Any]:
        return {}

    def get_form_kwargs(self) -> dict[str, Any]:
        view = cast("TemplateContextProtocol", self)
        return {
            "data": None,
            "files": None,
            "initial": self.get_initial(),
            "request": view.request,
        }

    def get_form(self, **kwargs: Any) -> BaseForm:
        form_class = self.get_form_class()
        form_kwargs = self.get_form_kwargs()
        form_kwargs.update(
            {key: value for key, value in kwargs.items() if value is not None}
        )
        return form_class(**form_kwargs)

    def get_success_url(self) -> str:
        if not self.success_url:
            msg = (
                f"{self.__class__.__name__} requires success_url "
                "or a custom form_valid() implementation."
            )
            raise RuntimeError(msg)
        return self.success_url

    async def form_valid(self, _form: BaseForm) -> Response:
        return RedirectResponse(
            url=self.get_success_url(),
            status_code=status.HTTP_303_SEE_OTHER,
        )

    async def form_invalid(self, form: BaseForm) -> Response:
        view = cast("TemplateContextProtocol", self)
        context = view.get_context_data(form=form)
        return view.render_to_response(context)


class ProcessFormView(FormMixin):
    """
    GET/POST handlers for form processing.

    Combine with TemplateView to render templates and with PermissionMixin
    or DatabaseMixin for access control and persistence.
    """

    async def get(self, **kwargs: Any) -> Response:
        view = cast("TemplateContextProtocol", self)
        form = self.get_form()
        context = view.get_context_data(form=form, **kwargs)
        return view.render_to_response(context)

    async def post(self, **_kwargs: Any) -> Response:
        view = cast("TemplateContextProtocol", self)
        form = getattr(self, "form", None)
        if form is None:
            form_data = await view.request.form()
            form = self.get_form(data=dict(form_data))
        if form.is_valid():
            return await self._maybe_await(self.form_valid(form))
        return await self._maybe_await(self.form_invalid(form))

    async def _maybe_await(self, result: Response | Awaitable[Response]) -> Response:
        if inspect.isawaitable(result):
            return await result
        return result
