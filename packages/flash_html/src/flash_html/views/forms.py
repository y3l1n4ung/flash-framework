"""
FormView implementation.

Keep form processing logic in mixins and compose with TemplateView for rendering.
"""

from flash_html.views.generic.base import TemplateView
from flash_html.views.mixins.form import ProcessFormView


class FormView(ProcessFormView, TemplateView):
    """Template-backed view for form display and submission."""
