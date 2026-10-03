# Plan: Global API pagination, customers/suppliers dashboard pages, production-readiness report

This plan is written to be executed top-to-bottom by another agent. Do not improvise outside
the stated scope. All `manage.py` commands are run from `src/tarcom/` (where `manage.py` lives)
with the project venv (`.venv`), i.e. `python manage.py ...` with the venv active. Repo root:
`D:\projects\tarcom`. Templates are UTF-8 (Arabic text written literally).

Confirmed decisions (already agreed with the user):

1. Pagination is applied **globally** via `DEFAULT_PAGINATION_CLASS` in `settings.py`
   (`tarcom.utils.pagination.CustomNumberPagination`, page_size=4 — keep the size as is).
   The explicit `pagination_class` on `MaterialViewSet` is removed.
2. The new customers/suppliers dashboard pages copy the **working users flow**
   (`users_list.html` / `user_form.html` / `UserForm` + the User views in
   `base/views/auth.py`). The broken legacy `users/admins/*` templates stay untouched.
3. The existing users page (`users-list`) is filtered to **admins only** (`user_type=admin`).
4. The production validation delivers a **report only**: a new
   `PRODUCTION_CHECKLIST.md` at the repo root. No production code changes.

Warning to record in the report (Part C): global pagination changes every list endpoint's
response from a bare array to `{"count", "next", "previous", "results"}` — a breaking change
for the mobile (Flutter) client, which must read `results`. Server-side nothing can avoid this.

---

## Part A — Global API pagination

### Step 1 — `src/tarcom/settings.py`: register the default pagination class

In the `REST_FRAMEWORK` dict (currently lines ~74-86) add one line:

```python
REST_FRAMEWORK = {
    'DEFAULT_AUTHENTICATION_CLASSES': (
        'rest_framework_simplejwt.authentication.JWTAuthentication',
    ),
    'DEFAULT_SCHEMA_CLASS': 'drf_spectacular.openapi.AutoSchema',
    'DEFAULT_PAGINATION_CLASS': 'tarcom.utils.pagination.CustomNumberPagination',
    'EXCEPTION_HANDLER': 'tarcom.utils.exceptions.custom_exception_handler',
    ...
}
```

Do NOT change `src/tarcom/utils/pagination.py` (page_size 4 is intentional).

### Step 2 — `src/tarcom/api/views/core.py`: drop the per-viewset override

`MaterialViewSet` currently declares `pagination_class = CustomNumberPagination` (line ~70)
and the file imports it at line ~7. Remove BOTH the attribute line and the import line
(`from tarcom.utils.pagination import CustomNumberPagination`). The global default now covers
`MaterialViewSet`, `MaterialCategoryViewSet`, `UnitOfMeasureViewSet`, `SettingsViewSet`
(core.py), `UserViewSet` (auth.py), `FavouriteViewSet` (favourites.py), `OrderViewSet`
(orders.py). No other view file needs changes — do not add `pagination_class` anywhere else.

### Step 3 — Update the API tests to the paginated shape

Every list-endpoint assertion that treats `response.data` as a list must switch to
`response.data['results']`. All test datasets below fit in one page (≤ 3 rows, page_size 4),
so no multi-page traversal is needed. Exact changes:

`src/tarcom/api/tests/core_tests.py` — `test_unauthenticated_can_list_units` (line ~96):

```python
    def test_unauthenticated_can_list_units(self):
        response = self.client.get('/api/units/')
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data['count'], 1)
        self.assertIsNone(response.data['next'])
        self.assertEqual(len(response.data['results']), 1)
```

`src/tarcom/api/tests/favourite_tests.py` — `test_list_favourites_authenticated` (lines ~47-48):

```python
        results = response.data['results']
        self.assertEqual(len(results), 2)
        material_ids = {item['material'] for item in results}
        self.assertEqual(material_ids, {self.material.id, self.other_material.id})
```

`src/tarcom/api/tests/order_tests.py` — three tests:
- `test_customer_can_only_see_own_orders` (lines ~139-140): `len(response.data), 1` →
  `len(response.data['results']), 1`; `response.data[0]['id']` → `response.data['results'][0]['id']`.
- `test_admin_can_see_all_orders` (line ~153): `len(response.data), 2` →
  `len(response.data['results']), 2`.
- `test_order_list_includes_items_count` (line ~243): `response.data[0]['items_count']` →
  `response.data['results'][0]['items_count']`.

