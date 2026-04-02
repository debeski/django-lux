# System Settings Transition to UI-Driven Configuration

Migrate system configuration (name, languages, logos) from the static `MICROSYS_CONFIG` in `settings.py` to a database-backed [SystemSettings](file:///home/debeski/xPy/microsys-pkg/microsys/models.py#80-97) model. This plan introduces a mandatory setup wizard that appears on first login until the system is configured.

## Proposed Changes

### [microsys]

#### [MODIFY] [models.py](file:///home/debeski/xPy/microsys-pkg/microsys/models.py)
- Add `is_configured` field (BooleanField, default=False) to [SystemSettings](file:///home/debeski/xPy/microsys-pkg/microsys/models.py#80-97).
- Update `SingletonModel.load()`:
    - If `created=True` during `get_or_create`, check `settings.MICROSYS_CONFIG`.
    - If `MICROSYS_CONFIG` contains a [name](file:///home/debeski/xPy/microsys-pkg/microsys/models.py#211-214), set `is_configured=True` automatically (seeding from codebase).
    - This ensures existing projects don't suddenly trigger the wizard if they already have config in code.

#### [MODIFY] [utils.py](file:///home/debeski/xPy/microsys-pkg/microsys/utils.py)
- Refactor [get_system_config()](file:///home/debeski/xPy/microsys-pkg/microsys/utils.py#67-151):
    - Prioritize [SystemSettings](file:///home/debeski/xPy/microsys-pkg/microsys/models.py#80-97) (DB) values if they are set.
    - Add logic to detect if the system is truly configured (checks `is_configured` flag).

#### [NEW] [middleware.py](file:///home/debeski/xPy/microsys-pkg/microsys/middleware.py)
- Add `SystemSetupMiddleware`:
    - Checks `SystemSettings.is_configured`.
    - If `False` and user is a superuser:
        - Redirect to `manage_users` (or a default safe landing page) if they try to access other admin pages.
        - Inject a flag into the request context (or just let the context processor handle it).
    - > [!IMPORTANT]
    - > This ensures that if a user bypasses the modal (e.g. by deleting it via devtools), they are still limited in what they can do until configuration is saved.

#### [MODIFY] [context_processors.py](file:///home/debeski/xPy/microsys-pkg/microsys/context_processors.py)
- In [microsys_context](file:///home/debeski/xPy/microsys-pkg/microsys/context_processors.py#130-284), fetch `SystemSettings.is_configured`.
- If `False` and user.is_superuser, set `context['TRIGGER_SYSTEM_SETUP'] = True`.

#### [MODIFY] [forms.py](file:///home/debeski/xPy/microsys-pkg/microsys/forms.py)
- Refactor [SystemSettingsForm](file:///home/debeski/xPy/microsys-pkg/microsys/forms.py#823-930) into a **Wizard**:
    - Use `Div(..., css_class="wizard-step wizard-step-1")`, etc.
    - Add `ms-btn-prev`, `ms-btn-next`, and `ms-btn-submit` in `FormActions`.
    - In [save()](file:///home/debeski/xPy/microsys-pkg/microsys/forms.py#769-783), set `instance.is_configured = True`.
- This reuses the [wizard.js](file:///home/debeski/xPy/microsys-pkg/microsys/static/microsys/users/js/wizard.js) logic already present in the package.

#### [MODIFY] [base.html](file:///home/debeski/xPy/microsys-pkg/microsys/templates/microsys/base.html)
- Add a script block that checks `TRIGGER_SYSTEM_SETUP`.
- If true, dispatch `micro:dynamic_modal:open` event targetting the [SystemSettings](file:///home/debeski/xPy/microsys-pkg/microsys/models.py#80-97) modal.
- Use the `backdrop: 'static', keyboard: false` options for the modal (via a new parameter or custom JS trigger) to make it persistent.

## Verification Plan

### Automated Tests
- Since I cannot run migrations, I will ask the USER to run `python manage.py makemigrations` and `python manage.py migrate` after the changes.
- Test [get_system_config](file:///home/debeski/xPy/microsys-pkg/microsys/utils.py#67-151) logic via a scratch script to ensure DB values override `MICROSYS_CONFIG`.

### Manual Verification
1. **Fresh Install Scenario**:
   - Manually set `is_configured = False` in the database.
   - Log in as a superuser.
   - Verify the System Settings modal appears automatically.
   - Verify the modal cannot be closed by clicking outside or pressing Escape.
   - Fill in the settings and save.
   - Verify the modal closes and does not appear again on subsequent page loads.
2. **Transition Scenario**:
   - Have `MICROSYS_CONFIG` set in `settings.py`.
   - Verify [SystemSettings](file:///home/debeski/xPy/microsys-pkg/microsys/models.py#80-97) inherits these values if it was just created (seeding).
   - Change a value in the UI and verify it takes precedence over the `settings.py` value.

#### P.S. "an addition to the original plan above".
   - rework the sidebar to be more naturally integrated in microsys as a whole.
   - discover urls worthy of being in the sidebar using apps as their parents.
   - add an interactive step in the setup wizard to select which apps/urls to include in the sidebar.
   - add a step in the setup wizard to select names and icons for selected items or include in the same previous step using a dropdown with bootstrap icons for icon selection. either way, make it so that the user can select names and icons for selected items.
   - make a dedicated table/model in the DB for the selected sidebar items. with name, url, and icon.
   - link the user-preferences model to the new sidebar items table for ordering
   - and link the user permissions model to the new sidebar items table for visibility.
   - in the user creation permission management step, the app/group checkboxes will also be used to determine visibility of the sidebar items. for example, if the user selects the "storage" app/group, the "Storage" sidebar group accordion with selected models as items will be visible to that user. this might be done by linking the url items to the model default view permission. or maybe by linking the url items to the app/group permissions.
   - either way the current way of setting EXTRA_GROUPS in the sidebar configuration with setting permission individually for each entry needs to be implemented into an interactive way in the sidebar setting steps.