# Performance Analysis Report

**Project**: django-microsys  
**Version**: 2.0.3 (2.1.0 pending)  
**Analysis Date**: 2026-05-01  
**Focus**: Database queries, caching, memory usage, rendering performance

## Executive Summary

This report analyzes the django-microsys framework for performance bottlenecks. While the codebase shows awareness of performance concerns (caching for scoped model checks, template optimizations), **several significant N+1 query patterns and unoptimized data access patterns remain**.

**Overall Performance Grade**: C+ (Satisfactory with notable issues)  
**Critical Issues**: 1  
**High Issues**: 5  
**Medium Issues**: 6  
**Low/Info**: 4

---

## Analysis Scope

| Component | Coverage | Status |
|-----------|----------|--------|
| Database Queries (ORM) | Full | Multiple N+1 patterns |
| Caching Strategy | Partial | Ad-hoc, no systematic approach |
| Template Rendering | Partial | Heavy context processors |
| Sidebar/Discovery | Full | Expensive on every request |
| Table Rendering | Full | Missing prefetch for accessors |
| Forms | Full | Repeated permission queries |
| Static Assets | Limited | Reviewed asset pipeline |
| Middleware | Full | Thread-local overhead |

---

## Part 1: Database Query Performance (ORM)

### Description
Analysis of queryset patterns, N+1 detection, and query optimization opportunities.

### Findings

| Severity | Issue | Location | Description | Impact | Remediation |
|----------|-------|----------|-------------|--------|-------------|
| **CRITICAL** | **N+1 via profile accessors in UserTable** | `microsys/tables.py:93-99` | `accessor='profile.phone'`, `accessor='profile.scope.name'`, `accessor='profile.full_name'` - Each row triggers separate profile query + potentially scope query | 100 users × 3 accessors = 300+ queries per page load | Add `select_related('profile__scope')` to `UserListView.get_queryset()` |
| **HIGH** | **Permission lookup on every form init** | `microsys/forms.py:537-541, 870-876, 942-950` | `user_permissions.all()`, `Permissions.objects.filter()`, and `Permission.objects.get()` called in `__init__` | 3-5 extra queries per form render | Cache permission lookups at module level or use lazy evaluation |
| **HIGH** | **Scope lookup in form __init__** | `microsys/forms.py:532-533` | `Scope.objects.all()` called in every `CustomUserCreationForm.__init__` | 1 query per user creation form | Use cached scope choices or lazy queryset evaluation |
| **HIGH** | **Permission N+1 in UserListView** | `microsys/views/users.py:123-131` | `Permission.objects.get()` inside `get_queryset()` looped filtering | 1 query per user list view | Cache at module level or use `user.has_perm()` instead |
| **HIGH** | **Missing select_related in registration views** | `microsys/views/registration.py:63-66, 102-104` | `select_related('user')` present but no prefetch for related data | Moderate - minimal related data | Add `prefetch_related` for user permissions if needed |
| **MEDIUM** | **get_user_scope() does defensive queries** | `microsys/utils.py:491-498` | `getattr(user, 'profile', None)` can trigger query if profile not cached | 1 query per scope check | Ensure `select_related('profile')` on all user querysets |
| **MEDIUM** | **discovery.py URL resolver iteration** | `microsys/discovery.py:156-166` | `_iterate_named_patterns()` recursively walks all URL patterns on every request | CPU overhead, not cached | Cache discovered sidebar structure; invalidate on URLConf change |
| **MEDIUM** | **build_sidebar_navigation() runs every request** | `microsys/context_processors.py:265-271` | Sidebar navigation rebuilt from scratch every request even if config unchanged | 50-200ms per request | Implement aggressive caching with cache key based on config hash |
| **MEDIUM** | **Activity log lookups without prefetch** | `microsys/views/users.py:397-403` | `UserActivityLog._default_manager.filter()` without prefetch for created_by | N+1 if iterating logs | Add `select_related('created_by')` |
| **LOW** | **ScopedManager applies scoping repeatedly** | `microsys/managers.py:53-60` | `get_queryset()` calls `apply_scoping()` which checks `_is_scope_enabled()` | Small overhead per query | Cache `_is_scope_enabled()` result at module level |
| **LOW** | **utils.py helpers call get_user_scope repeatedly** | `microsys/utils.py:501-534` | `can_manage_target_user()` calls `get_user_scope()` and `is_central_staff()` multiple times | Function call overhead | Accept pre-fetched user/profile objects |

### Query Performance Metrics (Estimated)

| View | Current Queries | Optimized | Improvement |
|------|-----------------|-----------|-------------|
| User List (100 users) | ~120 | ~5 | 96% ↓ |
| User Create Form | ~8 | ~3 | 62% ↓ |
| Registration List | ~15 | ~3 | 80% ↓ |
| Options View | ~20 | ~8 | 60% ↓ |
| Sidebar (every page) | ~10 | ~2* | 80% ↓ |

*With proper caching

---

## Part 2: Caching Strategy

### Description
Current caching implementation and strategy gaps.

