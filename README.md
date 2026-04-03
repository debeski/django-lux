# Django microSYS - System Integration Service

[![PyPI version](https://badge.fury.io/py/django-microsys.svg)](https://pypi.org/project/django-microsys/)

<p align="center">
  <img src="https://raw.githubusercontent.com/debeski/django-microsys/main/microsys/static/img/login_logo.webp" alt="microSys Logo" width="450"/>
</p>

<center>**Multilingual** lightweight, dynamic Django app providing a comprehensive, highly customizable system integration service, including user management, profile extension, permissions, language switching, dynamic sidebar, automated activity logging, dynamic auxiliary model detection, global autofill feature and more.</center>

---

## 📋 Requirements
- Python 3.11+
- Django 5.1.4+
- django-crispy-forms 2.3+
- crispy-bootstrap5 2025.3+
- django-tables2 2.5+
- django-filter 24.1+
- psutil
- pyotp
- qrcode

---

## 🚀 Installation

```bash
pip install git+https://github.com/debeski/django-microsys.git
# OR
pip install django-microsys
```

---

## ⚙️ Quick Start & Configuration

1. **Add to `INSTALLED_APPS`:**
   ```python
   INSTALLED_APPS = [
       'django.contrib.admin',
       'django.contrib.auth',
       # ... dependencies
       'crispy_forms',
       'crispy_bootstrap5',
       'django_filters',
       'django_tables2',

       'microsys', # Place anywhere.
   ]
   ```

2. **Add Middleware:**
   Required for activity logging and request caching.
   ```python
   MIDDLEWARE = [
       # ...
       'django.contrib.auth.middleware.AuthenticationMiddleware',
       # ... Must be below Auth Middleware
       'microsys.middleware.ActivityLogMiddleware',
   ]
   ```

3. **Add Context Processor:**
   Unified context processor for branding, sidebar config, scope settings, auto-fill, and more.
   ```python
   TEMPLATES = [
       {
           # ...
           'OPTIONS': {
               'context_processors': [
                   # ...
                   'microsys.context_processors.microsys_context',
               ],
           },
       },
   ]
   ```

4. **Include URLs:**
   Mount at **root** for seamless Django auth integration:
   ```python
   from django.urls import path, include

   urlpatterns = [
       # ...
       path('', include('microsys.urls')),  # Mount at root
   ]
   ```
   
   This provides:
   - `/accounts/login/` and `/accounts/logout/` (Django defaults)
   - `/sys/` for all system management routes

   > ⚠️ **Warning:** If your project already uses `/accounts/` URLs (e.g., `django-allauth`), you'll have conflicts. In that case, mount with a prefix and configure custom auth URLs:
   > ```python
   > # urls.py
   > path('microsys/', include('microsys.urls')),
   > 
   > # settings.py
   > LOGIN_URL = '/microsys/accounts/login/'
   > LOGIN_REDIRECT_URL = '/microsys/sys/'
   > LOGOUT_REDIRECT_URL = '/microsys/accounts/login/'
   > ```

5. **Run Setup Command:**
   ```bash
   python manage.py microsys_setup
   ```
   This will create migrations, apply them, and validate your configuration.

---

### 🛠️ Management Commands

- `microsys_setup`
Initial setup command that handles migrations and configuration validation.

```bash
# Full setup (recommended for first install)
python manage.py microsys_setup

# Skip configuration check
python manage.py microsys_setup --skip-check

# Only validate config (skip migrations)
python manage.py microsys_setup --no-migrate
```

- `microsys_check`
Validates your Django settings and shows exact code snippets for any missing configuration.

```bash
python manage.py microsys_check
```

**Output example:**
```
🔍 MicroSys Configuration Check
==================================================

📋 INSTALLED_APPS: ✓ OK
📋 MIDDLEWARE: ✗ MISSING
📋 CONTEXT_PROCESSORS: ✓ OK
📋 URLS: ✓ OK
📋 CRISPY_FORMS: ✓ OK

==================================================
❌ REQUIRED CONFIGURATION MISSING:

▶ MIDDLEWARE:

MIDDLEWARE = [
    # ... after AuthenticationMiddleware
    'microsys.middleware.ActivityLogMiddleware',
]
```

> **Note:** microsys also validates your configuration at runtime and will emit warnings if required middleware or context processors are missing.

---

### 🖥️ App Configuration

Customize branding, the global Home URL, default theme, default languages, and translation overrides directly from the **App Options** UI for Superusers. On a fresh install, superusers are guided through a dedicated first-launch setup wizard at `/sys/setup/`, and the same settings remain editable afterward from the Options modal.

Under the hood, microsys uses a database-backed **SystemSettings** singleton model (`microsys.models.SystemSettings`). This means NO manual configuration in `settings.py` is needed, and any changes apply instantly via cache.

```python
# Auth redirects
# 1. 'next' query param (highest priority)
# 2. LOGIN_REDIRECT_URL in settings (if set)
# 3. SystemSettings.home_url (configured in UI)
# 4. '/sys/' (default fallback)
LOGIN_REDIRECT_URL = '/sys/' 
LOGOUT_REDIRECT_URL = '/accounts/login/'
```

---

## ✨ Features:
- **System Integration**: Centralized management for users, permissions and system scopes.
- **Profile Extension**: Automatically links a `Profile` to your existing User model.
- **Scope Management**: Optional, dynamic scope isolation system with abstract `ScopedModel`.
- **Permissions**: Custom grouped permission UI (App/Model/Action) with dynamic multi-language translation for permission prefixes.
- **User Detail View**: Detailed page for user profile, activity, and last login.
- **Dynamic Auxiliary Model Detection**: Zero-Boilerplate Zero-Code Detection of auxiliary models using model attrs.
- **Dynamic Forms, Filters and Tables**: Automatically detects and registers or creates forms, filters and tables to auxiliary models.
- **Dynamic Modal Manager**: Universal AJAX-driven modal system for managing any model with a combined List + Form UI.
- **Global Autofill**: Dynamic Smart Autofill tool that fills form fields based on related FK models, or model last entry.
- **Universal Fetcher**: Global, Smart single-file and multi-file Downloader, and data-driven Excel Exporter for querysets.
- **Automated Logging**: Full automatic activity tracking (CRUD, Login/Logout) via Signals with **Detailed Diff Tracking** and **Smart Deduplication**.
- **Dynamic Sidebar**: Auto-discovery of list views and customizable, reorderable menu items.
- **Dynamic Titlebar**: Show-Hide autofill-toggle, dynamic home url, and title.
- **Context Menu**: Easy to use context menu for quick actions.
- **Two-Factor Authentication**: Email OTP and TOTP Authenticator App support with backup codes.
- **Options View**: Options view to enable, disable, and configure system features and details.
- **Dynamic Translation Framework**: Intelligent zero-boilerplate translation with robust cascading fallbacks (defaults to English), transparent database content translation via `TranslationMixin`, `gettext` hijacking, and native JS client-side localization.
- **Modern Dashboard UI**: Sleek, glass-like module cards with cascading entrance animations and an admin-exclusive System Setup shortcut.
- **Themes & Accessibility**: Bootstrap5 integration with built-in dark/light modes and accessibility tools (High Contrast, Zoom, etc.).
- **Native Mobile Support**: Responsive design for all screen sizes.
- **Management Commands**: Built-in management commands for system setup and checks.
- **Tutorial**: Built-in help/tutorial for microSYS views and features.
- **Security**: CSP compliance, role-based access control (RBAC), Backend A&A enforcement, and Global **Double-Submit Prevention**.

---

### 👤 User Management

1. Profile Access
`microsys` automatically creates a `Profile` for every user via a `post_save` signal — no manual creation needed.
```python
# Accessing profile data
phone = user.profile.phone
scope = user.profile.scope
preferences = user.profile.preferences  # JSONField dict
is_2fa = user.profile.is_2fa_enabled    # Property
```

2. Grouped Permissions
Microsys provides a custom, intuitive UI for managing permissions. Permissions are automatically grouped by **Application**, **Model**, and **Action** (View, Add, Change, Delete), making it easy to manage complex access controls.

**Programmatic Permission Filtering:**
You can dynamically filter UI actions based on user permissions using the `filter_context_actions` helper.
```python
from microsys.utils import filter_context_actions

def my_view(request):
    actions = [
        {"label": "View", "url": "/view/"}, 
        {"label": "Edit", "url": "/edit/", "permissions": ["storage.change_asset"]}, 
    ]
    # Only keeps the "Edit" button if the user has the 'change_asset' permission
    safe_actions = filter_context_actions(request.user, actions)
```

3. Automated Activity Logging
Every action (CRUD, Login/Logout, etc.) is automatically recorded in the `UserActivityLog`.
- **Global Middleware**: Tracks IP address and User Agent via thread-local storage.
- **Signal-Based**: Captures changes even from the Django Admin.
- **Detailed Diffs**: Logs specific field changes as JSON (e.g., `{"phone": {"old": "123", "new": "456"}}`) and masked password updates.
- **Smart Merging**: Concurrent updates to `User` and `Profile` are intelligently merged into a single "User Update" log entry to reduce noise.
- **Searchable**: View and filter activity logs directly from the system dashboard.
- **Deduplication**: `UserActivityLog.safe_log()` prevents duplicate entries within a 2-second window.

4. Interactive User Wizard
User management in dynamic modals now features a sleek 2-step interactive wizard:
- **Step 1: Account Details**: Captures core credentials, profile information, and conditional scope assignment.
- **Step 2: Permissions**: Interactive grouped permission selection with master-toggle support for applications and models.

5. Dynamic Permission Translation
The system automatically translates standard Django permission prefixes (Add, Change, Delete, View) into the active language, providing a completely localized experience for non-English speakers.

**Accessing Middleware Context:**
Use these helpers to grab the active user or request anywhere (e.g., in `save()` or signals):
```python
from microsys.middleware import get_current_user, get_current_request

class Asset(ScopedModel):
    def save(self, *args, **kwargs):
        user = get_current_user()
        if user and user.is_authenticated:
            self.last_modified_by = user
        super().save(*args, **kwargs)
```

**Manual Logging:**
The `log_user_action` helper is the primary way to maintain an audit trail. It automatically extracts metadata (PK, verbose name) and client context.
```python
from microsys.utils import log_user_action

def my_view(request, pk):
    asset = Asset.objects.get(pk=pk)
    # Perform some logic...
    log_user_action(request, 'MAINTENANCE_LOG', instance=asset, details={'notes': 'Oil changed'})
```

> **Note**: Sensitive fields (`password`, `backup_codes`, `token`, `secret`) are automatically masked as `********` in log details.

4. Unified Preferences
User UI settings (Theme, Language, Sidebar State, Autofill status) are persisted in the database (`Profile.preferences`), ensuring a consistent experience across different browsers and devices.

---

### 🔐 Two-Factor Authentication (2FA)

microsys includes built-in Two-Factor Authentication with multiple methods.

- **Supported Methods**

| Method | How It Works |
|---|---|
| **Email OTP** | Sends a 6-digit code to the user's email address |
| **TOTP App** | Generates time-based codes via authenticator apps (Google Authenticator, Authy, etc.) |
| **Backup Codes** | 10 one-time recovery codes for account recovery |

- **How It Works**
  - Users enable/disable 2FA methods from their **Profile** page.
  - When **Email OTP** is enabled, the system sends a verification code on login.
  - When **TOTP** is enabled, the system shows a QR code that the user scans with their authenticator app.
  - **Backup codes** can be generated as a fallback if the primary method is unavailable.
  - 2FA status is stored in the `Profile` model (`is_email_2fa_enabled`, `is_totp_2fa_enabled`).

- **URL Routes**

| Route | Purpose |
|---|---|
| `/sys/2fa/enable/?method=email` | Start enabling Email 2FA |
| `/sys/2fa/setup/totp/` | Generate TOTP secret + QR code |
| `/sys/2fa/verify/login/` | Verify OTP during login |
| `/sys/2fa/verify/enable/` | Verify OTP to confirm method activation |
| `/sys/2fa/disable/` | Disable a 2FA method |
| `/sys/2fa/backup-codes/generate/` | Generate new backup codes |
| `/sys/2fa/resend/<intent>/` | Resend OTP code |

> **Note**: Email-based 2FA requires a configured `EMAIL_BACKEND` in your Django settings.

---

### 🏗️ Core Integration (ScopedModel)

The foundation of the Microsys ecosystem is the `ScopedModel`. By inheriting from this abstract base, your models immediately gain advanced system features that ensure seamless integration with the dashboard and auxiliary management tools:

```python
from microsys.models import ScopedModel

class MyModel(ScopedModel):
    name = models.CharField(...)
    # ... your fields
```

That's it. Your model now has:

| Built-in Field | Type | Behavior |
|---|---|---|
| `scope` | ScopeForeignKey | Auto-hidden from forms when scopes are disabled |
| `created_at` | DateTimeField | Auto-set on creation (`auto_now_add`) |
| `updated_at` | DateTimeField | Auto-set on every save (`auto_now`) |
| `created_by` | ForeignKey(User) | Auto-populated from current user via middleware |
| `updated_by` | ForeignKey(User) | Auto-populated from current user via middleware |
| `deleted_at` | DateTimeField | Set automatically when `delete()` is called |
| `deleted_by` | ForeignKey(User) | Auto-populated from current user on delete |

> **All audit fields are `editable=False`** — they are automatically excluded from ModelForms, including auto-generated Section and Modal forms. No `form_exclude` needed.

- **Zero-Config Audit Trail**
All 4 actor fields (`created_by`, `updated_by`, `deleted_by`) are **auto-populated** from the current user via the `ActivityLogMiddleware` thread-local. No manual assignment is needed in views:
```python
# These are set AUTOMATICALLY by ScopedModel.save() — no code needed:
instance.created_by   # set on first save
instance.updated_by   # set on every save
instance.deleted_by   # set on delete()
```

- **Global Soft-Delete**
Every call to `instance.delete()` on a ScopedModel performs a **soft-delete** (sets `deleted_at` + `deleted_by`). The row is never removed from the database:
```python
record.delete()            # Soft-delete (sets deleted_at, auto-detects user)
record.soft_delete()       # Alias for delete()
record.restore()           # Undo soft-delete (clears deleted_at + deleted_by)
record.hard_delete()       # PERMANENT removal (escape hatch)
```

- **Dual Managers**

| Manager | Behavior |
|---|---|
| `MyModel.objects` | Default. Filters by user scope + hides soft-deleted records |
| `MyModel.all_objects` | Raw Django manager — **no** scope or soft-delete filtering |

```python
# Normal use (scope-aware, hides deleted)
MyModel.objects.all()

# Admin/migration scripts (bypass all filtering)
MyModel.all_objects.filter(deleted_at__isnull=False)  # see soft-deleted records
```

- **ScopeForeignKey**

`ScopedModel` uses `ScopeForeignKey` for its scope field. This is a standard `ForeignKey` that **automatically hides itself** from ModelForms when the Scope system is globally disabled — no conditional form logic needed:
```python
# This field auto-hides from forms when scopes are turned off
scope = ScopeForeignKey('microsys.Scope', on_delete=models.PROTECT, null=True, blank=True)
```

---

### 🧩 Core Utilities

- **`get_model_classes` Helper function**
The `get_model_classes` function acts as a unified factory for resolving your application's `Form`, `Table`, and `Filter` classes using standard naming conventions (`ModelNameForm`, `ModelNameTable`, etc.).

**How it works**
By default, the function searches within the specified model's app for matching forms, tables, and filters. If found, it returns them inside a `LazyModelClasses` object. If none are explicitly provided, it will dynamically generate default ones at runtime.

**Key Features:**
- **Caching**: Results are memoized so the discovery process only happens once per app lifecycle, achieving 0.0001ms fetch times on subsequent visits.
- **Lazy Loading**: If you only ask for the `model` or the `form`, the function will not evaluate or generate the `Table` or `Filter` classes. This prevents unnecessary database queries (e.g. filter year aggregations) and speeds up your views.
- **Convention Overrides**: If your form does not match the standard `ModelForm` naming convention (e.g., `AdminAssetForm`), you can easily explicitly override it.

**Usage:**

```python
from microsys.utils import get_model_classes

def my_view(request):
    # Retrieve the classes
    classes = get_model_classes('Asset')
    
    # 1. Accessing values resolves them lazily
    AssetModel = classes.get('model')
    AssetForm = classes.get('form')
    
    # 2. Providing custom overrides at the request level
    admin_classes = get_model_classes('Asset', overrides={'form': 'storage.forms.AdminAssetForm'})
```

**Model-Level Overrides:**
Instead of passing `overrides` in every view, you can permanently register exceptions in your model definition:
```python
class Asset(ScopedModel):
    name = models.CharField(...)
    
    model_classes_overrides = {
        'form': 'storage.forms.AdminAssetForm',
        'table': 'storage.tables.CompactAssetTable'
    }
```

- **`resolve_model_by_name` Helper function**
Dynamically resolves a Django model class from a string, allowing you to build decoupled, dynamic views without hardcoded model imports.

**Usage:**
```python
from microsys.utils import resolve_model_by_name

# Checks if full path is provided, otherwise searches globally across all apps
model = resolve_model_by_name('Invoice') 

# Or restrict to a specific app
model = resolve_model_by_name('Asset', app_label='storage')
```

- **`has_related_records` & `collect_related_objects` Helper functions**
Data introspection utilities for understanding model dependencies at runtime. Perfect for building custom "Smart Delete" warnings, dependency analysis, or "Usage Info" panels without having to know the exact field relationships in advance.

**Usage:**
```python
from microsys.utils import has_related_records, collect_related_objects

def check_delete(request, pk):
    instance = MyModel.objects.get(pk=pk)
    
    # 1. Fast boolean check (often used to lock records from deletion or editing)
    # the ignore_relations param skips accessors you do not care about.
    is_locked = has_related_records(instance, ignore_relations=['logs'])
    
    if is_locked:
        # 2. Detailed introspection (returns dict of e.g. {'Invoices': ['INV-01', 'INV-02']})
        blocking_items = collect_related_objects(instance)
        print("Cannot delete, used in:", blocking_items)
```

- **`setup_filter_helper` Helper function**
Instantly transforms a standard `django-filter` instance into a modern, responsive search bar with a "Clear" button that only appears when filters are active.

**Usage:**
```python
from microsys.utils import setup_filter_helper

def asset_list(request):
    filter_instance = AssetFilter(request.GET, queryset=Asset.objects.all())
    # 1. Configures Crispy Layout and Hidden parameters (sort, page, per_page)
    # 2. Handles the Search/Clear button UI alignment
    setup_filter_helper(filter_instance, request)
    
    return render(request, 'my_template.html', {'filter': filter_instance})
```

---

### 📂 Dynamic Section Mode


Microsys offers a powerful "Zero-Boilerplate" CRUD interface for managing auxiliary data models (like Departments, Categories, etc.).

- **How It Works**
1. **Mark Your Model**: Add `is_section = True` to your model attrs.
   ```python
   class Department(ScopedModel):
       name = models.CharField(...)
       is_section = True
   ```
2. **Auto-Discovery**: The system automatically generates a management UI with:
   - Searchable Table (with pagination & sorting)
   - Add/Edit Modals (using Crispy Forms)
   - Delete protection (checks for related records)
   - Filters (Keyword search + Date ranges if applicable)
   - Context menu on every row (View, Edit, Delete) with permission checks

   > **Note**: You can customize the auto-generated components by adding `form_exclude` and `table_exclude` lists to your model:
   > ```python
   > class Department(ScopedModel):
   >     # ...
   >     form_exclude = ['internal_notes']
   >     table_exclude = ['internal_notes', 'created_at']
   > ```

- **Custom Form / Table / Filter Classes**

The system follows a **resolution order** when looking for Form, Table, and Filter classes:

| Priority | Method | Example |
|---|---|---|
| 1 | **Convention import** | `forms.py` → `DepartmentForm`, `tables.py` → `DepartmentTable` |
| 2 | **Model method** | `get_form_class()`, `get_table_class()`, `get_filter_class()` |
| 3 | **String path method** | `get_form_class_path()` → `'myapp.forms.CustomForm'` |
| 4 | **Auto-generation** | Built at runtime from model introspection |

```python
class Department(ScopedModel):
    is_section = True
    name = models.CharField(...)

    # Option A: Define methods that return the class directly
    @classmethod
    def get_form_class(cls):
        from .forms import DepartmentForm
        return DepartmentForm

    # Option B: Return a dotted import path
    @classmethod
    def get_table_class_path(cls):
        return 'myapp.tables.DepartmentTable'
```

> **Tip**: If you simply name your classes following the convention (`<Model>Form`, `<Model>Table`, `<Model>Filter`) in the standard module files (`forms.py`, `tables.py`, `filters.py`), the system finds them automatically — no model method needed.

- **What Auto-Generated Components Include**

| Component | Features |
|---|---|
| **Form** | All fields (respects `form_exclude`), autofill widgets on FKs, scope auto-hidden when disabled |
| **Table** | All columns (respects `table_exclude`), sorting, pagination, context menu per row |
| **Filter** | Keyword search across text/numeric fields, date range pickers (flatpickr), year dropdown |

- **Auto Subsections (Parent-Child Relations)**
If a Section model has a `ManyToManyField` to another model that is **not** a standalone section (i.e. a "child" model), the system automatically nests it:

```python
class SubUnit(ScopedModel):  # Child model (no is_section=True)
    name = models.CharField(...)

class MainUnit(ScopedModel): # Parent section
    is_section = True
    sub_units = models.ManyToManyField(SubUnit)
```

**Result:**
- When editing a `MainUnit`, you will see a list of `SubUnits`.
- You can **Add/Edit/Delete** `SubUnits` directly from the `MainUnit` modal via AJAX.
- This creates a seamless "Master-Detail" management experience without writing a single view or form.

- **Section Discovery Tool**
The `discover_section_models` helper function is the engine behind the "Zero-Boilerplate" dashboard. It scans your apps for any model marked with `is_section = True` and returns a complete metadata package (resolved Forms, Tables, Filters, and M2M Subsections).
```python
from microsys.utils import discover_section_models
sections = discover_section_models(app_name='storage')
```

Notes:
- These attributes apply only to the auto-generated form/table.
- If you provide a custom Form/Table class, it takes full precedence.

---

### 📂 Universal File Fetcher & Excel Export

Microsys provides a unified, zero-boilerplate utility for downloading files and exporting data.

- **Universal Fetcher (`fetch_file`)**
Handles single-file serving and multi-file zipping automatically.

```python
from microsys.fetcher import fetch_file

def download_view(request, pk):
    # 1. Single Instance -> Serves the file directly
    obj = MyModel.objects.get(pk=pk)
    return fetch_file(request, obj)

def bulk_download_view(request):
    # 2. QuerySet/List -> Serves a ZIP file containing all files
    objs = MyModel.objects.filter(category='urgent')
    return fetch_file(request, objs)

def specific_field_view(request, pk):
    # 3. Filter by specific file field
    obj = MyModel.objects.get(pk=pk)
    return fetch_file(request, obj, file_type='pdf_report')
```

- **Smart Excel Export (`fetch_excel`)**
Exports any QuerySet to Excel with auto-generated headers and smart column hiding.

```python
from microsys.fetcher import fetch_excel

def export_view(request):
    qs = MyModel.objects.all()
    
    )
```

- **Smart Fetcher Logic**
The system automatically handles:
- **Single Instance**: Serves the file directly with appropriate headers.
- **Lists/QuerySets**: Generates a ZIP file containing all non-empty `FileFields` found on the objects.
- **Smart Metadata**: Automatically finds the best "Identifier" (e.g. `number`, `code`, `pk`) and "Date" field for clean filenames.
- **Smart Excel Hiding**: `fetch_excel` automatically hides sensitive system columns (IDs, file paths, timestamps) to keep the exported sheet professional.

---

### ⚡ Global Autofill

`microsys` includes a powerful client-side autofill engine designed to eliminate repetitive data entry.

- **Features**
1.  **Smart FK Autofill**:
    -   Selecting a ForeignKey (e.g., `User`, `Employee`) automatically populates related fields in the form (like `email`, `phone`, `department`).
    -   **Recursive Data Fetching**: It intelligently fetches data from related `OneToOne` models (e.g., `User.profile.phone`) without extra configuration.
    -   **Auto-Clear**: Deselecting a value or toggling autofill **OFF** instantly clears the related fields to prevent stale data.

2.  **Sticky Forms (Clone Last Entry)**:
    -   Perfect for high-volume data entry. When enabled, the form automatically pre-fills with values from the **last created record** upon load.
    -   Submitting the form saves the state, allowing rapid sequential entry.

3.  **Global Toggle**:
    -   A toggle switch automatically appears in the top-right title bar whenever autofill is available on the page.
    -   The state (ON/OFF) is saved in user preferences (DB-backed).

- **How to Use**

1. **Foreign Key Autofill (Zero Config)**
The system automatically detects standard Django ForeignKey widgets and injects the necessary `data-autofill-source` attributes during form generation. **It works out of the box** for any model managed via Sections or Dynamic Modals.

The injected attribute looks like:
```html
<select name="user" data-autofill-source="auth.user">
```
When a value is selected, the JS engine calls the detail API to fetch related fields and populates matching form inputs.

> **Note**: Only works for fields that have a corresponding input in the form with a matching name (e.g., `User.email` -> `<input name="email">`).

2. **Enable Sticky Forms**
To enable the "Clone Last Entry" feature for a specific form, simply add the `data-model-name` attribute to your HTML form tag:

```html
<form method="post" data-app-label="myapp" data-model-name="mymodel">
    <!-- ... fields ... -->
</form>
```

- **Autofill API Endpoints**

These are the REST endpoints powering autofill behind the scenes:

| Endpoint | Method | Purpose |
|---|---|---|
| `/sys/api/details/<app>/<model>/<pk>/` | GET | Fetch a specific record's data (recursive FK/O2O traversal) |
| `/sys/api/details/<app>/<model>/empty_schema/` | GET | Get empty field structure (for clearing forms) |
| `/sys/api/last-entry/<app>/<model>/` | GET | Get the last created record (for Sticky Forms) |

**Programmatic Integration:**
You can manually trigger or configure autofill in your forms:
```python
class InvoiceForm(forms.ModelForm):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        # 1. Manually set the source for FK lookup
        self.fields['customer'].widget.attrs['data-autofill-source'] = 'crm.Customer'
        # 2. Or use the set_field_attrs helper to auto-detect all FKs
        set_field_attrs(self)
```

---

### ↔️ Interactive Sidebar 

The sidebar is a dynamic, highly customizable navigation hub that supports both auto-discovery and manual configuration.

- **Auto-Discovery Mode**
Microsys can automatically introspect your project's URL patterns and Models to generate navigation items. By default, it looks for URLs containing `_list`.

```python
SIDEBAR_AUTO = {
    'ENABLED': True,                    # Enable auto-discovery
    'URL_PATTERNS': ['list'],           # Keywords to match in URL names
    'EXCLUDE_APPS': ['admin', 'auth'],  # Apps to exclude from sidebar
    'EXCLUDE_MODELS': [],               # Specific models to exclude (e.g., ['myapp.mymodel'])
    'CACHE_TIMEOUT': 3600,              # Cache timeout in seconds
    'DEFAULT_ICON': 'bi-list',          # Default Bootstrap icon
    'SYSTEM_GROUP_ENABLED': True,       # Toggle the built-in "System Management" group
}
```

- **Advanced Customization**
Fine-tune the sidebar behavior using `SIDEBAR_AUTO` settings in your `settings.py`:

- **Reordering**: Users with `is_staff` or specific permissions can toggle **Reorder Mode** from the sidebar toolbar. Drag and drop items to customize the layout; the new order is persisted to the database preferences.
- **Label & Icon Overrides**: Use `DEFAULT_ITEMS` to customize labels, icons, or sort order for auto-discovered views without modifying the models.
- **Custom Groups (Accordions)**: Use `EXTRA_ITEMS` to add manual groups and links for non-model views or external URLs. Supports permission-based visibility.

```python
SIDEBAR_AUTO = {
    'DEFAULT_ITEMS': {
        'decree_list': {
            'label': 'Decisions', 
            'icon': 'bi-gavel', 
            'order': 10
        },
    },
    'EXTRA_ITEMS': {
        'Management': {
            'icon': 'bi-gear',
            'items': [
                {
                    'url_name': 'custom_report', 
                    'label': 'Yearly Report', 
                    'icon': 'bi-file-earmark-bar-graph',
                    'permission': 'is_staff'
                },
            ]
        }
    }
}
```

- Template Tags
If you are building a custom sidebar template, you can use these tags:
- `{% auto_sidebar %}`: Renders all auto-discovered items.
- `{% extra_sidebar %}`: Renders the groups and items defined in `EXTRA_ITEMS`.

---

### 🖱️ Micro Context Menu ("Right-Click")

A global, data-driven context menu that can be attached to any element to provide quick actions.

- **How it works**
1. **Mark Element**: Add `data-micro-context="true"` to any HTML element.
2. **Define Actions**: Provide a JSON list of actions in `data-micro-actions`.

```html
<tr data-micro-context="true" 
    data-micro-actions='[{"label": "Edit", "url": "/edit/1", "icon": "bi-pencil"}]'>
    ...
</tr>
```

- **Features**:
  - **Global**: Works anywhere, automatically initialized.
  - **Dynamic**: Actions are defined per-element via data attributes.
  - **Mobile Ready**: Supports long-press on touch devices.
  - **Standardized**: Used by system tables (Users, Sections) for a consistent experience.
  - **Double Click**: Supports double-click actions (e.g. View) if `dblclick: true` is set on an action.
  - **Smart Actions**: Includes "View Content" and "Smart Delete" handling for Sections using dynamic modals.
  - **Permission-Based**: Actions can require permissions — users without them won't see the action.

- **Action Schema**

| Key | Type | Description |
|---|---|---|
| `label` | string | Display text |
| `icon` | string | Bootstrap Icon class (e.g. `bi bi-pencil`) |
| `url` | string | Navigation URL (for `"type": "url"`) |
| `type` | string | `"url"` (default), `"event"`, or `"divider"` |
| `event` | string | Custom JS event name (for `"type": "event"`) |
| `data` | object | Payload dispatched with the event |
| `dblclick` | bool | Also trigger on double-click |
| `textClass` | string | CSS class for text (e.g. `"text-danger"`) |
| `permissions` | list | Required Django permissions (e.g. `["myapp.delete_item"]`) |
| `permission` | string | Single required permission (shorthand) |

- **Event-Based Actions**

Instead of navigating to a URL, actions can dispatch custom JavaScript events:
```python
{
    "label": "View Details",
    "icon": "bi bi-eye",
    "type": "event",
    "event": "micro:record:view",
    "data": {"model": "department", "id": record.pk},
    "dblclick": True
}
```
You can listen for these events in your own JS:
```javascript
document.addEventListener('micro:record:view', function(e) {
    console.log(e.detail.data);  // {model: 'department', id: 5, name: '...'}
});
```

**Built-in Record Events (dispatched by AutoTable):**

| Event | Triggered By |
|---|---|
| `micro:record:view` | Double-click or "View" context item |
| `micro:record:edit` | "Edit" context item |
| `micro:record:delete` | "Delete" context item |

**Event Payload (`e.detail`):**

| Key | Description |
|---|---|
| `e.detail.data.model` | Lowercase model name (e.g. `"employee"`) |
| `e.detail.data.id` | Record primary key |
| `e.detail.data.name` | String representation of the record |
| `e.detail.originalTarget` | The DOM element that was right-clicked |
| `e.detail.action` | Full action object (label, icon, permissions, etc.) |

- **Permission Filtering**

Actions with `permissions` are automatically hidden from users who lack the required permissions. Use `filter_context_actions` in your backend code:

```python
from microsys.utils import filter_context_actions

# In your table __init__ or view:
actions = filter_context_actions(request.user, actions)
```

> **Note**: Auto-generated section tables already apply permission filtering automatically — no extra code needed.

- **Usage with Django Tables2**

You can inject the context menu directly from your `tables.py` without modifying templates.

1.  **Define Row Attributes**: Use `row_attrs` in `Meta` or `__init__`.
2.  **Define Actions**: Create a list of actions and serialize to JSON.

```python
import json
from django.urls import reverse

class MyTable(tables.Table):
    class Meta:
        model = MyModel
        # ...

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        
        # Define Actions Helper
        def get_actions(record):
            actions = [
                {
                    "label": "View", 
                    "icon": "bi bi-eye", 
                    "url": reverse('my_view', args=[record.pk]),
                    "dblclick": True  # OPTIONAL: Trigger on double-click
                },
                {"type": "divider"},
                {
                    "label": "Delete", 
                    "icon": "bi bi-trash", 
                    "url": reverse('my_delete', args=[record.pk]),
                    "textClass": "text-danger",
                    "permissions": ["myapp.delete_mymodel"]
                }
            ]
            return json.dumps(actions)

        # Inject Attributes
        self.row_attrs.update({
            "data-micro-context": "true",
            "data-micro-actions": get_actions
        })
```

---

### 🌍 Translation Framework
 
microsys ships with Arabic and English translations. Add more languages directly via the **System Settings** UI (available in the App Options page for superusers).

**How it works:**
- The system automatically discovers and loads translations from all installed apps.
- It looks for `translations.py` in each app and merges the `MS_TRANSLATIONS` dictionary.
- Language is resolved: **user preference** → **`default_language`** → **`'ar'`**
- Templates use `{{ MS_TRANS.key }}` for all UI strings.
- The `<html>` tag gets dynamic `lang`/`dir` attributes.
- Bootstrap CSS auto-switches between RTL and LTR variants.

**Template variables available:**
| Variable | Type | Description |
|---|---|---|
| `CURRENT_LANG` | `str` | Active language code (e.g. `'ar'`, `'en'`) |
| `CURRENT_DIR` | `str` | Active direction (`'rtl'` or `'ltr'`) |
| `LANGUAGES` | `dict` | All configured languages |
| `MS_TRANS` | `dict` | Translated strings for the active language |

**Adding custom strings:**
Simply add a `translations.py` file to any of your apps:
```python
# my_app/translations.py
MS_TRANSLATIONS = {
    'ar': {'my_key': 'قيمة مخصصة'},
    'en': {'my_key': 'Custom Value'},
}
```
Then in templates: `{{ MS_TRANS.my_key }}`

---

### 🏷️ Template Tags Reference

Microsys provides several custom template tags and filters. Load them in your templates as needed.

**Sidebar Tags** (`{% load sidebar_tags %}`)
| Tag | Usage | Description |
|---|---|---|
| `{% auto_sidebar %}` | Inclusion tag | Renders all auto-discovered sidebar navigation items |
| `{% extra_sidebar %}` | Inclusion tag | Renders extra sidebar groups defined in `EXTRA_ITEMS` |
| `{% sidebar_item_class 'url_name' %}` | Simple tag | Returns `'active'` if current path matches the URL name |

**Microsys Tags** (`{% load microsys_tags %}`)
| Tag | Usage | Description |
|---|---|---|
| `{% ms_timesince value %}` | Simple tag | Translated relative timestamp (e.g., "9 ساعات و 52 دقيقة") |
| `{% include_if_exists 'path/to/template.html' %}` | Simple tag | Safely includes a template only if it exists — no error if missing |

**Translation Tags** (`{% load microsys_translation %}`)
| Tag | Usage | Description |
|---|---|---|
| `{% translate_log_value value 'action' %}` | Simple tag | Translates log values using `MS_TRANS` (e.g., `action_login` key) |
| `{% format_log_details details %}` | Simple tag | Renders a JSON diff dict as styled HTML badges |

```html
<!-- Example: translated relative time -->
{% load microsys_tags %}
<span>{% ms_timesince user.last_login %}</span>

<!-- Example: activity log with translated action and formatted diffs -->
{% load microsys_translation %}
<td>{% translate_log_value log.action 'action' %}</td>
<td>{% format_log_details log.details %}</td>
```

---

### 🔲 Dynamic Modal Manager

The Dynamic Modal Manager provides a **universal, AJAX-driven modal** for managing any model's records (List + Form) without writing custom views or templates.

- **How it works**

1.  **Include the Modal Template**: Add the modal shell to any template that extends `base.html`:
    ```html
    {% include 'microsys/includes/dynamic_modal.html' %}
    ```
    This adds a hidden Bootstrap modal and loads the `dynamic_modals.js` script.

2.  **Wire URLs**: In your `urls.py`, register the class-based views for your model:
    ```python
    from microsys.views import DynamicModalManagerView, DynamicModalDeleteView

    urlpatterns = [
        # Combined List + Form (GET = load, POST = save)
        path('my-model/modal/', DynamicModalManagerView.as_view(), name='mymodel_modal'),
        path('my-model/modal/<int:pk>/', DynamicModalManagerView.as_view(), name='mymodel_modal'),
        # Delete endpoint
        path('my-model/modal/delete/<int:pk>/', DynamicModalDeleteView.as_view(), name='mymodel_modal_delete'),
    ]
    ```

3.  **Trigger the Modal**: Add a button with `data-dynamic-modal` pointing to your URL:
    ```html
    <button data-dynamic-modal="{% url 'mymodel_modal' %}"
            data-modal-title="Manage Items">
        <i class="bi bi-gear"></i> Manage
    </button>
    ```

- **Features**
  - **Auto Form/Table**: Uses the same generic discovery system as Sections (convention → model method → auto-generation).
  - **Inline CRUD**: Edit and delete records directly inside the modal — the list auto-refreshes seamlessly.
  - **Smart Form Context**: Instantiates forms with `user` and `request` automatically if their `__init__` signature accepts them.
  - **Delete Protection**: Checks for related records before deletion, blocking unsafe actions and displaying localized error messages.

### 🎛️ Advanced Configuration

`DynamicModalManagerView` provides powerful URL-level overrides to customize its behavior without writing new views.

```python
# 1. Standard (Combined Form + Table)
path('zones/modal/', DynamicModalManagerView.as_view(model=Zone), name='zone_modal'),

# 2. Form Only (No Table)
path('users/modal/', DynamicModalManagerView.as_view(
    model=User,
    form_class=UserModalForm, # Form Override
    show_table=False
), name='user_modal'),

# 3. Read-Only Detail View (Custom Template)
path('logs/<int:pk>/modal/', DynamicModalManagerView.as_view(
    model=UserActivityLog,
    template_name='microsys/activity_detail_modal.html',
    show_form=False, 
    show_table=False
), name='log_modal'),
```

**Attributes:**
- `model`: Target model (Required).
- `form_class`: Override auto-discovered form class.
- `show_table`: Default `True`. Set `False` to hide the list section.
- `show_form`: Default `True`. Set `False` to hide the form section.
- `template_name`: Override the default `dynamic_modal_combined.html` shell.

#### 🧠 `handles_save` Flag
If your form performs complex saving logic (e.g. password hashing, nested M2M assignments, profile generation), set `handles_save = True` on your class. The ManagerView will bypass its generic save cycle and yield execution entirely to `form.save(commit=True)`.

#### 🔗 Automated Detail Context (`get_modal_context`)
When using custom templates (`show_form=False`, `show_table=False`), the view automatically resolves the `instance` (also available as `object`). If your model requires additional context (like resolving related objects), simply define `get_modal_context(self)` on the model:

```python
class MyModel(models.Model):
    def get_modal_context(self):
         return {'related_items': self.items.all()}
```
The view will auto-call this method and inject the returned dictionary natively into the template context. *Zero boilerplate.*

#### 🪄 Zero-Boilerplate AutoDetail View
If you request a read-only modal (`show_form=False`, `show_table=False`) and *do not provide a custom template*, `DynamicModalManagerView` will automatically generate a dynamic info-grid containing all the object's fields.

The generator natively:
- Skips audit fields (`created_at`, `updated_by`, etc.) and passwords.
- Skips the `scope` field if scopes are universally disabled.
- Evaluates `ManyToMany` fields into comma-separated lists.
- Renders `FileField`/`ImageField` as downloadable buttons.
- Translates `verbose_name` and `choices` values correctly.

```python
# Fully automated read-only detail view — No template required!
path('logs/<int:pk>/modal/', DynamicModalManagerView.as_view(
    model=UserActivityLog,
    show_form=False, 
    show_table=False
), name='log_modal'),
```

---

### 🌐 Automatic Scope Management

The `ScopedModel` is designed to be completely dynamic — if you turn off `is_scope_enabled()`, the `scope` field **automatically disappears** from every form, filter, and table across the entire app without any code edits.

This is achieved through **auto-injection patches** applied at startup (`AppConfig.ready()`). There is **nothing** you need to do as a developer:

```python
# Just use ScopedModel. That's it. Scope is handled automatically.
class MyModel(ScopedModel):
    name = models.CharField(max_length=100)

# Your forms, filters, and tables don't mention scope at all:
class MyForm(forms.ModelForm):
    class Meta:
        model = MyModel
        fields = ['name']  # scope is auto-injected + auto-managed

class MyFilter(django_filters.FilterSet):
    class Meta:
        model = MyModel
        fields = ['name']  # scope filter auto-injected when enabled

class MyTable(tables.Table):
    class Meta:
        model = MyModel
        fields = ('name',)  # scope column auto-injected when enabled
```

**How it works:**
- **Forms**: Scope field auto-injected into `self.fields`. Auto-hidden when disabled. Auto-locked to user's profile scope for non-superusers.
- **Filters**: Scope filter auto-injected into `self.filters`. Auto-removed when disabled or user is scope-locked.
- **Tables**: Scope column auto-added via `extra_columns` when enabled. Auto-excluded when disabled.
- **Model save**: `ScopedModel.save()` auto-sets scope from the user's profile (just like `created_by`).

> **Opt-out**: If you explicitly add `'scope'` to `Meta.exclude`, the auto-injection is skipped.

#### 🛡️ Relation Protection (`has_related_records`)
`DynamicModalDeleteView` natively checks if a record has foreign key or M2M relations before allowing deletion. This powers the localized "Cannot delete because related records exist" error.

This is powered by the `microsys.utils.has_related_records(instance, ignore_relations=None)` utility. 

**Important Performance Note:**
The context menu `Edit` and `Delete` buttons are **not** hidden when related records exist. Running `has_related_records()` on every row during table rendering would cause massive N+1 query bottlenecks on large datasets. 
Instead:
- The **Delete** button is always shown, but the deletion *attempt* is safely intercepted by `DynamicModalDeleteView`.
- If you need to block **Editing** based on relations, call `has_related_records(self.instance)` inside your form's `clean()` method and raise a `ValidationError`.

**Usage Examples:**

*1. Blocking edits on records with relations:*
```python
from django import forms
from django.core.exceptions import ValidationError
from microsys.utils import has_related_records
from myapp.models import BudgetChapter

class BudgetChapterForm(forms.ModelForm):
    class Meta:
        model = BudgetChapter
        fields = '__all__'

    def clean(self):
        cleaned_data = super().clean()
        # Only block editing on existing instances, not new creations
        if self.instance.pk and has_related_records(self.instance):
             raise ValidationError("This chapter cannot be edited because it has related records (e.g. distributed funds).")
        return cleaned_data
```

*2. Safely deleting in a custom view (bypassing Dynamic Modals):*
```python
from django.shortcuts import get_object_or_404
from django.http import JsonResponse
from microsys.utils import has_related_records

def my_custom_delete_view(request, pk):
    obj = get_object_or_404(MyModel, pk=pk)
    
    # You can pass a list of relation field names to ignore during the check
    if has_related_records(obj, ignore_relations=['logs', 'temporary_drafts']):
        return JsonResponse({'error': 'Cannot delete because related active records exist.'})
        
    obj.delete()
    return JsonResponse({'success': True})
```

---

### 🖱️ Programmatic & Context Menu Control

You can trigger modals dynamically via JavaScript or the `AutoTable` Context Menu system.

**Context Menu Example (Direct Open):**
```json
{
    "label": "Review details",
    "icon": "bi bi-eye",
    "event": "micro:dynamic_modal:open",
    "data": {
        "url": "/my-model/modal/1/",
        "title": "Modal Title"
    }
}
```

**Context Menu Example (Global Edit Event):**
Starting in v1.14.1, you can dispatch a decoupled `micro:record:edit` event. Standard `manage_sections.html` listeners natively catch this and pipe it into the Dynamic Modal system.
```json
{
    "label": "Edit",
    "icon": "bi bi-pencil",
    "type": "event",
    "event": "micro:record:edit",
    "data": {
        "model": "zone",
        "id": 1,
        "name": "Warehouse A"
    }
}
```

**JavaScript Example:**
```javascript
const event = new CustomEvent('micro:dynamic_modal:open', {
    bubbles: true,
    detail: { data: { url: '/my-model/modal/1/', title: 'Manage items' } }
});
document.body.dispatchEvent(event);
```

- **Creating Custom Modal endpoints**

If you bypass `DynamicModalManagerView` and create your own views (like invoice item processing) returning a `JsonResponse({'html': ...})` structure during GET, ensure that on POST requests your custom backend endpoint returns exactly:
- `JsonResponse({'success': True})` for a successful form submission, or
- `JsonResponse({'error': 'Error message'})` if validation fails.
This strict JSON signature is required for the `dynamic_modals.js` interceptor to gracefully capture and handle the result!

---

### 🔒 Double-Submit Prevention

microsys includes a **global JavaScript** mechanism that prevents accidental double form submissions.

- **How it works**: When any form's submit button is clicked, it is immediately **disabled** to block rapid successive clicks.
- **Scope**: Applies automatically to all forms managed by microsys templates (login, user management, sections, modals, profile).
- **No configuration needed** — it's built into the base template.

---

### 🔧 Preferences API

The Preferences API allows real-time persistence of user UI settings.

| Endpoint | Method | Purpose |
|---|---|---|
| `/sys/api/preferences/update/` | POST | Update individual preference keys |
| `/sys/api/preferences/reset/` | POST | Reset all preferences to defaults |

**Payload format** (for update):
```json
{"key": "theme", "value": "dark"}
```

**Supported keys**: `theme`, `lang`, `sidebar_collapsed`, `sidebar_accordions`, `sidebar_order`, `autofill_enabled`.

> **Note**: Preferences are stored in `Profile.preferences` (a `JSONField`). The API handles both session and database persistence.

---

### 🎨 Templates & Theming

- **Base Template**
The system provides a robust base template located at `microsys/templates/microsys/base.html`.
You can extend this template in your own views to maintain consistent layout and functionality:

```html
{% extends "microsys/base.html" %}

{% block extra_head %}
    <!-- Extra CSS or Meta tags -->
{% endblock %}

{% block content %}
    <h1>Page Content</h1>
{% endblock %}

{% block scripts %}
    <!-- Extra JS scripts -->
{% endblock %}
```

- **Global List Template**

`microsys/helpers/global_list.html` is a ready-to-use, zero-boilerplate list page that renders a form, filter, and table from context. Any CBV list view can use it directly.

**Required context variables:**

| Variable | Type | Description |
|---|---|---|
| `page_title` | string | Page heading and `<title>` |
| `form` | Django Form | The create/edit form (optional — card hidden if `None`) |
| `filter` | django-filter FilterSet | The search/filter form (optional — card hidden if `None`) |
| `table` | django-tables2 Table | The data table (optional — card hidden if `None`) |
| `MS_TRANS` | dict | Translation strings dictionary |

**Usage with a CBV:**
```python
class MyListView(LoginRequiredMixin, FilterView, SingleTableView):
    template_name = 'microsys/helpers/global_list.html'
    paginate_by = 10

    @property
    def table_class(self):
        return get_model_classes('MyModel', app_label='myapp').get('table')

    @property
    def filterset_class(self):
        return get_model_classes('MyModel', app_label='myapp').get('filter')

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['page_title'] = 'My Records'
        context['MS_TRANS'] = _get_request_translations(self.request)
        return context
```

The template automatically loads `form_toggle.js` and renders everything in a consistent card layout with proper CSP nonces.

### 🏷️ Microsys Template Tags
Microsys provides several global template tags built for dynamic, multi-language UI rendering. Load them using `{% load microsys_tags %}`.

- **`{% ms_timesince %}`**: A translated relative timestamp (e.g., "9 hours" -> "9 ساعات").
- **`{% include_if_exists %}`**: Safely includes a template only if it exists — fails silently if missing.

### 🪄 Design Helper: `set_field_attrs`
The `set_field_attrs` utility instantly makes any Django form compatible with the Microsys design system, adding Bootstrap 5 classes, RTL/LTR support, and Flatpickr date pickers.
```python
from microsys.utils import set_field_attrs
set_field_attrs(form, request)
```

> **Note:** The base template automatically handles the sidebar, title bar, messages, and theme loading. Replacing it entirely will break core system functionality.

- **Customizing Base Template (Injection)**

You can inject custom HTML, CSS, or JavaScript into the `microsys` base template globally without overriding the entire template.
This is useful for adding analytics scripts, global styles, or meta tags.

**How to use:**
Create the following files in your project's `templates/` directory:

1.  **Head Content (Meta, CSS)**: `microsys/includes/custom_head.html`
    - Renders in `<head>`, **before** `{% block extra_head %}`.
    - Ideal for global CSS overrides or meta tags.

2.  **Scripts**: `microsys/includes/custom_scripts.html`
    - Renders just before `</body>`.
    - Ideal for global JS libraries or analytics.

> **Note**: Because these are templates (not static files), you can use template tags like `{% static %}` or `{% url %}` inside them, in addition to conditional logic!

- **Theming**
- **Framework**: Built on **Bootstrap 5**.
- **Colors**: The `primary` color automatically adapts to the selected theme. Secondary/Success/Danger colors are slightly desaturated for better visual ergonomics.
- **Customization**:
  - Use standard Bootstrap classes (`btn-primary`, `text-success`, etc.).
  - Dark mode is supported out of the box. If you encounter issues, you can override styles via `extra_head` or report them.

- **Unified User Preferences (DB-Backed)**
The system now centralizes user UI settings in the database instead of relying on `localStorage` or server sessions. This ensures that a user's chosen theme, sidebar state, and item ordering are consistent across all their devices.

- **Storage**: Preferences are stored in a `JSONField` named `preferences` within the `Profile` model.
- **Syncing**: An API endpoint (`/sys/api/preferences/update/`) handles real-time updates from the frontend.
- **Persistence**:
  - **Sidebar**: Collapsed/Expanded state and open accordion groups are persisted.
  - **Reordering**: Drag-and-drop order of sidebar items is saved globally.
  - **Theme**: Selected UI theme (Light, Dark, Royal, etc.) is synced.
  - **Language**: Selected language is synced.
  - **Autofill**: Selected autofill state is synced.

> [!IMPORTANT]
> To enable this feature, ensure you have applied migrations (`makemigrations microsys` and `migrate microsys`).

- **Dashboard Activity Chart**
The dashboard now includes a built-in activity chart powered by **Plotly.js**:
- **Visualizes**: System activity for the last 24 hours.
- **Design**: Seamless, transparent, lightweight line chart with no axis labels for a clean look.
- **Data Source**: Aggregates `UserActivityLog` entries.
- **Responsive**: Automatically resizes with the window and sidebar toggles using `ResizeObserver`.

----

## 📁 File Structure

```
microsys/
├── management/             # Custom Management commands (microsys_setup, microsys_check).
├── migrations/             # App Migrations.
├── static/                 # microsys/ (js/css/img).
│   └── microsys/
│       ├── autofill/       # Autofill engine JS.
│       ├── context_menu/   # Context menu JS/CSS.
│       ├── js/             # dynamic_modals.js.
│       ├── main/           # Core CSS (themes, layouts, fonts) and JS.
│       ├── sidebar/        # Sidebar JS/CSS.
│       ├── themes/         # Theme CSS variants (dark, royal, etc.).
│       └── tutorial/       # Tutorial engine JS/CSS.
├── templates/              # microsys/ templates.
│   └── microsys/
│       ├── includes/       # Reusable partials (dashboard, dynamic_modal, titlebar, etc.).
│       ├── sections/       # Section management templates.
│       ├── users/          # User management templates.
│       └── base.html       # Main layout template.
├── templatetags/           # Custom template tags.
│   ├── microsys_tags.py        # ms_timesince, include_if_exists.
│   ├── microsys_translation.py # translate_log_value, format_log_details.
│   └── sidebar_tags.py         # auto_sidebar, extra_sidebar, sidebar_item_class.
├── views/                  # Modular view package.
│   ├── __init__.py         # Re-exports all views for backward compatibility.
│   ├── general.py          # Dashboard, Options.
│   ├── users.py            # User CRUD, Login, Detail views.
│   ├── twofa.py            # 2FA setup, verification, backup codes.
│   ├── sections.py         # Section CRUD, DynamicModalManagerView, DynamicModalDeleteView.
│   ├── scopes.py           # Scope management.
│   ├── activitylog.py      # Activity log views.
│   ├── profile.py          # Profile view and edit.
│   └── sidebar.py          # Sidebar toggle.
├── admin.py                # Admin Panel Registration.
├── api.py                  # Autofill API, Preferences API, Permission Checker.
├── apps.py                 # Django App configuration.
├── context_processors.py   # Branding, Scope, Sidebar order and Themes.
├── discovery.py            # Sidebar auto-discovery logic.
├── fetcher.py              # Universal Dynamic Downloader and Excel Exporter.
├── filters.py              # User and ActivityLog filters.
├── forms.py                # User, Profile, Permissions, and Section forms.
├── managers.py             # ScopedManager (scope + soft-delete filtering).
├── middleware.py            # ActivityLog middleware (thread-local user/request).
├── models.py               # Profile, Scope, ScopedModel, ScopeForeignKey, UserActivityLog.
├── signals.py              # Auto-create profile, Auto activity logging (CRUD/Login/Logout).
├── tables.py               # User, ActivityLog, and Scope tables.
├── translations.py         # Built-in AR/EN translation strings.
├── urls.py                 # URL routing.
└── utils.py                # Discovery, form/table/filter resolution, helpers.
```

---

## 📜 Version History

| Version  | Changes |
|----------|---------|
| v1.0.0   | • Initial release as pip package |
| v1.1.0   | • **Application Complete Restructure** with moudular files, templates, static, etc. <br> • URL restructure: auth at `/accounts/`, system at `/sys/` <br> • Added `microsys_setup` and `microsys_check` management commands <br> • Runtime configuration validation |
| v1.2.0   | • **Dynamic Section Management** New Powerful Zero-Boilerplate Section management mode <br> • Name changed to `django-microsys` <br> • Scope fields now hide automatically when scopes are disabled <br> • System sidebar group ships by default (configurable) <br> • `is_staff` moved into the permissions UI |
| v1.2.1   | • Fixed subsection display: subsections now show correctly regardless of user scope <br> • Fixed SessionInterrupted error: reduced session writes in section management <br> • Scope toggle now accepts explicit target state to prevent race conditions <br> • Improved error messaging in Arabic for scope operations |
| v1.3.0   | • **Section table context menu**: right-click on table rows for Edit/Delete actions <br> • **View Subsections modal**: sections with M2M subsections show linked items in a modal <br> • AJAX-based section deletion with related-record protection <br> • Auto-generated tables now include row data attributes for JS binding |
| v1.3.1   | • Auto-generated section filters now include date range pickers (from/to) with flatpickr integration <br> • Added clarifying inline comments to complex view logic <br> • Fixed login Enter key submission <br> • Pypi Release |
| v1.3.2   | • Fixed Readme file and added detailed instructions |
| v1.3.3   | • Optimized form and filters auto generation and layout |
| v1.3.4   | • Added global head and scripts injection |
| v1.3.5   | • Switch to Database JSON attached to user profile for consistent prefrences accross devices |
| v1.3.6   | • Fixed theme picker popup positioning in LTR mode (CSS logical properties) |
| v1.4.0   | • **Comprehensive Translation Framework**: table headers, filter labels/placeholders, and template strings now resolved from `translations.py` per user language <br> • Tables, filters, and templates (`manage_users`, `user_activity_log`, `manage_sections`) fully translated <br> • Reset Defaults now purges sidebar reordering from DB and localStorage <br> • Reset UI redesigned to match other options (inline Confirm/Cancel animation) <br> • Fixed activity log actions always showing in Arabic regardless of language (duplicate `get_table_kwargs`) |
| v1.4.1   | • Translation related fixes and UI enhancements |
| v1.5.0   | • **Global Dynamic Autofill Feature**: Automatically fill forms from related ForeignKeys (e.g. User Profile data) with smart clearing and toggle controls |
| v1.5.1   | • Autofill fixes: Resolved 500/404 errors during clearing, refined toggle behavior, and standardized console logging |
| v1.5.2  | • Completely Restructured README for a clearer understanding of the system and its setup |
| v1.6.0  | • **Context Menu**: Added global, data-driven context menu support for interactive elements |
| v1.6.1  | • **Translation Upgrade**: Improved translation system and coverage <br> • Various bug fixes and stability improvements |
| v1.6.2  | • **Custom Password Form**: Refactored password change form with dynamic translations and helpful descriptions <br> • **RTL/LTR Fixes**: Fixed Login screen text direction in English mode <br> • **Profile Translations**: Fully translated profile view and edit pages |
| v1.6.3  | • **Login Enhancements**: Added language switcher, session-based language persistence, and fixed RTL alignment bug <br> • **Smart Redirects**: Login now automatically redirects authenticated users and supports `home_url` config fallback <br> • **Unified Translations**: Refactored internal translation helper to support anonymous sessions |
| v1.7.0  | • **Universal Fetcher**: Added a global, smart single-file and multi-file downloader<br> • Added a data-driven Excel exporter for querysets with auto-hidden fields, and an optional exclude fields list |
| v1.7.1   | • **Enhanced Activity Logging**: Added JSON-based detail tracking for all updates (Diffs), including masked password changes and file download specifics <br> • **Log Deduplication**: Implemented smart merging of concurrent User/Profile updates into single log entries <br> • **Double Submit Prevention**: Added global JavaScript protection to disable submit buttons immediately after click <br> • **Profile UI**: Updated profile view to display detailed log history with formatted diffs |
| v1.7.2   | • **Premium Modal UI**: Overhauled all section and activity modals with the glass-card/info-label design from the Profile view <br> • **Dark Mode Accessibility**: Increased glass-card opacity to 0.92 and refined shadows to ensure data visibility in dark themes <br> • **Double Modal Fix**: Resolved redundant script inclusion causing duplicate modal triggers <br> • **Log Refinement**: Standardized activity log details with profile-consistent typography and theme-aware badges |
| v1.7.3   | • **Dashboard Activity Chart**: Added a built-in activity chart powered by Plotly.js, visualizing system activity for the last 24 hours. <br> • **Responsive Chart**: Chart automatically resizes with the window and sidebar toggles using `ResizeObserver`. |
| v1.7.5   | • **Unified User Detail Modal (2026-02-17)**: AJAX-driven modal for user details, integrating activity timeline and migrating context menu events for Users. |
| v1.7.6   | • **Intuitive Double-Click Feedback (2026-02-17)**: Automatic pointer cursor for dblclick targets. |
| v1.7.7   | • **Navigation Refactor**: Moved Profile to Sidebar and simplified Titlebar to a unified "Username \| Logout" button. |
| v1.7.8   | • **UI Refinement**: Moved user's name outside the sign-out button in the titlebar for better separation. |
| v1.7.9   | • **Premium Navigation Stability**: Finalized logout button with a `warning` theme, fixed icon "wobble" transitions, and tighter 8px spacing for a high-end, glitch-free feel. |
| v1.7.10  | • **Responsive 2FA UI**: Fixed two-factor authentication method rows to stay side-by-side on small screens, preventing the enable buttons and labels from stacking. |
| v1.7.11  | • **Theme Fixes**: Resolved issue where language picker options appeared white in dark theme by adding proper CSS variable overrides in `dark.css`. |
| v1.7.12  | • **Offline Twemoji Flags**: Added local hosting for the Twemoji Country Flags web font polyfill to ensure flag emojis render correctly on Windows without external CDN dependencies. |
| v1.8.0   | • **Dynamic Multi-Language Tutorial**: Completely refactored the guided tutorial system. The tutorial is now fully dynamic based on the current URL path (`/sys/`, `/sys/sections/`, `/sys/users/`, etc.), supports full English/Arabic translations, and intelligently targets elements even if they change positions. |
| v1.8.1   | • **Auto Profile Creation**: Added a post-save signal to automatically create a Profile instance whenever a new User is created to prevent profile missing errors. <br> • **Sidebar Accordions State**: Updated sidebar accordions to decouple from the active URL and each other, strictly persisting each accordion's open/close state independently based purely on user interaction. |
| v1.9.0   | • **Dynamic Modal Reconstruction**: Successfully restored the deleted `DynamicModalManagerView` and `DynamicModalDeleteView` functionality. <br> • Standardized dynamic modals with a unified AJAX-driven combined view (List + Form) for auxiliary models. <br> • Integrated related-record protection in deletion views with localized error messaging. |
| v1.9.1   | • **Views Modularization**: Refactored monolithic `views.py` into a `views/` package with dedicated modules: `general.py`, `users.py`, `twofa.py`, `sections.py`, `scopes.py`, `activitylog.py`, `profile.py`, `sidebar.py` <br> • Added role-distinguishing top comments to all functions and classes |
| v1.9.2   | • **Comprehensive README Overhaul**: Added extensive developer how-to documentation for Dynamic Modal Manager, 2FA, Template Tags, Double-Submit Prevention, Preferences API <br> • Expanded ScopedModel docs (dual managers, ScopeForeignKey, soft-delete), Section Mode (class resolution order, customization hooks), Context Menu (permission filtering, event actions, action schema), Autofill (API endpoints), and Activity Logging (safe_log, diffs, masking) <br> • Updated file structure to reflect views/ package refactor |
| v1.10.0  | • **ScopedModel Audit Trail**: Added 6 built-in fields (`created_at`, `updated_at`, `created_by`, `updated_by`, `deleted_at`, `deleted_by`) with `editable=False` to ScopedModel <br> • **Auto-Populated Actors**: `save()` override auto-populates `created_by`/`updated_by` from thread-local middleware |
| v1.10.1  | • **Global Soft-Delete**: `delete()` overridden to perform soft-delete; added `soft_delete()`, `restore()`, `hard_delete()` methods |
| v1.10.2  | • **UserActivityLog Refactor**: Removed redundant `user`/`timestamp` fields in favor of inherited `created_by`/`created_at` with backward-compat properties <br> • **Centralized Logging**: Enhanced `log_user_action()` utility — replaced all manual `UserActivityLog.objects.create()` calls across signals, fetcher, and views |
| v1.10.3  | • **Removed all `hasattr` guards** in views (fields always exist now) <br> • Simplified `ScopedManager` (no conditional `deleted_at` check) |
| v1.11.0  | • **Sidebar Accordion Refinement**: Added dashboard navigation behavior to the built-in "System" group header, matching the split-accordion behavior of other functional groups |
| v1.11.1  | • **Sidebar Parent Reordering**: Enabled reordering for entire accordion groups with dedicated persistence and FOUC prevention |
| v1.11.2  | • **Premium Dark Theme Legibility**: Comprehensive overhaul of contrast, outlines, and visibility for all UI components in dark mode. <br> • **Improved Text Contrast**: Enforced high-contrast labels and text utility classes for maximum readability on dark backgrounds. <br> • **Preserved Utility Borders**: Protected Bootstrap `border-*` classes from global theme overrides |
| v1.11.3  | • **Separate Accordion URL Button**: Modified sidebar accordion headers to display a separate, non-intrusive URL button (`>`/`<`) for groups with dashboard links, preserving default accordion toggle behavior without JS routing conflicts |
| v1.11.4  | • **Sidebar RTL Precision**: Synchronized direction context with sidebar templatetags to ensure correct chevron mirroring in RTL layouts. <br> • **Padding Optimization**: Refined RTL padding for sidebar items and accordion buttons to pull navigation elements flush with the sidebar borders, eliminating "phantom" side gaps. |
| v1.11.5  | • **Dynamic Sidebar Width**: Converted sidebar layout to `col-auto` with `fit-content` min-width on large screens, allowing it to adapt to the longest item or accordion parent. <br> • **Flexible Content Layout**: Updated the main content area to utilize fluid grid sizing, ensuring it seamlessly fills the workspace adjacent to the dynamic sidebar. |
| v1.12.0  | • **Smart Filter Controls**: Enhanced `setup_filter_helper` to conditionally render the reset (cancel) button. It now only appears when active filters with non-empty values are present, reducing UI clutter. <br> • **Alignment Refinement**: Standardized global filter alignment to `start` for improved visual hierarchy. |
| v1.12.1  | • **Universal Filter Standardization**: Migrated `Users`, `Sections`, and `Activity Log` views to the unified `setup_filter_helper` utility. All core lists now benefit from conditional clear buttons, `Hidden` GET parameter preservation, and consistent responsive layouts. |
| v1.12.2  | • **`get_model_classes` Performance Enhancement**: Upgraded `get_model_classes` utility to use dictionary caching and `LazyModelClasses` for lazy evaluation, reducing module import overhead during the request loop. <br> • **`get_model_classes` Overrides**: Added support for explicit convention overrides via the `overrides` argument or the model-level `model_classes_overrides` attribute. |
| v1.12.3  | • **Migrator Component Integration**: Integrated `migrator.py` into the `microsys/management/commands` package to centralize and reuse initial deployment logic across projects. Added `-mm` (make-migrations) flag to `migrator.py` to safely force makemigrations. |
| v1.12.4  | • **Dynamic Connected Profiles Failsafe**: Universal `post_save` signal that introspects OneToOne User profiles globally and auto-creates them with type-safe dummy values, bypassing database requirements for flawless system-agnostic onboarding. |
| v1.12.5  | • **HR Validation Overhaul**: Shipped powerful ProfileCompletionMiddleware and EmployeeSetupForm that globally trap unverified dummy users upon login, forcing them to complete their profiles before gaining system access. |
| v1.12.6  | • **Global Context Menus**: Refactored AutoTable generic context menus to dispatch decoupled `micro:record:edit` events, empowering standard views to handle routing and Custom Views to pipe explicitly into Dynamic Modals without boilerplate code. |
| v1.12.7  | • **Reusable Global List Template**: Added `microsys/helpers/global_list.html` to standardize form/filter/table list views project-wide. <br> • **Event Rename**: Renamed `micro:section:*` → `micro:record:*` for semantic accuracy across AutoTable, section_manager.js, and all consumer templates. |
| v1.13.0  | • **User Modal CRUD**: Migrated User add/edit from separate pages into `DynamicModalManagerView`. <br> • **Smart Form Kwargs**: Auto-introspects form `__init__` signatures and passes `user`/`request` if accepted. <br> • **`form_class` / `template_name` Overrides**: URL-level customization of form class and template. <br> • **`show_table` / `show_form` Flags**: Render form-only, table-only, or combined. <br> • **`handles_save` Flag**: Forms managing their own save cycle (password hashing, M2M). <br> • **`get_modal_context()` Convention**: Models can define this method to auto-inject extra context into modals. <br> • **`UserModalForm`**: Smart proxy delegating to creation/change forms based on instance. |
| v1.14.0  | • **Scope Auto-Injection**: Monkey-patches `ModelForm`, `FilterSet`, and `Table` in `AppConfig.ready()` to auto-inject and manage scope for any `ScopedModel`-based component — zero developer effort. <br> • Auto Scope on Save: `ScopedModel.save()` now auto-sets scope from user's profile (like `created_by`). <br> • ScopeForeignKey Fix: `formfield()` no longer returns `None` when scopes are disabled. |
| v1.15.0  | • **Universal Auto-Translation**: Augmented `AppConfig.ready()` patches to automatically translate Table headers, Filter labels, and ModelForm field labels by looking up `verbose_name` or `label` in the project's translation dictionary. Supports `tbl_` and `label_` prefixes with zero developer effort. |
| v1.15.1  | • **Translation Language Resolution Fix**: Rewrote `get_strings()` to use the same robust language fallback as `microsys_context`: user profile prefs → session → `MICROSYS_CONFIG['default_language']` → `get_language()` → `'ar'`. Previously the function skipped profile prefs and `default_language`, causing Django's default `en-us` to override the intended Arabic default. <br> • **Table Patch Kwargs Fix**: Fixed `TypeError` in `_patched_init` where microsys-specific kwargs (`translations`, `request`, `model_name`) were forwarded to django-tables2's `Table.__init__()`. |
| v1.15.2  | • **Micro Context Menu Dark Mode Enhancement**: Updated hover background color for context menu items in dark mode to improve contrast and reduce visual harshness. |
| v1.15.3  | • **Universal Context Menu Translation**: Augmented the `Table.__init__` patch in `AppConfig.ready()` to automatically and globally translate `label` properties inside `row_attrs['data-micro-actions']` dynamically based on the current user linguistic preferences. |
| v1.15.4  | • **Translation System Streamlining**: Completely overhauled the translation system to make `get_strings()` the single, smart source of truth. Removed all redundant wrappers from `utils.py` (`_get_default_strings`, `_get_request_lang`, `_get_request_translations`), `forms.py` (`_get_form_strings`), and `filters.py` (`_get_filter_strings`). All views, templates, tables, forms, and filters now route directly through `translations.get_strings()` which automatically handles request/session/profile context language resolution internally. |
| v1.15.5  | • **Translation Signature Fix**: Fixed `get_strings` function call and replaced removed `_get_request_lang` usages in `utils.py` and `models.py` with Django's native language detection to prevent AttributeError during form generation. |
| v1.15.6  | • **M2M Serialization Fix**: Wrapped lazy translation proxies (`verbose_name`, `verbose_name_plural`) with `str()` in `utils.py` and `views/sections.py` to prevent `TypeError: Object of type Promise is not JSON serializable` resulting in 500 errors when viewing section details with M2M relations via Context Menu. |
| v1.15.7  | • **Context Menu Smart View Duplicate Data Fix**: Fixed a bug in `collect_related_objects` where M2M relations were processed twice (via both `auto_created` reverse accessors and `many_to_many` forward accessors), causing duplicate cards in the Smart View modal. Added tracking to ensure relations are only added once. <br> • **Modal CSS Fix**: Replaced hardcoded `text-white-50` class with theme-adaptive `text-muted` in `section_manager.js` to ensure related records list items are visible in both light and dark themes. |
| v1.15.8  | • **Filter Layout Suffix Fix**: Fixed hardcoded fallback strings `'from'` and `'to'` in `set_field_attrs` to properly consult the mapped translation dictionary keys `'filter_from'` and `'filter_to'` when computing translated placeholders for range filters (`__gte` and `__lte`). |
| v1.15.9  | • **Leftover `_get_default_strings` Fix**: Replaced two remaining references to the removed `_get_default_strings()` function in `utils.py` (`_build_generic_detail_context` and `_build_generic_table_class`) with `get_strings()`. These stale references caused `NameError` → 500 Internal Server Error when the Dynamic Modal Manager auto-generated tables/detail views for models like `SystemSettings`. |
| v1.16.0  | • **Interactive User Wizard**: Transformed user creation and editing into an interactive 2-step wizard (Account Details & Permissions) within the dynamic modal system. <br> • **Dynamic Permission Translation**: Implemented a system-wide patch to dynamically translate permission prefixes and labels based on the active language. <br> • **Permission Widget Polishing**: Fixed "Select All" functionality at both App and Model levels in the permission widget using event delegation for reliable AJAX support. <br> • **Modal Flow Optimization**: Updated the dynamic modal success handler to trigger a parent page reload specifically for the user management flow, ensuring the list view is always synchronized with changes. |
| v1.17.0  | • **Modern UX & Branding Overhaul**: Systematic enhancement of the titlebar and sidebar. <br> • **User Intelligence Center**: Replaced legacy titlebar buttons (Home, Help, Logout) with a modern, circular user trigger. <br> • **Advanced User Dropdown**: Implemented a professional, rectangular glass-morphism dropdown activated by the user icon. Features real-time info text on the left and a high-fidelity image preview on the right. <br> • **Fixed Dropdown Toolbar**: Integrated specialized toolbar at the bottom of the user dropdown containing Profile, Manage Users (for staff), Activity Log, and System Options links. <br> • **Sidebar Streamlining**: Deprecated and removed the `system_group` accordion and its associated dashboard elements to simplify navigation. <br> • **Circular Login Interface**: Introduced a sleek, circular login icon for unauthenticated users. |
| v1.17.1  | • **UI Optimization**: Reduced user button height and padding in the titlebar for a more compact and refined navigation experience. |
| v1.17.2  | • **Dark Mode Refinement**: Fixed dashboard hero section gradient in dark mode for a more premium, high-contrast appearance. |
| v1.17.3  | • **UI Cleanup**: Removed decorative pseudo-element from hero section background to ensure a clean, glitch-free visual across all themes. |
| v1.17.4  | • **User Hub Dark Mode**: Complete dark theme overrides for the user trigger and dropdown hub, featuring enhanced glass-morphism and high-contrast toolbars. |
| v1.17.5  | • **Avatar Fix**: Enforced circular shape and fixed dimensions for titlebar user avatars to prevent layout issues with square images. |
| v1.17.6  | • **User Hub UX Optimization**: Prevented automatic collapse of the user hub dropdown when interacting with tutorial controls or the sidebar theme picker. |
| v1.17.7  | • **Modern Tooltips**: Replaced native browser tooltips in the User Hub with custom, high-fidelity glass-morphism tooltips for a more premium toolbar experience. |
| v1.18.0  | • **First-Launch Setup Wizard**: Added `/sys/setup/` onboarding for branding, languages, translations, and global sidebar configuration, while keeping System Settings editable later from Options. <br> • **Resolver-Driven Sidebar Builder**: Replaced suffix-based discovery with reversible URL discovery and a two-pane builder with group selection, add-all/remove-all controls, and persistent home destination handling. <br> • **Navigation Cleanup**: Excluded Microsys, Django admin, and health-check routes from discovered application navigation. |
| v1.18.1  | • **Theme-Aware Setup Builder**: Refactored the first-launch sidebar builder to derive its surfaces, text, active states, and tree accents from shared Microsys theme tokens instead of hardcoded colors. <br> • **Shared Control Styling**: Wired setup search, home destination, and inspector inputs onto existing `glass-input` styling for consistent appearance across themes. |
| v1.18.2  | • **Theme Fallback Fix**: Added a guaranteed default `light` theme path so titlebar and other theme-scoped surfaces no longer render transparent when no theme preference is saved. <br> • **Sidebar Toggle Polish**: Refined the titlebar sidebar toggle with a proper default surface and matching dark-theme treatment. |
| v1.18.3  | • **System Default Theme**: Added `SystemSettings.default_theme` and `MICROSYS_CONFIG['default_theme']` fallback support so new users inherit a configurable default look until they save their own theme preference. <br> • **Setup Theme Picker**: Added the same circular theme chooser from Options to first-launch setup beside default language, with live preview while editing the system default. |
| v1.18.4  | • **Pre-Setup Branding Cleanup**: Removed the legacy Arabic system-name default so fresh and unconfigured installs no longer surface `ادارة النظام` before setup is completed. <br> • **Blank Arabic Setup Field**: The Arabic system-name field now starts empty during first launch, while runtime branding continues to fall back to `microSYS` until the developer saves real names. |
| v1.18.5  | • **Shared Language Picker UI**: Replaced the setup default-language dropdown with the same language-card toggle UI used in Options, so language and theme selection now feel consistent during first launch. <br> • **Setup State Preservation**: Applying a setup language change now preserves the wizard step and unsaved text/JSON/sidebar values across the reload instead of resetting the onboarding form. |
| v1.18.6  | • **Immediate Setup Language Switching**: Removed the extra Apply action from first-launch setup so language cards now switch the UI immediately, matching the instant-feedback feel of the theme picker. <br> • **State-Safe Language Reloads**: The immediate setup language switch still preserves the current wizard step and unsaved onboarding values before reloading the page. |
| v1.18.7  | • **Setup Form Initial Sync Fix**: Corrected the first-launch System Settings form so cleaned singleton defaults are pushed into `self.initial` after form construction, preventing stale legacy values like `ادارة النظام` from rendering in the Arabic name field. |
| v1.18.8  | • **Optional Titlebar Home Target**: Stopped forcing the titlebar Home button to follow a top-level sidebar item, so setup can leave Home on its normal system destination without adding an Index entry to the sidebar. <br> • **Builder Home Selector Cleanup**: The sidebar builder now offers a default “use the titlebar Home button link” option instead of auto-selecting the first sidebar item or disabling the control when no top-level entries exist. |
| v1.18.9  | • **Unified Runtime Sidebar Tree**: Replaced the live sidebar’s split auto-items/accordion-groups render path with the same single tree model used by the first-launch setup builder, so saved Microsys sidebar structure now renders directly at runtime. <br> • **Tree-Based Personal Reordering**: Reworked live sidebar reordering to save a user-specific tree override instead of juggling separate root/group/localStorage order buckets, while still merging in newly added base sidebar items from system setup. |
| v1.18.10 | • **Global Home URL Setting**: Moved Home selection out of the sidebar builder and into general System Settings, so developers can choose any discovered page as the project-wide Home destination or type a custom URL directly. <br> • **Sidebar/Home Decoupling**: Stopped letting sidebar configuration implicitly override `home_url`, and reset the builder’s old Home selector so sidebar structure no longer dictates the titlebar Home button. |
| v1.18.11 | • **Inspector Two-Column Layout**: Reworked the setup sidebar inspector into a cleaner two-column layout, with label/icon fields on one side and the icon chooser on the other. <br> • **Expanded Scrollable Icon Picker**: Greatly increased the available Bootstrap icon suggestions and moved them into a capped inline-scroll picker so the inspector stays compact while offering many more choices. |
| v1.18.12 | • **Broader Curated Icon Set**: Expanded the setup inspector’s icon suggestions to a much more diverse, verified set covering navigation, storage, finance, admin, communication, scheduling, and data-oriented icons. |
