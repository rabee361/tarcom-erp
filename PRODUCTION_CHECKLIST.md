# Production Readiness Checklist — Tarcom

Audit date: 2026-10-03. Scope: `src/tarcom/` (Django 6.1.1 + DRF), commit `c49d694` plus the
uncommitted working-tree changes. This document is **report only** — no production code was
changed to produce it.

---

## 1. Verdict

**Not production-ready.** The application runs correctly and its test suite is
near-green, but it is configured for local development and cannot be exposed to the
internet as-is. The blocking items are:

1. `DEBUG = True` hardcoded (`settings.py:33`) — leaks settings, SQL and tracebacks.
2. `SECRET_KEY` is a `django-insecure-…` development key (`settings.py:30`).
3. `ALLOWED_HOSTS = []` (`settings.py:35`) — the app cannot serve real hostnames.
4. No HTTPS enforcement at all: `SECURE_SSL_REDIRECT`, `SECURE_HSTS_SECONDS`,
   `SESSION_COOKIE_SECURE`, `CSRF_COOKIE_SECURE`, `SECURE_PROXY_SSL_HEADER` are all unset.
5. `django-silk` is unconditionally enabled (`settings.py:57`, `:72`, `urls.py:18`) — it
   profiles and records every request/response including headers and bodies.
6. The deployment artifacts are non-functional: `docker-compose.yml` extends
   `tarcom/docker-compose.yml` and builds from `./tarcom`, neither of which exists; the
   root `dockerfile` is empty.
7. Any account with `user_type = admin` has full user-management power over the system
   even when Django's `is_staff` is false — see findings #21 and #22.
8. Four tests fail (`3 failures, 1 error`) — all pre-existing, all real bugs.
9. No `STATIC_ROOT`, so `collectstatic` cannot run; media is served only under `DEBUG`.

---

## 2. Django deploy checks — `python manage.py check --deploy`

Verbatim output:

```
System check identified some issues:

WARNINGS:
?: (security.W004) You have not set a value for the SECURE_HSTS_SECONDS setting. If your entire site is served only
over SSL, you may want to consider setting a value and enabling HTTP Strict Transport Security. Be sure to read the
documentation first; enabling HSTS carelessly can cause serious, irreversible problems.
?: (security.W008) Your SECURE_SSL_REDIRECT setting is not set to True. Unless your site should be available over both
SSL and non-SSL connections, you may want to either set this setting True or configure a load balancer or
reverse-proxy server to redirect all connections to HTTPS.
?: (security.W009) Your SECRET_KEY has less than 50 characters, less than 5 unique characters, or it's prefixed with
'django-insecure-' indicating that it was generated automatically by Django. Please generate a long and random value,
otherwise many of Django's security-critical features will be vulnerable to attack.
?: (security.W012) SESSION_COOKIE_SECURE is not set to True. Using a secure-only session cookie makes it more
difficult for network traffic sniffers to hijack user sessions.
?: (security.W016) You have 'django.middleware.csrf.CsrfViewMiddleware' in your MIDDLEWARE, but you have not set
CSRF_COOKIE_SECURE to True. Using a secure-only CSRF cookie makes it more difficult for network traffic sniffers to
steal the CSRF token.
?: (security.W018) You should not have DEBUG set to True in deployment.
?: (security.W020) ALLOWED_HOSTS must not be empty in deployment.

System check identified 7 issues (0 silenced).
```

| Check | Status | Fix |
|---|---|---|
| `security.W018` DEBUG | ❌ FAIL | `DEBUG = env.bool('DEBUG', default=False)` at `settings.py:33`. |
| `security.W020` ALLOWED_HOSTS | ❌ FAIL | `ALLOWED_HOSTS = env.list('ALLOWED_HOSTS', default=[])`, set `ALLOWED_HOSTS=tarcom.example.com` in the production `.env`. |
| `security.W009` SECRET_KEY | ❌ FAIL | Replace the `django-insecure-` value with `python -c "from django.core.management.utils import get_random_secret_key as k; print(k())"`. Externalisation itself is already correct. |
| `security.W008` SECURE_SSL_REDIRECT | ❌ FAIL | `SECURE_SSL_REDIRECT = env.bool('SECURE_SSL_REDIRECT', default=True)`, or terminate TLS at a proxy and redirect there. |
| `security.W012` SESSION_COOKIE_SECURE | ❌ FAIL | `SESSION_COOKIE_SECURE = True`. |
| `security.W016` CSRF_COOKIE_SECURE | ❌ FAIL | `CSRF_COOKIE_SECURE = True`. |
| `security.W004` SECURE_HSTS_SECONDS | ❌ FAIL | `SECURE_HSTS_SECONDS = 31536000`, `SECURE_HSTS_INCLUDE_SUBDOMAINS = True`, `SECURE_HSTS_PRELOAD = True` — only once HTTPS is confirmed working on every subdomain. |

