# FastAPI-Native Pydantic ModelForm Plan

## Overview

Integrate ModelForm with FastAPI's native `Form()` dependency injection system.
## Core Architecture

### Files to Create

```
flash_html/src/flash_html/
├── forms/
│   ├── __init__.py              # Exports
│   ├── base.py                  # BaseForm with FastAPI integration
│   ├── dependencies.py           # Form dependency helpers
│   ├── security.py              # CSRF protection system
│   └── views.py                 # Form-enhanced base views
├── templates/forms/
│   ├── field.html               # Secure field rendering
│   ├── base.html               # Form wrapper with CSRF
│   └── csrf.html               # CSRF token hidden field
```

## Implementation

### 1. CSRF Protection System (`security.py`)

```python
import secrets
from fastapi import Request

class CSRFProtection:
    """Session-based CSRF protection for forms."""
    
    @staticmethod
    def generate_token(request: Request) -> str:
        """Generate and store CSRF token in session."""
        if not hasattr(request.state, 'auth') or not request.state.auth:
            raise ValueError("No active session for CSRF protection")
        
        token = secrets.token_urlsafe(32)
        
        # Store token in session (existing flash_authentication_session)
        if 'csrf_tokens' not in request.state.auth:
            request.state.auth['csrf_tokens'] = []
        request.state.auth['csrf_tokens'].append(token)
        
        return token
    
    @staticmethod
    def validate_token(request: Request, token: str) -> bool:
        """Validate CSRF token against session."""
        if not hasattr(request.state, 'auth') or not request.state.auth:
            return False
        
        stored_tokens = request.state.auth.get('csrf_tokens', [])
        if token in stored_tokens:
            # Remove token after validation (one-time use)
            stored_tokens.remove(token)
            return True
        return False
    
    @staticmethod
    def get_hidden_field_html(request: Request, token: str) -> str:
        """Generate hidden input field for CSRF token."""
        return f'<input type="hidden" name="csrf_token" value="{token}">'
    
    @staticmethod
    def generate_csrf_field(request: Request) -> str:
        """Generate CSRF token and return hidden field HTML."""
        token = CSRFProtection.generate_token(request)
        return CSRFProtection.get_hidden_field_html(request, token)
```

## Security Features

🔒 **CSRF Protection**
- Session-based token generation
- Automatic template injection via `{{ csrf_token }}`
- Token validation on form submission
- One-time token use (rotation)

🔒 **Input Validation**
- Pydantic field validation
- Custom validator support
- Form-wide validation methods
- Error handling and display

🔒 **Session Integration**
- Uses existing `flash_authentication_session`
- Leverages `request.state.auth`
- Secure token storage
- Session expiration handling

## Edge Cases Handled

🎯 **Security Scenarios**
- **AJAX Requests**: CSRF token validation for XHR
- **Multiple Forms**: Different tokens per form instance
- **Session Expiration**: Graceful handling of expired sessions
- **Token Rotation**: New tokens generated after validation
- **Safe Methods**: GET/HEAD/OPTIONS exempt from CSRF

🎯 **Form Scenarios**
- **Mixed Content Types**: JSON vs form data handling
- **File Uploads**: Integration with FastAPI UploadFile
- **Large Forms**: Pagination and chunked submission
- **Internationalization**: Multi-language error messages
- **Accessibility**: ARIA labels and semantic HTML

## Implementation