`src/tarcom/api/tests/filter_tests.py` — apply the same transformation to EVERY assertion in
these tests (all hit list endpoints):

- `OrderListFilterTest` (class starts ~line 60):
  - `test_search_matches_order_number_phone_and_email`: lines ~101, ~105-106, ~110, ~114.
    `none.data, []` becomes `none.data['results'], []`; `by_email.data[0]['id']` becomes
    `by_email.data['results'][0]['id']`.
  - `test_status_filter_is_case_insensitive`: lines ~125, ~129.
  - `test_payment_status_filter_is_case_insensitive`: lines ~137, ~142.
  - `test_ordering_by_total_amount`: lines ~155, ~158.
  - `test_csv_ordering_is_applied_left_to_right`: line ~170.
  - `test_default_ordering_is_newest_first`: line ~181.
- `CategoryListFilterTest` (~line 184): lines ~194, ~197-199, ~201-204.
- `MaterialListFilterTest` (~line 207): lines ~228, ~231, ~234, ~238-241, ~244-247,
  ~262 (`paired.data`), ~265 (`mismatched.data, []` → `mismatched.data['results'], []`),
  ~273, ~279, ~297.
- `UnitAndSettingFilterTest` (~line 300): lines ~310, ~313, ~316, ~322, ~325-327, ~329-332.
- `FavouriteListFilterTest` (~line 335): lines ~358, ~368, ~378.

The mechanical rule for all of the above: `response.data` / `by_name.data` / `found.data`
etc. → append `['results']` when the value is iterated or compared as a list. Leave every
assertion on error payloads (`response.data['errors']`, `response.data['code']`) untouched —
the custom exception handler is not paginated.

`user_tests.py` and `profile_tests.py` need no changes (verified: no list-endpoint array
assertions).

## Part B — Customers & suppliers dashboard pages (copy of the working users flow)

### Step 4 — `src/tarcom/base/forms.py`: two tiny form subclasses

Append after `UserForm` (line ~127):

```python
class CustomerUserForm(UserForm):
    class Meta(UserForm.Meta):
        widgets = {'user_type': forms.HiddenInput()}


class SupplierUserForm(UserForm):
    class Meta(UserForm.Meta):
        widgets = {'user_type': forms.HiddenInput()}
```

(`UserForm.Meta` currently has no `widgets` key, so this adds it only for the subclasses.
`UserForm.save()` already handles password hashing and `username = email`.)

### Step 5 — `src/tarcom/base/views/auth.py`: the 8 new views + users-list filter

Add `from tarcom.utils.enums import UserType` to the imports.

Append the new views after `UserDeleteView` (end of file):