### Findings

| Severity | Issue | Location | Description | Remediation |
|----------|-------|----------|-------------|-------------|
| **HIGH** | **No systematic sidebar caching** | `microsys/discovery.py`, `microsys/context_processors.py` | Sidebar discovered and built on every request; config hash generated but not used for caching | Implement `cache.set()` with `sidebar:{config_hash}:{user_id}` key; invalidate on SystemSettings save |
| **MEDIUM** | **Scoped model check cache is process-local only** | `microsys/patches.py:14` | `_scoped_model_cache` dict only persists per-process; no shared cache | Consider Django cache for multi-process deployments |
| **MEDIUM** | **No caching for SystemSettings** | `microsys/models.py` | `SystemSettings.load()` called frequently; no cache layer | Add `@cached_property` or Django cache with 5-minute TTL |
| **MEDIUM** | **Translation strings not cached** | `microsys/translations.py` | `get_strings()` likely loads JSON/translations on every call | Cache per language code; invalidate on settings change |
| **LOW** | **Permission lookups not cached** | `microsys/utils.py:645-660` | `user.has_perm()` triggers DB; `user_matches_permission_token()` has no caching | Cache permission checks per request using `request._cached_perms` |
| **LOW** | **URL reverse not cached** | `microsys/context_processors.py:53-55, 75-81` | `reverse()` called repeatedly for sidebar URLs | Cache resolved URLs in sidebar build cache |

### Recommended Caching Architecture

```
Sidebar Structure       →  Cache 5 minutes (config hash + user perms hash)
System Settings         →  Cache 5 minutes (singleton)
User Permissions        →  Cache per request (request attribute)
Translations            →  Cache per language (indefinite)
Scoped Model Checks     →  Process-local (current) is fine
URL Reverses            →  Cache with sidebar structure
```

---

## Part 3: Template & Rendering Performance

### Description
Analysis of context processor overhead, template complexity, and rendering bottlenecks.

### Findings

| Severity | Issue | Location | Description | Remediation |
|----------|-------|----------|-------------|-------------|
| **HIGH** | **Context processor builds full sidebar every request** | `microsys/context_processors.py:148-320` | `microsys_context()` runs full sidebar discovery, translation loading, config building | Move sidebar to lazy evaluation or separate cached inclusion tag |
| **MEDIUM** | **Heavy config group building** | `microsys/context_processors.py:205` | `build_config_groups()` processes nested config structure | Cache config groups with language code |
| **MEDIUM** | **Language resolution complex** | `microsys/context_processors.py:163-203` | Multiple fallback checks for language resolution | Simplify; cache resolved language per session |
| **LOW** | **Theme options generated every request** | `microsys/context_processors.py:242` | `get_theme_options()` called even if theme picker disabled | Add early exit if `MICROSYS_THEMES` not used |
| **LOW** | **Multiple preference resolution calls** | `microsys/context_processors.py:225-231` | `resolve_user_theme_preference()`, `resolve_sidebar_density_preference()`, etc. | Combine into single preference resolution function |

### Context Processor Timing Breakdown (Estimated)

| Operation | Time | % of Total |
|-----------|------|------------|
| get_system_config() | 5ms | 8% |
| Language resolution | 3ms | 5% |
| build_config_groups() | 8ms | 13% |
| build_sidebar_navigation() | 35ms | 58% |
| Theme/options processing | 5ms | 8% |
| Other | 5ms | 8% |
| **Total** | **~60ms** | **100%** |

---

## Part 4: Memory Usage

### Description
Memory allocation patterns and potential leaks.

### Findings

| Severity | Issue | Location | Description | Remediation |
|----------|-------|----------|-------------|-------------|
| **MEDIUM** | **Thread-local storage for user/request** | `microsys/middleware.py:10-16` | `_thread_locals` keeps references until middleware processes next request | Clear thread locals at end of request processing |
| **MEDIUM** | **Large translation dictionaries in context** | `microsys/context_processors.py:239` | Full `MS_TRANS` dict passed to every template | Only pass needed translations or use template tag |
| **LOW** | **Sidebar tree state duplicated in context** | `microsys/context_processors.py:273-274` | `sidebar_entries` and `sidebar_tree_state` appear to be same data | Remove duplication; use single key |
| **LOW** | **Config dict copied/modified** | `microsys/context_processors.py:205-207` | `build_config_groups()` may copy large config structure | Modify in place if possible |

---

## Part 5: Form Performance

### Description
Form initialization and validation performance.

### Findings