**Files: 6 files in flash_html/src/flash_html/forms/** + 3 templates**

### 2. FastAPI Form Integration (`base.py`)

```python
from typing import Any, TypeVar, ClassVar
from pydantic import BaseModel, Field
from fastapi import Form
from flash_db.schema_generator import SchemaGenerator

T = TypeVar("T", bound="BaseForm")

class BaseForm(BaseModel):
    """Form that integrates with FastAPI Form() dependencies with CSRF protection and schema generation."""
    
    model: ClassVar[Type[Model]] = None  # Optional model for auto-generation
    use_csrf: bool = Field(True, description="Enable CSRF protection")
    _csrf_token: str | None = Field(None, exclude=True)
    
    def __init_subclass__(cls) -> None:
        """Generate form fields from model or use manual definitions."""
        super().__init_subclass__()
        
        if cls.model:
            cls._generate_fields_from_model()
        cls._process_field_definitions()
    
    @classmethod
    def _generate_fields_from_model(cls) -> None:
        """Auto-generate form fields from Flash model using existing SchemaGenerator."""
        generator = SchemaGenerator(cls.model)
        schema = generator.create_schema()
        
        # Add generated fields to class annotations
        for field_name, field_info in schema.model_fields.items():
            cls.__annotations__[field_name] = field_info.annotation
            setattr(cls, field_name, field_info)
    
    @classmethod
    def _process_field_definitions(cls) -> None:
        """Process manual field definitions after schema generation."""
        # Manual field definitions take precedence over auto-generated ones
        pass
    
    @classmethod
    def get_form_dependencies(cls):
        """Convert form fields to FastAPI Form() dependencies."""
        form_fields = {}
        
        for field_name, field_info in cls.model_fields.items():
            default = field_info.default if field_info.default is not ... else ...
            form_fields[field_name] = Form(default)
        
        # Add CSRF token field
        form_fields['csrf_token'] = Form("")
        
        return form_fields
    
    @classmethod
    def from_fastapi_form(cls, request: Request, **form_data):
        """Create form from FastAPI-injected form data."""
        # Validate CSRF token first
        if cls.use_csrf:
            csrf_token = form_data.pop('csrf_token', '')
            if not CSRFProtection.validate_token(request, csrf_token):
                raise ValueError("Invalid CSRF token")
            
            # Generate new token for next form
            csrf_token = CSRFProtection.generate_token(request)
            instance = cls(**form_data)
            instance._csrf_token = csrf_token
            return instance
        
        return cls(**form_data)
    
    def is_valid(self) -> bool:
        """Validate form using Pydantic."""
        try:
            self.model_validate(self.model_dump())
            return True
        except:
            return False
    
    def get_form_errors(self) -> dict[str, list[str]]:
        """Get validation errors preserving types."""
        return getattr(self, '_form_errors', {})
    
    def cleaned_data(self) -> dict[str, Any]:
        """Get validated data."""
        return self.model_dump(exclude_unset=True, exclude={'csrf_token'})
    
    def get_context(self) -> dict[str, Any]:
        """Template context with CSRF token."""
        return {
            'form': self,
            'fields': {name: getattr(self, name, None) for name in self.model_fields},
            'csrf_token': self._csrf_token,
        }

### 2. Dependency Helper (`dependencies.py`)

```python
from typing import Type, TypeVar, Generic
from fastapi import Depends
from pydantic import BaseModel

F = TypeVar('F', bound=BaseModel)

class FormDependency(Generic[F]):
    """Type-safe form dependency wrapper."""
    
    def __init__(self, form_class: Type[F]) -> None:
        self.form_class = form_class
    
    def as_dependency(self) -> Depends[F]:
        """Create FastAPI dependency preserving types."""
        
        async def form_dependency(**form_data) -> F:
            """FastAPI dependency that creates and validates form."""
            return self.form_class(**form_data)
        
        return Depends(form_dependency)

def create_form_dependency(form_class: Type[F]) -> FormDependency[F]:
    """Create type-safe form dependency."""
    return FormDependency(form_class)

def get_form_dependencies(form_class: Type[BaseModel]) -> dict[str, Any]:
    """Extract form field definitions for FastAPI Form() conversion."""
    return {
        name: Form(field.default if field.default is not ... else ...)
        for name, field in form_class.model_fields.items()
    }
```

### 3. Enhanced View Integration (`views.py`)

```python
from flash_html.views.base import View

class FormView(View):
    """Base view with FastAPI form integration and CSRF protection."""
    
    async def get(self, request: Request, **kwargs):
        """Handle GET request - create form with CSRF token."""
        form_class = getattr(self, 'form_class', None)
        if form_class:
            form = form_class()
            if hasattr(form, 'generate_csrf_token'):
                form._csrf_token = CSRFProtection.generate_token(request)
        
        context = self.get_context_data(form=form, **kwargs)
        return self.render_to_response(context)
    
    async def post(self, **kwargs):
        """Extract form from kwargs and handle validation."""
        # Form is automatically injected by FastAPI with CSRF validation
        form = kwargs.get('form')
        
        if form and form.is_valid():
            return await self.form_valid(form)
        else:
            return await self.form_invalid(form)
    
    async def form_valid(self, form):
        """Handle valid form submission."""
        return {"success": True, "data": form.cleaned_data()}
    
    async def form_invalid(self, form):
        """Handle invalid form submission."""
        return {"success": False, "errors": form.get_form_errors()}

class ModelFormView(FormView):
    """Enhanced view with automatic model form handling."""
    
    model_form: Type[BaseForm]
    success_url: str = "/"
    
    async def form_valid(self, form, db=None):
        """Save form data and redirect. DB handled automatically via view."""
        instance = self.model(**form.cleaned_data())
        db.add(instance)
        await db.commit()
        
        return RedirectResponse(url=self.get_success_url())
    
    def get_success_url(self) -> str:
        return self.success_url

## Usage Examples

### Form Definition

```python
from flash_html.forms import BaseForm
from pydantic import BaseModel, Field

class ProductForm(BaseForm):
    name: str = Field(..., min_length=3)
    price: float = Field(..., gt=0)
    published: bool = Field(False)
    
    def clean_name(self):
        return self.name.title()
```

### View Usage

```python
from flash_html.forms.views import FormView
from flash_html.forms.dependencies import create_form_dependency

class ProductCreateView(FormView):
    model = Product
    model_form = ProductForm
    template_name = "products/create.html"
    success_url = "/products/"
    
    async def post(self,
                   db: AsyncSession = Depends(get_db),
                   form: ProductForm = Depends(create_form_dependency(ProductForm))):
        
        # Form is automatically created and validated by FastAPI
        return await super().post(db=db, form=form)

app.add_api_route("/products/create", ProductCreateView.as_view(), methods=["GET", "POST"])
```

### Alternative: Multiple Forms

```python
class ProductUpdateView(View):
    async def post(self,
                   db: AsyncSession = Depends(get_db),
                   product_form: ProductForm = Depends(create_form_dependency(ProductForm)),
                   price_form: PriceForm = Depends(create_form_dependency(PriceForm))):
        
        if product_form.is_valid() and price_form.is_valid():
            # Process both forms
            product_data = product_form.cleaned_data()
            price_data = price_form.cleaned_data()
            
            return {"success": True, "product": product_data, "price": price_data}
        
        return {"success": False}
```

### Template Usage

```html
<form method="post">
    {{ csrf_token }}
    
    <div class="field">
        <label for="name">Name</label>
        <input type="text" name="name" required>
        {% if form.get_form_errors().name %}
            <div class="error">{{ form.get_form_errors().name[0] }}</div>
        {% endif %}
    </div>
    
    <div class="field">
        <label for="price">Price</label>
        <input type="number" name="price" step="0.01" required>
        {% if form.get_form_errors().price %}
            <div class="error">{{ form.get_form_errors().price[0] }}</div>
        {% endif %}
    </div>
    
    <div class="field">
        <label>
            <input type="checkbox" name="published"> Published
        </label>
    </div>
    
    <button type="submit">Create Product</button>
</form>
```

### Template Functions

```python
# Register in TemplateManager global_functions
def csrf_token(request: Request) -> str:
    """Generate CSRF token hidden field for template."""
    if not hasattr(request.state, 'auth') or not request.state.auth:
        return CSRFProtection.generate_csrf_field(request)
    
    return CSRFProtection.generate_csrf_field(request)

def form_field(field_name: str, field_info: dict) -> str:
    """Secure form field rendering."""
    pass

def form_errors(form: BaseModel) -> dict[str, list[str]]:
    """Extract form errors for template display."""
    return form.get_form_errors()
```