```python
class CustomerListView(StaffRequiredMixin, ListView):
    model = CustomUser
    template_name = "dashboard/customers/customers_list.html"
    context_object_name = "customers"
    paginate_by = 20

    def get_queryset(self):
        qs = CustomUser.objects.filter(user_type=UserType.CUSTOMER).order_by('-date_joined')
        q = self.request.GET.get('q')
        if q:
            qs = qs.filter(
                Q(email__icontains=q)
                | Q(first_name__icontains=q)
                | Q(last_name__icontains=q)
                | Q(phone__icontains=q)
            )
        return qs


class CustomerCreateView(StaffRequiredMixin, CreateView):
    model = CustomUser
    form_class = CustomerUserForm
    template_name = "dashboard/customers/customer_form.html"
    success_url = reverse_lazy('customers-list')

    def get_initial(self):
        initial = super().get_initial()
        initial['user_type'] = UserType.CUSTOMER
        return initial

    def form_valid(self, form):
        form.instance.user_type = UserType.CUSTOMER
        messages.success(self.request, "تم إضافة العميل بنجاح.")
        return super().form_valid(form)


class CustomerUpdateView(StaffRequiredMixin, UpdateView):
    model = CustomUser
    form_class = CustomerUserForm
    template_name = "dashboard/customers/customer_form.html"
    success_url = reverse_lazy('customers-list')

    def get_queryset(self):
        return CustomUser.objects.filter(user_type=UserType.CUSTOMER)

    def form_valid(self, form):
        form.instance.user_type = UserType.CUSTOMER
        messages.success(self.request, "تم تحديث بيانات العميل بنجاح.")
        return super().form_valid(form)


class CustomerDeleteView(StaffRequiredMixin, ProtectedDeleteMixin, DeleteView):
    model = CustomUser
    http_method_names = ["post"]
    success_url = reverse_lazy('customers-list')
    protected_message = "لا يمكن حذف هذا العميل لارتباطه بطلبات أو بيانات أخرى في النظام."
    deleted_message = "تم حذف العميل بنجاح."

    def form_valid(self, form):
        if self.object == self.request.user:
            message = "لا يمكنك حذف حسابك الحالي أثناء تسجيل الدخول."
            if self.is_ajax_request():
                return JsonResponse({"ok": False, "message": message})
            messages.error(self.request, message)
            return redirect(self.success_url)
        return super().form_valid(form)


class SupplierListView(StaffRequiredMixin, ListView):
    model = CustomUser
    template_name = "dashboard/suppliers/suppliers_list.html"
    context_object_name = "suppliers"
    paginate_by = 20

    def get_queryset(self):
        qs = CustomUser.objects.filter(user_type=UserType.SUPPLIER).order_by('-date_joined')
        q = self.request.GET.get('q')
        if q:
            qs = qs.filter(
                Q(email__icontains=q)
                | Q(first_name__icontains=q)
                | Q(last_name__icontains=q)
                | Q(phone__icontains=q)
            )
        return qs


class SupplierCreateView(StaffRequiredMixin, CreateView):
    model = CustomUser
    form_class = SupplierUserForm
    template_name = "dashboard/suppliers/supplier_form.html"
    success_url = reverse_lazy('suppliers-list')

    def get_initial(self):
        initial = super().get_initial()
        initial['user_type'] = UserType.SUPPLIER
        return initial

    def form_valid(self, form):
        form.instance.user_type = UserType.SUPPLIER
        messages.success(self.request, "تم إضافة المورد بنجاح.")
        return super().form_valid(form)


class SupplierUpdateView(StaffRequiredMixin, UpdateView):
    model = CustomUser
    form_class = SupplierUserForm
    template_name = "dashboard/suppliers/supplier_form.html"
    success_url = reverse_lazy('suppliers-list')

    def get_queryset(self):
        return CustomUser.objects.filter(user_type=UserType.SUPPLIER)

    def form_valid(self, form):
        form.instance.user_type = UserType.SUPPLIER
        messages.success(self.request, "تم تحديث بيانات المورد بنجاح.")
        return super().form_valid(form)


class SupplierDeleteView(StaffRequiredMixin, ProtectedDeleteMixin, DeleteView):
    model = CustomUser
    http_method_names = ["post"]
    success_url = reverse_lazy('suppliers-list')
    protected_message = "لا يمكن حذف هذا المورد لارتباطه بطلبات أو بيانات أخرى في النظام."
    deleted_message = "تم حذف المورد بنجاح."

    def form_valid(self, form):
        if self.object == self.request.user:
            message = "لا يمكنك حذف حسابك الحالي أثناء تسجيل الدخول."
            if self.is_ajax_request():
                return JsonResponse({"ok": False, "message": message})
            messages.error(self.request, message)
            return redirect(self.success_url)
        return super().form_valid(form)
```

Then change `UsersListView.get_queryset` (line ~112) to admins-only. Remove the `user_type`
GET-parameter branch and hardcode the filter:

```python
    def get_queryset(self):
        qs = CustomUser.objects.filter(user_type=UserType.ADMIN).order_by('-date_joined')
        q = self.request.GET.get('q')
        if q:
            qs = qs.filter(
                Q(email__icontains=q)
                | Q(first_name__icontains=q)
                | Q(last_name__icontains=q)
                | Q(phone__icontains=q)
            )
        return qs
```

### Step 6 — `src/tarcom/base/urls.py`: routes

`urls.py` uses `from .views.auth import *`, so the new views are picked up automatically.
Insert after the users routes (line ~18):

```python
    path("dashboard/customers/", CustomerListView.as_view(), name="customers-list"),
    path("dashboard/customers/create/", CustomerCreateView.as_view(), name="customer-create"),
    path("dashboard/customers/<int:pk>/edit/", CustomerUpdateView.as_view(), name="customer-edit"),
    path("dashboard/customers/<int:pk>/delete/", CustomerDeleteView.as_view(), name="customer-delete"),

    path("dashboard/suppliers/", SupplierListView.as_view(), name="suppliers-list"),
    path("dashboard/suppliers/create/", SupplierCreateView.as_view(), name="supplier-create"),
    path("dashboard/suppliers/<int:pk>/edit/", SupplierUpdateView.as_view(), name="supplier-edit"),
    path("dashboard/suppliers/<int:pk>/delete/", SupplierDeleteView.as_view(), name="supplier-delete"),
```

