# Flash Framework Blog Example

A complete blog application demonstrating the Flash Framework - a Django-inspired web framework built on FastAPI.

## Features Demonstrated

- **FlashApp**: Framework wrapper around FastAPI for app setup
- **Class-Based Views**: Using TemplateView and DetailView from flash_html
- **Database Integration**: Flash DB ORM with async support
- **Permission System**: Custom permissions with object-level access control
- **Template Management**: Automatic template discovery and rendering

## Quick Start

### Prerequisites
- Python 3.12+
- uv package manager

### Running the Application

1. **From project root** (recommended):
   ```bash
   pymelos run example_one dev
   ```

2. **Directly from example_one directory**:
   ```bash
   cd apps/example_one
   uv run python main.py
   ```

3. **With uvicorn explicitly**:
   ```bash
   cd apps/example_one
   uv run uvicorn main:app --reload --host 0.0.0.0 --port 8000
   ```

Visit http://localhost:8000 to access the blog.

## Application Structure

```
apps/example_one/
├── main.py              # FlashApp entry point and route registration
├── views.py             # Class-based views using flash_html
├── models.py            # Database models using flash_db
├── permissions.py       # Custom permissions
├── templates/           # Jinja2 templates
│   ├── base.html       # Base template with styling
│   ├── about.html      # About page
│   ├── articles/       # Article-related templates
│   └── layout/         # Layout components
└── pyproject.toml       # Package configuration
```

## Key Patterns Demonstrated

### 1. Class-Based Views

```python
# TemplateView for static pages
class HomeView(TemplateView):
    template_name = "dashboard.html"

# DetailView for individual objects
class ArticleDetailView(DetailView[Article]):
    model = Article
    template_name = "articles/detail.html"
    permission_classes = [AllowAny]
```

### 2. URL Configuration

```python
# FlashApp routes using class-based views
app.add_view("/", HomeView)
app.add_view("/articles/{slug}", ArticleDetailView)
```

### 3. Database Models

```python
class Article(Model):
    __tablename__ = "example_articles"
    
    title: Mapped[str] = mapped_column()
    slug: Mapped[str] = mapped_column(unique=True)
    content: Mapped[str] = mapped_column()
```

### 4. Custom Permissions

```python
class ArticleOwnerPermission(BasePermission):
    async def has_object_permission(self, request, obj, user):
        return obj.author_id == user.id
```

## Available Routes

- `/` - Home page with recent articles
- `/login` - Login page
- `/register` - Register a new account
- `/logout` - Logout action
- `/articles/` - List all articles
- `/articles/new` - Create new article
- `/articles/{slug}` - View article details
- `/articles/{slug}/edit` - Edit article (owner only)
- `/about` - About page

## Development

### Running Tests
```bash
pymelos run test
```

### Linting and Formatting
```bash
pymelos run lint
pymelos run format
```

### Type Checking
```bash
pymelos run ty
```

## Database

The application uses SQLite with async support (`sqlite+aiosqlite:///blog.db`). 
The database file will be created automatically when you first run the application.

## Flash Framework Components Used

- **flash_web_framework**: FlashApp wrapper
- **flash_html**: TemplateView, DetailView, TemplateManager
- **flash_db**: Model base class, database operations
- **flash_authorization**: Permission system, BasePermission
- **flash_authentication**: User models and schemas (configured)

## Next Steps

This example demonstrates the core patterns of the Flash Framework. You can extend it by:

1. Adding user authentication and registration
2. Implementing comment functionality
3. Adding pagination for article lists
4. Creating admin interface for article management
5. Adding file upload support for article images

## Contributing

This is an example application for the Flash Framework. Feel free to experiment 
with the code and explore the framework's capabilities!
