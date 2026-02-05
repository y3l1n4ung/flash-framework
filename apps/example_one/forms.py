from __future__ import annotations

from flash_html.forms import (
    BaseForm,
    BooleanField,
    CharField,
    ChoiceField,
    EmailField,
    IntegerField,
    TextAreaField,
    URLField,
)
from pydantic import BaseModel


class ArticleFormData(BaseModel):
    title: str
    slug: str
    content: str
    published: bool = False


class ArticleForm(BaseForm[ArticleFormData]):
    title = CharField(
        required=True,
        min_length=3,
        max_length=120,
        description="Article title",
        form_kwargs={"alias": "title"},
    )
    slug = CharField(
        required=True,
        min_length=3,
        max_length=120,
        description="Article slug",
        form_kwargs={"alias": "slug"},
    )
    content = CharField(
        required=True,
        min_length=10,
        description="Article content",
        form_kwargs={"alias": "content"},
    )
    published = BooleanField(required=False)
    pydantic_model = ArticleFormData


class LoginForm(BaseForm):
    username = CharField(
        required=True,
        min_length=1,
        max_length=150,
        placeholder="Your username",
        input_type="text",
        attrs={"autocomplete": "username"},
    )
    password = CharField(
        required=True,
        min_length=1,
        placeholder="Your password",
        input_type="password",
        attrs={"autocomplete": "current-password"},
    )
    next = CharField(
        required=False,
        input_type="hidden",
    )


class RegisterForm(BaseForm):
    username = CharField(
        required=True,
        min_length=2,
        max_length=150,
        placeholder="Choose a username",
        input_type="text",
        attrs={"autocomplete": "username"},
    )
    email = EmailField(
        required=False,
        placeholder="you@example.com",
        attrs={"autocomplete": "email"},
    )
    password = CharField(
        required=True,
        min_length=8,
        placeholder="Create a strong password",
        help_text="At least 8 characters.",
        input_type="password",
        attrs={"autocomplete": "new-password"},
    )
    confirm_password = CharField(
        required=True,
        min_length=8,
        placeholder="Repeat your password",
        input_type="password",
        attrs={"autocomplete": "new-password"},
    )

    def clean(self):
        password = self.cleaned_data.get("password", "")
        confirm = self.cleaned_data.get("confirm_password", "")
        if password and confirm and password != confirm:
            self.add_error("confirm_password", "Passwords do not match.")
        if password and len(password) < 8:
            self.add_error("password", "Password must be at least 8 characters.")


class ProfileForm(BaseForm):
    display_name = CharField(
        required=True,
        min_length=2,
        max_length=50,
        placeholder="Your public name",
        help_text="Shown on your profile.",
    )
    email = EmailField(required=True, placeholder="you@example.com")
    website = URLField(
        required=False,
        placeholder="https://your-site.com",
        help_text="Optional personal site.",
    )
    role = ChoiceField(
        required=True,
        choices=[("writer", "Writer"), ("editor", "Editor"), ("reader", "Reader")],
    )
    experience_years = IntegerField(
        required=False,
        min_value=0,
        max_value=40,
        help_text="How long have you been writing?",
    )
    bio = TextAreaField(
        required=False,
        placeholder="Share a short bio...",
        attrs={"rows": 5},
    )
    newsletter = BooleanField(required=False)