### Step 7 — Templates (4 new files + 1 edit)

**NEW `src/tarcom/templates/dashboard/customers/customers_list.html`** — a copy of
`users_list.html` with: title/breadcrumb "العملاء" (breadcrumb: لوحة التحكم → العملاء);
the whole `actions-dropdown` block (user_type filter form) REMOVED (type is fixed, search
stays); search placeholder "بحث باسم العميل أو البريد أو الهاتف"; loop
`{% for u in customers %}`; edit/delete use `customer-edit`/`customer-delete` with the same
emoji buttons + `js-delete-btn`/`data-delete-url`/`data-object-name` attributes; the add
button links to `customer-create`; empty-row text "لا يوجد عملاء."; keep the pagination
include at the bottom. Full expected content:

```html
{% extends 'dashboard/base.html' %}
{% load static %}

{% block title %}العملاء{% endblock %}

{% block content %}
<div class="content-header">
    <nav class="breadcrumb">
        <a href="{% url 'dashboard' %}">لوحة التحكم</a>
        <i class="separator fas fa-chevron-left"></i>
        <span>العملاء</span>
    </nav>
</div>

<div class="actions">
    <div class="search-container">
        <form method="get" class="search-box">
            <i class="fas fa-search search-icon"></i>
            <input type="text" name="q" placeholder="بحث باسم العميل أو البريد أو الهاتف" value="{{ request.GET.q }}">
        </form>
    </div>
</div>

<div class="table-container">
    <table class="table table-hover">
        <thead>
            <tr>
                <th>البريد الإلكتروني</th>
                <th>الاسم الكامل</th>
                <th>الهاتف</th>
                <th>نوع المستخدم</th>
                <th>الحالة</th>
                <th>إجراءات</th>
            </tr>
        </thead>
        <tbody>
            {% for u in customers %}
            <tr>
                <td>{{ u.email }}</td>
                <td>{{ u.get_full_name|default:"-" }}</td>
                <td>{{ u.phone|default:"-" }}</td>
                <td>{{ u.get_user_type_display }}</td>
                <td>
                    <span class="status {% if u.is_active %}text-success{% else %}text-danger{% endif %}">
                        {% if u.is_active %}نشط{% else %}موقوف{% endif %}
                    </span>
                </td>
                <td>
                    <div class="row-actions">
                        <a href="{% url 'customer-edit' u.pk %}" class="btn-white" title="تعديل" aria-label="تعديل {{ u.email }}">✏️</a>
                        <button type="button" class="btn-white js-delete-btn" data-delete-url="{% url 'customer-delete' u.pk %}" data-object-name="{{ u.email }}" title="حذف" aria-label="حذف {{ u.email }}">🗑️</button>
                    </div>
                </td>
            </tr>
            {% empty %}
            <tr>
                <td colspan="6">لا يوجد عملاء.</td>
            </tr>
            {% endfor %}
        </tbody>
    </table>
</div>

<div class="table-controls">
    <div class="action-button-container">
        <a href="{% url 'customer-create' %}" class="btn btn-brown">إضافة</a>
    </div>
</div>

{% if page_obj %}{% include 'dashboard/pagination.html' %}{% endif %}
{% endblock %}
```

**NEW `src/tarcom/templates/dashboard/customers/customer_form.html`** — a copy of
`user_form.html` with: title `{% if object %}تعديل عميل{% else %}إضافة عميل{% endif %}`;
breadcrumb: لوحة التحكم → العملاء (link `customers-list`) → إضافة/تعديل عميل; the
`user_type` form-group (label + field + errors, lines ~57-63 of user_form.html) replaced by a
bare hidden field render:

```html
                    {{ form.user_type }}
```

(no label, no form-group wrapper — the HiddenInput renders an invisible input whose value
comes from `get_initial` on create and from the instance on edit); everything else stays
identical to user_form.html INCLUDING the avatar `image-picker` block and its trailing jQuery
preview script; the cancel button links to `{% url 'customers-list' %}`.