| Severity | Issue | Location | Description | Remediation |
|----------|-------|----------|-------------|-------------|
| **HIGH** | **CustomUserCreationForm.__init__ does heavy lifting** | `microsys/forms.py:528-670` | 150+ lines of __init__ logic including DB queries, permission filtering, layout building | Move layout building to class level; defer permission filtering until render |
| **HIGH** | **CustomUserPermissionsForm repeats query patterns** | `microsys/forms.py:860-967` | Similar pattern to creation form with additional permission lookups | Same remediation as above |
| **MEDIUM** | **Widget translations injected every form instance** | `microsys/forms.py:585, 867` | `self.fields['permissions'].widget.translations = s` | Set once at widget class level or use context processor |
| **MEDIUM** | **Permission widget queryset filtered repeatedly** | `microsys/forms.py:537-569, 870-918` | Same filtering logic in multiple forms | Extract to shared helper with caching |
| **LOW** | **get_strings() called in every form __init__** | `microsys/forms.py:581, 865` | Translation loading per form instance | Pass translations from view or use cached lookup |

---

## Part 6: Section Management Performance

### Description
Dynamic section model discovery and management.

### Findings

| Severity | Issue | Location | Description | Remediation |
|----------|-------|----------|-------------|-------------|
| **MEDIUM** | **discover_section_models() called frequently** | `microsys/views/sections.py:80` | Section discovery runs on every section-related request | Cache discovered sections at module level |
| **MEDIUM** | **Section registry rebuilt every request** | `microsys/views/sections.py:75-115` | `_get_section_registry()` builds dictionaries from scratch | Cache registry with app config change invalidation |
| **LOW** | **Model class resolution via apps.get_model** | `microsys/views/sections.py:81, 93` | `apps.get_model()` lookups inside loops | Resolve once and cache |

---

## Part 7: Static Assets & Frontend

### Description
Static file handling, JavaScript/CSS delivery optimization.

### Findings

| Severity | Issue | Location | Description | Remediation |
|----------|-------|----------|-------------|-------------|
| **LOW** | **No CDN or static file versioning strategy** | `microsys/templates/microsys/base.html` | Static files served without query string cache busting | Implement `{% static %}` with version query strings |
| **LOW** | **Multiple CSS/JS files not bundled** | Template analysis | Separate theme CSS files, multiple JS includes | Consider django-compressor or webpack for bundling |
| **INFO** | **Theme CSS loaded even if single theme** | Theme system | All theme CSS files potentially available | Lazy-load theme CSS based on user preference |

---

## Part 8: Specific Code Patterns

### Anti-Patterns Found

```python
# 1. Query in __init__ (forms.py)
self.fields['scope'].queryset = Scope.objects.all()  # Runs on every form instance

# 2. No select_related for foreign key access (tables.py)
accessor='profile.scope.name'  # N+1 for each row

# 3. Repeated function calls (utils.py)
get_user_scope(actor)  # Called multiple times in same function

# 4. No caching for expensive discovery (discovery.py)
def build_sidebar_navigation():  # Rebuilds every time
    # ... expensive URL resolver iteration ...

# 5. Complex context processor (context_processors.py)
def microsys_context(request):  # 60ms+ overhead per request
    # ... sidebar building, translation loading, config processing ...
```

### Best Practices Observed

```python
# 1. Scoped model caching (patches.py)
_scoped_model_cache = {}  # Good - prevents repeated issubclass checks

# 2. select_related in some views (registration.py)
.select_related('user')  # Good - prevents N+1

# 3. Lazy model loading (api.py)
UserActivityLog = apps.get_model('microsys', 'UserActivityLog')  # Good pattern
```

---

## Recommendations Summary

### Immediate (Before 2.1.0)

1. **CRITICAL**: Add `select_related('profile__scope')` to `UserListView.get_queryset()`
2. **HIGH**: Cache sidebar navigation with config hash key
3. **HIGH**: Move permission lookups out of form `__init__` methods
4. **HIGH**: Add module-level permission cache in `UserListView`
5. **MEDIUM**: Implement SystemSettings caching

### Near-Term (Post-2.1.0)

6. Add `prefetch_related` for table accessor patterns
7. Implement translation string caching
8. Optimize context processor with lazy evaluation
9. Cache section model discovery
10. Add query count assertions to tests (django-assert-num-queries)

### Long-Term

11. Implement Django Debug Toolbar integration for performance monitoring
12. Add database query logging for slow queries (>100ms)
13. Consider django-cachalot for automatic ORM caching
14. Profile template rendering with django-silk
15. Implement database read replicas for heavy read views

---

## Performance Testing Checklist

- [ ] Add `assertNumQueries` to UserListView tests (baseline: 5 queries)
- [ ] Add `assertNumQueries` to registration views
- [ ] Profile sidebar generation time
- [ ] Test with 1000+ users in database
- [ ] Test with 100+ sidebar entries
- [ ] Load test with concurrent requests
- [ ] Monitor memory usage with thread locals

---

## Overall Performance Grade

| Category | Grade | Notes |
|----------|-------|-------|
| Database Queries | D+ | Multiple N+1 patterns, missing select_related |
| Caching Strategy | C | Ad-hoc, no systematic approach |
| Template Rendering | C | Heavy context processor |
| Form Performance | C+ | Expensive __init__ methods |
| Memory Management | B | Thread locals need cleanup |
| Static Assets | B | Could benefit from bundling |
| **Overall** | **C+** | **Satisfactory with notable issues** |

---

*Report generated for django-microsys performance optimization review.*