---

## 3. Findings

| # | Status | Severity | Item | Location | Fix |
|---|---|---|---|---|---|
| 1 | ✅ | — | `SECRET_KEY` externalised via `env('SECRET_KEY')`; `.env` is git-ignored (`.gitignore:16`, confirmed by `git check-ignore`) | `settings.py:30` | Keep. See #2 for the key's value. |
| 2 | ❌ | Critical | `SECRET_KEY` value is a `django-insecure-…` development key (66 chars, 35 unique chars) — rotates all sessions/tokens and is predictable | `.env` | Generate a random production key. |
| 3 | ❌ | Critical | `DEBUG = True` hardcoded | `settings.py:33` | `DEBUG = env.bool('DEBUG', default=False)`. |
| 4 | ❌ | Critical | `ALLOWED_HOSTS = []` | `settings.py:35` | `ALLOWED_HOSTS = env.list('ALLOWED_HOSTS', default=[])`. |
| 5 | ❌ | High | No HTTPS/security-cookie settings at all | `settings.py` (absent) | Add `SECURE_SSL_REDIRECT`, `SESSION_COOKIE_SECURE`, `CSRF_COOKIE_SECURE`, `SECURE_HSTS_SECONDS`, `SECURE_PROXY_SSL_HEADER = ('HTTP_X_FORWARDED_PROTO', 'https')`. |
| 6 | ❌ | Critical | `django-silk` enabled unconditionally — `INSTALLED_APPS`, `SilkyMiddleware`, and the `/silk/` route | `settings.py:57`, `settings.py:72`, `urls.py:18` | Gate behind `env.bool('ENABLE_SILK', default=False)` in all three places, or remove entirely. |
| 7 | ❌ | High | Broken deployment artifacts: `tarcom_app` builds `context: ./tarcom` + `dockerfile: Dockerfile` and `extends: file: tarcom/docker-compose.yml` — neither exists; `tarcom_db` `extends` `docker-compose.yml` **from itself** (circular). Root `dockerfile` is 0 bytes. `networks: kadnya` is referenced but never declared. | `docker-compose.yml:2-34`, `dockerfile` | Rewrite the compose file against the real layout (`src/tarcom`), give the app a real Dockerfile, declare the `kadnya` network or drop it. |
| 8 | ❌ | High | `STATIC_ROOT` not defined — `collectstatic` has no destination; static is served only via app-dirs | `settings.py:197` | `STATIC_ROOT = BASE_DIR / 'staticfiles'` and run `collectstatic` at deploy time. |
| 9 | ⚠️ | Medium | Media served by Django only when `DEBUG` is on; with `DEBUG=False` uploaded avatars/icons 404 | `urls.py:21-22`, `settings.py:200` | Serve `MEDIA_ROOT` from nginx, or move to S3/another storage backend. |
| 10 | ⚠️ | Medium | `/api/schema/`, `/api/docs/`, `/api/redoc/` are public with no auth | `urls.py:13-15` | Gate behind staff auth or an env flag, or drop in production. |
| 11 | ⚠️ | Medium | JWT `ACCESS_TOKEN_LIFETIME = timedelta(days=500)`, refresh 100 days, `ROTATE_REFRESH_TOKENS=False` — a leaked access token is valid for well over a year and cannot be revoked | `settings.py:218-219` | Access ~15 min, refresh ~7 days, `ROTATE_REFRESH_TOKENS=True` + `BLACKLIST_AFTER_ROTATION=True`. |
| 12 | ⚠️ | Medium | `EMAIL_HOST_PASSWORD = env('EMAIL_HOST_PASSWORD')` has no default — the process raises `ImproperlyConfigured` at import if unset, so a missing var is a hard crash rather than a degraded feature | `settings.py:212` | Give it a default (`env('EMAIL_HOST_PASSWORD', default='')`) and alert instead, or document it as a required var in the deployment runbook. |
| 13 | ⚠️ | Medium | Database defaults to SQLite when `DATABASE_URL` is unset | `settings.py:142` | Set `DATABASE_URL` to PostgreSQL in production; SQLite cannot serve concurrent writes. |
| 14 | ✅ | — | All four `AUTH_PASSWORD_VALIDATORS` enabled (similarity, min-length, common, numeric) | `settings.py:150-163` | Keep. |
| 15 | ✅ | — | `X_FRAME_OPTIONS` middleware present (clickjacking protection) | `settings.py:71` | Keep. |
| 16 | ✅ | — | CSRF protection active for the dashboard; `CsrfViewMiddleware` present | `settings.py:66` | Keep; add `CSRF_COOKIE_SECURE` (#5). |
| 17 | ✅ | — | Throttle rates configured for anonymous and authenticated traffic | `settings.py:86-89` | Keep. `120/min` anon is generous for auth endpoints — consider a separate scope. |
| 18 | ✅ | — | Admin at the default `/admin/` path | `urls.py:12` | Optional: rename to an unguessable path and/or add HTTP Basic auth in front of it. |
| 19 | ✅ | — | Test runner resets throttle counters so the suite cannot self-inflict 429s | `settings.py:96` | Keep. |
| 20 | ⚠️ | Low | `UnorderedObjectListWarning: Pagination may yield inconsistent results with an unordered object_list: CustomUser` — `UserViewSet.queryset = CustomUser.objects.all()` (`api/views/auth.py:280`) has no `ordering`, and `CustomUser.Meta` defines none. With global pagination now active, a row can be skipped or repeated across pages | `api/views/auth.py:280`, `base/models.py:26` | Add `ordering = ['-date_joined']` to `CustomUser.Meta`, or `.order_by('-date_joined')` on the viewset queryset. All other paginated querysets (`UnitOfMeasure`, `MaterialCategory`, `Setting`, `FavouriteItem`, `Material`, `Order`) already declare `Meta.ordering`. |
| 21 | ❌ | High | **Any account with `user_type = admin` can delete any user in the system, including superusers.** `StaffRequiredMixin.test_func` grants access on `user.is_staff or user.is_admin`, and `user.is_admin` is just `user_type == 'admin'` — an attribute any staff member can hand out from the admins page. `UserDeleteView` sets `model = CustomUser` with **no** `get_queryset()` override, so `DeleteView` resolves `CustomUser._default_manager.all()` and deletes whatever pk it is given | `utils/mixins.py:46-48`, `base/views/auth.py:150` (`UserDeleteView`) | Tighten `test_func` to `user.is_active and user.is_staff` (keep the `user.is_admin` fallback only if Django-`is_staff` is force-set at creation), **and** scope the view: add `get_queryset()` returning `CustomUser.objects.filter(user_type=UserType.ADMIN)`. Verified by probe: a `user_type=admin`, `is_staff=False` account successfully deleted another user through `/dashboard/customers/<pk>/delete/`. |
| 22 | ❌ | High | `CustomerDeleteView` / `SupplierDeleteView` originally inherited `UserDeleteView`'s unfiltered `model = CustomUser`, so `/dashboard/customers/<pk>/delete/` and `/dashboard/suppliers/<pk>/delete/` deleted **admins and cross-type users** — not just customers/suppliers | `base/views/auth.py` (`CustomerDeleteView`, `SupplierDeleteView`) | **Fixed in this change**: both now override `get_queryset()` to filter on `UserType.CUSTOMER` / `UserType.SUPPLIER`, so a mismatched pk is a 404. Regression tests: `test_customer_delete_url_cannot_delete_a_non_customer`, `test_supplier_delete_url_cannot_delete_a_non_supplier`. Note the same fix is still **missing** on `UserDeleteView` (#21). |

### Test suite result

```
Ran 148 tests in 391.612s
FAILED (failures=3, errors=1)
```

**144 pass, 4 fail — all four pre-existing and unrelated to pagination or the dashboard
work.** Each was verified to fail identically at commit `c49d694` with the pagination
changes reverted.

| Test | Symptom | Root cause |
|---|---|---|
| `api.tests.favourite_tests.FavouriteAPITest.test_toggle_favourite_requires_material` | 500 instead of 400 | `django.core.exceptions.ValidationError` escapes instead of DRF's |
| `api.tests.favourite_tests.FavouriteAPITest.test_check_favourite_status` | 500 instead of 400 | same |
| `api.tests.order_tests.OrderAPITest.test_customer_cannot_cancel_shipped_order` | 500 instead of 400 | same |
| `base.tests.DashboardMaterialsCrudTest.test_dashboard_materials_crud` | `Material.DoesNotExist` | `MaterialForm.Meta.fields` no longer contains `name` (modeltranslation split it into `name_en`/`name_ar`), but the test still posts `name` |

The first three share one bug. `api/views/favourites.py:14-16` and
`api/views/orders.py:13-15` both carry a comment saying the name must be re-bound after
the star imports — but the re-binding statement was never written:

```python
# Re-bound after the star imports above, which re-export
# django.core.exceptions.ValidationError and would otherwise
# turn these raises into 500s instead of DRF 400s.
```

`from ..serializers import *` re-exports `django.core.exceptions.ValidationError` (via
`serializers.py:11` → `from tarcom.base.models import *` → `models.py:5`), shadowing the
correctly-imported `rest_framework.exceptions.ValidationError` from line 6. `auth.py` has
the fix (`auth.py:8` imports as `DRFValidationError`, `auth.py:26` re-binds); the other two
files do not. **Fix: add `ValidationError = DRFValidationError` after the star imports in
both files** (and import it under an alias, as `auth.py` does).

---

## 4. Mobile-client impact — breaking change

Global pagination (`DEFAULT_PAGINATION_CLASS = tarcom.utils.pagination.CustomNumberPagination`,
`page_size = 4`) changes **every** DRF list endpoint from a bare JSON array to an envelope:

```json
{ "count": 42, "next": "http://…?page=2", "previous": null, "results": [ … ] }
```

Affected endpoints: `/api/materials/`, `/api/categories/`, `/api/units/`, `/api/settings/`,
`/api/users/`, `/api/favourites/`, `/api/orders/` — every `list` action. `/api/materials/`
already returned the envelope; the other six previously returned arrays.

The Flutter client must now read `results` and use `next`/`previous` for traversal.
`page_size_query_param = 'page_size'` (`utils/pagination.py:6`) lets the client request up to
`max_page_size = 50` per call — worth using to reduce round-trips.

This is unavoidable server-side once pagination is global. Detail endpoints, create/update
responses and error payloads (`{"code", "errors"}`) are unchanged. **The mobile app must be
updated in lockstep or it will silently show zero rows.**

---

## 5. Go-live checklist

Ordered. Nothing ships until every box is ticked.

**Secrets and configuration**

1. Generate a production `SECRET_KEY` (no `django-insecure-` prefix) and put it in the
   production `.env`.
2. Make `DEBUG`, `ALLOWED_HOSTS`, and the five `SECURE_*`/cookie flags env-driven in
   `settings.py`, then set `DEBUG=False` and the real hostname list in `.env`.
3. Set `DATABASE_URL` to a PostgreSQL DSN.
4. Confirm `EMAIL_HOST_PASSWORD` is present, or give it a default so a missing value does
   not crash the process at import.
5. Decide whether `.env` values come from the platform secret store rather than a file.

**Transport**

6. Terminate TLS at nginx / the load balancer and forward `X-Forwarded-Proto`; set
   `SECURE_PROXY_SSL_HEADER`.
7. Enable `SECURE_SSL_REDIRECT`, `SESSION_COOKIE_SECURE`, `CSRF_COOKIE_SECURE`.
8. Only after HTTPS is verified end-to-end, enable `SECURE_HSTS_SECONDS`.

**Static and media**

9. Add `STATIC_ROOT`; run `collectstatic` as a release step; serve `/static/` from the web
   server.
10. Serve `/media/` from the web server, or move uploads to object storage.

**Application hardening**

11. Remove or env-gate `django-silk` (`INSTALLED_APPS`, middleware, `/silk/` route).
12. Gate or remove `/api/schema/`, `/api/docs/`, `/api/redoc/`.
13. Shorten the JWT lifetimes and enable refresh-token rotation + blacklisting.
14. Give `UserViewSet` a deterministic ordering (finding #20).
15. Fix the privilege model (findings #21, #22): require Django's `is_staff` for
    user-management routes, and scope `UserDeleteView.get_queryset()` to admins.

**Data and correctness**

16. Fix the four failing tests — especially the `ValidationError` shadowing, which is a live
    500-on-bad-input bug on three API endpoints.
17. Run `makemigrations --check` and `migrate` against a copy of production data first;
    confirm `0006_image_fields_to_versatileimagefield` and
    `0007_copy_category_icons_to_media` apply cleanly — they rewrite image fields and copy
    files.

**Deployment plumbing**

18. Rewrite `docker-compose.yml` against the real layout and supply a real Dockerfile, or
    drop containerisation entirely.
19. Run the test suite (`python manage.py test tarcom.base tarcom.api`) and require it green.

**Client**

20. Ship the mobile client change for the pagination envelope **before** or **with** the
    server deploy.