**NEW `src/tarcom/templates/dashboard/suppliers/suppliers_list.html`** — same as
customers_list.html with: title/breadcrumb "الموردون"; placeholder "بحث باسم المورد أو
البريد أو الهاتف"; loop `{% for u in suppliers %}`; `supplier-edit`/`supplier-delete`/
`supplier-create`; empty text "لا يوجد موردون."

**NEW `src/tarcom/templates/dashboard/suppliers/supplier_form.html`** — same as
customer_form.html with المورد/مورد wording, `suppliers-list` links.

**EDIT `src/tarcom/templates/dashboard/base.html`** — wire the two empty nav links
(in the `المستخدمين` nav section, currently `<a href="" class="sub-item">`):

```html
                            <a href="{% url 'customers-list' %}" class="sub-item">العملاء</a>
                            ...
                            <a href="{% url 'suppliers-list' %}" class="sub-item">الموردون</a>
```

(keep the `المدراء` link pointing at `users-list` as it is.)

### Step 8 — `src/tarcom/templates/dashboard/users/users_list.html`: admins-only page

The users page is now the admins page. Edit it:
1. Title block → `المدراء`; breadcrumb span → `المدراء`.
2. DELETE the whole `actions-dropdown` div (the `user_type` filter form, lines ~23-35) —
   the list is fixed to `user_type=admin`, the dropdown is meaningless. Keep the search box.
3. Empty-row text → `لا يوجد مدراء.`
4. Everything else (table columns, emoji buttons, add/edit/delete links, pagination) stays
   unchanged. `UserCreateView`/`UserUpdateView`/`UserForm` are NOT modified — the general
   form keeps its user_type dropdown (existing behavior, out of scope).

### Step 9 — Dashboard tests (append to `src/tarcom/base/tests.py`)

Add a `DashboardUserPagesTest(TestCase)` class following the existing style in that file
(`self.client.force_login(self.staff)`, create users via `CustomUser.objects.create_user`),
covering at minimum:

```python
class DashboardUserPagesTest(TestCase):
    def setUp(self):
        self.client = APIClient()  # or Django client as used elsewhere in the file
        self.staff = CustomUser.objects.create_user(
            email='staff@tarcom.com', password='StaffPass123!', is_staff=True,
            user_type=UserType.ADMIN,
        )
        self.client.force_login(self.staff)
        self.customer = CustomUser.objects.create_user(
            email='cust@tarcom.com', password='CustPass123!', user_type=UserType.CUSTOMER,
        )
        self.supplier = CustomUser.objects.create_user(
            email='sup@tarcom.com', password='SupPass123!', user_type=UserType.SUPPLIER,
        )

    def test_customers_list_shows_only_customers(self): ...
        # GET /dashboard/customers/ -> 200, contains cust@tarcom.com, not sup@tarcom.com

    def test_suppliers_list_shows_only_suppliers(self): ...

    def test_users_list_shows_only_admins(self): ...
        # GET /dashboard/users/ -> does not contain cust@/sup@

    def test_customer_create_presets_user_type(self): ...
        # POST /dashboard/customers/create/ with email/password -> 302;
        # CustomUser.objects.get(email=...).user_type == UserType.CUSTOMER

    def test_customer_delete_ajax(self): ...
        # POST /dashboard/customers/<pk>/delete/ with HTTP_X_REQUESTED_WITH
        # -> JSON ok:true, user gone (mirror the existing DashboardProtectedDeleteTest style)
```

Write the bodies following the patterns already present in `base/tests.py`
(`DashboardProtectedDeleteTest` for the AJAX delete; `assertContains`/`assertRedirects` for
the rest). Import `UserType` if not already imported in that file.

## Part C — Production-readiness validation (REPORT ONLY)

### Step 10 — Gather evidence

Run (record the full output — it goes into the report):

```
python manage.py check --deploy
python manage.py test tarcom.base tarcom.api
```

Also inspect: `src/tarcom/settings.py`, `.env` presence, `docker-compose.yml` (repo root),
`pyproject.toml`, and whether `tarcom/Dockerfile` + `tarcom/docker-compose.yml` exist.

### Step 11 — Write `PRODUCTION_CHECKLIST.md` at the repo root

Structure (write in English, keep it factual; every finding cites file:line and gives the
exact fix):

1. **Verdict** — one paragraph: not production-ready yet, with the blocking items listed.
2. **Django deploy checks** — paste the `check --deploy` warnings verbatim (expect: DEBUG,
   ALLOWED_HOSTS, SECURE_SSL_REDIRECT, SESSION_COOKIE_SECURE, CSRF_COOKIE_SECURE,
   SECURE_HSTS_SECONDS) and mark each as FAIL with the fix (env-driven values, HTTPS
   termination).
3. **Findings table** — per item: status (✅ / ⚠️ / ❌), severity, location, fix. Cover at
   least these known items (verify each against the current code; add anything else found):
   - `SECRET_KEY` from `.env` — ✅ (already externalized).
   - `DEBUG = True` hardcoded (settings.py ~line 33) — ❌ make env-driven
     (`env.bool('DEBUG', default=False)`).
   - `ALLOWED_HOSTS = []` — ❌ env-driven list.
   - `SESSION_COOKIE_SECURE`, `CSRF_COOKIE_SECURE`, `SECURE_SSL_REDIRECT`,
     `SECURE_HSTS_SECONDS`, `SECURE_PROXY_SSL_HEADER` — ❌ all missing.
   - Password validators — ✅ present.
   - Database: `env.db_url` with sqlite fallback — ⚠️ production must set `DATABASE_URL`
     (PostgreSQL); the root `docker-compose.yml` declares a `tarcom_db` service but references
     a `./tarcom` build context and `tarcom/docker-compose.yml` that do not exist — ❌ broken
     deployment artifacts.
   - `STATIC_ROOT` missing — ❌ needed with `collectstatic`; static currently served via
     app dirs only.
   - Media: served only under DEBUG (urls.py) — ⚠️ prod needs a web server (nginx) or a
     storage backend.
   - `silk` enabled unconditionally (INSTALLED_APPS, middleware, `/silk/` route) — ❌ gate
     behind an env flag / remove in prod.
   - `/api/schema/`, `/api/docs/`, `/api/redoc/` publicly exposed — ⚠️ consider gating.
   - JWT `ACCESS_TOKEN_LIFETIME = 500 days` — ⚠️ far above typical production lifetimes.
   - Email: `EMAIL_HOST_PASSWORD = env('EMAIL_HOST_PASSWORD')` with no default — ⚠️ app
     crashes at startup if the var is missing; document it as required.
   - Admin URL, throttle rates, CSRF defaults, `X_FRAME_OPTIONS` — ✅ acceptable/defaults.
   - Test suite result (from Step 10) — report pass/fail with counts.
4. **Mobile-client impact note** — pagination response-shape change (Part A warning).
5. **Go-live checklist** — ordered list of what must happen before deploying (env vars,
   HTTPS, collectstatic, DB migration plan, disable silk, run tests).

NO code changes in Part C — findings only.

---

## Step 12 — Verification (commands from `src/tarcom/`)

1. `python manage.py check` — clean.
2. `python manage.py test tarcom.base tarcom.api` — all pass (includes the rewritten list
   tests from Step 3 and the new dashboard tests from Step 9).
3. Grep checks: no `pagination_class` remains in `api/views/`; `DEFAULT_PAGINATION_CLASS`
   present once in settings.py.
4. Browser checklist (`python manage.py runserver`, staff login):
   - Nav: المدراء / العملاء / الموردون all navigate to their pages.
   - Users page lists only `user_type=admin` users; search works.
   - Customers page lists only customers; add → form without visible user_type dropdown →
     save → new row appears; edit works; 🗑️ opens the shared modal and AJAX delete removes
     the row without reload.
   - Suppliers page: same checks.
   - API spot-check: `GET /api/units/` returns an object with `count/next/previous/results`.
5. `PRODUCTION_CHECKLIST.md` exists at the repo root and contains the `check --deploy`
   output.

## Out of scope — do NOT do

- Do NOT touch the broken legacy `templates/dashboard/users/admins/*` templates (they
  reference non-existent routes/partials; left as dead code).
- Do NOT change `page_size` in `utils/pagination.py`.
- Do NOT modify `UserForm`, `UserCreateView`, `UserUpdateView`, `UserDeleteView` (only
  `UsersListView`'s queryset changes).
- Do NOT change serializers, filters, or any API view beyond removing the MaterialViewSet
  override.
- Part C is report-only: no settings/deploy code changes.
