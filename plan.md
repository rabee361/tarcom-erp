# Step-by-Step Implementation Plan: Auth/OTP/User ViewSets & drf-spectacular Integration

## 1. Overview & Objectives
This plan outlines the exact steps to:
1. Refactor authentication, OTP management, and user profile processes from individual `APIView`s into **3 cohesive DRF ViewSets**:
   - **`AuthViewSet`**: Handles `login`, `signup`, and token refresh.
   - **`OTPViewSet`**: Handles `send-otp`, `verify-otp`, `forget-password`, and `reset-password`.
   - **`UserViewSet` / `UserInfoViewSet`**: Handles user profile management (`me` endpoint for authenticated users) and administrative user CRUD.
2. Integrate and configure **`drf-spectacular`**:
   - Configure settings in `settings.py`.
   - Add OpenAPI schema, Swagger UI, and ReDoc documentation endpoints in `urls.py`.
   - Annotate all viewsets (`AuthViewSet`, `OTPViewSet`, `UserViewSet`, `MaterialViewSet`, `MaterialCategoryViewSet`, `UnitOfMeasureViewSet`) using `@extend_schema` and `@extend_schema_view` with accurate request/response serializers, tags, and status codes.
3. Ensure 100% test compatibility and verification across the existing test suite (26 passing tests).

---

## 2. Architectural Design & Caveats

### Caveat 1: Action-based Routing vs. RESTful ViewSets
- `login`, `signup`, `send-otp`, `verify-otp`, `forget-password`, and `reset-password` are RPC-style operations rather than standard model CRUD operations.
- Therefore, `AuthViewSet` and `OTPViewSet` will extend `viewsets.GenericViewSet` (or `viewsets.ViewSet`), using `@action(detail=False, methods=['post'])` for each operation.
- `UserViewSet` will extend `viewsets.ModelViewSet` for `CustomUser` with an action `@action(detail=False, methods=['get', 'patch'], permission_classes=[IsAuthenticated])` for `/me/` to allow mobile app users to fetch and update their own profile.

### Caveat 2: Router URL Prefixes & Backward Compatibility
- Existing API tests in `src/tarcom/api/tests.py` target endpoints at `/api/auth/signup/`, `/api/auth/login/`, etc.
- In `src/tarcom/api/urls.py`, we will configure the router prefixes such that:
  - `router.register('auth', AuthViewSet, basename='auth')` provides:
    - `POST /api/auth/signup/`
    - `POST /api/auth/login/`
  - `router.register('otp', OTPViewSet, basename='otp')` provides:
    - `POST /api/otp/send-otp/`
    - `POST /api/otp/verify-otp/`
    - `POST /api/otp/forget-password/`
    - `POST /api/otp/reset-password/`
  - In addition, aliases/redirects or shared action bindings will be registered so both `/api/auth/send-otp/` and `/api/otp/send-otp/` resolve cleanly, maintaining complete backward compatibility with mobile clients and existing test suites.
  - `router.register('users', UserViewSet, basename='users')` provides:
    - `GET /api/users/me/`
    - `PATCH /api/users/me/`
    - `GET /api/users/` (admin only)
    - `GET /api/users/{id}/` (admin only)

### Caveat 3: drf-spectacular Schema Generation for Translated Models
- `Material`, `MaterialCategory`, and `UnitOfMeasure` use `django-modeltranslation`.
- Dynamic translation fields (`name_en`, `name_ar`, etc.) must be accurately exposed in the OpenAPI schema without generating schema warnings. `TranslateModelSerializer` already registers these fields in `get_field_names`, which `drf-spectacular` picks up automatically.

---

## 3. Step-by-Step Implementation Steps

### Step 1: Configure `drf-spectacular` in `settings.py`
1. Open `src/tarcom/settings.py`.
2. Add `'drf_spectacular'` to `INSTALLED_APPS`:
   ```python
   INSTALLED_APPS = [
       'modeltranslation',
       'django.contrib.admin',
       ...
       'rest_framework',
       'rest_framework_simplejwt',
       'rest_framework_simplejwt.token_blacklist',
       'drf_spectacular',
       'silk',
       'tarcom.base',
       'tarcom.api'
   ]
   ```
3. Update `REST_FRAMEWORK` dictionary to set the default schema class:
   ```python
   REST_FRAMEWORK = {
       'DEFAULT_AUTHENTICATION_CLASSES': (
           'rest_framework_simplejwt.authentication.JWTAuthentication',
       ),
       'DEFAULT_SCHEMA_CLASS': 'drf_spectacular.openapi.AutoSchema',
   }
   ```
4. Define `SPECTACULAR_SETTINGS`:
   ```python
   SPECTACULAR_SETTINGS = {
       'TITLE': 'Tarcom E-Commerce API',
       'DESCRIPTION': 'REST API for Tarcom E-Store and Flutter mobile application',
       'VERSION': '1.0.0',
       'SERVE_INCLUDE_SCHEMA': False,
       'COMPONENT_SPLIT_REQUEST': True,
   }
   ```

---

### Step 2: Implement User Serializers in `src/tarcom/api/serializers.py`
1. Ensure `UserSerializer` has proper read-only fields (`id`, `is_verified`, `user_type`).
2. Add `UserProfileUpdateSerializer` for the `/me/` endpoint:
   - Allowed update fields: `first_name`, `last_name`, `phone`, `avatar`.
3. Add response serializers for OpenAPI documentation:
   - `TokenResponseSerializer`: contains `access` and `refresh` tokens plus nested `user` profile.
   - `MessageResponseSerializer`: contains standard status/info messages (`{"message": "..."}`).

---

### Step 3: Implement the 3 ViewSets in `src/tarcom/api/views.py`

#### 1. `AuthViewSet(viewsets.GenericViewSet)`
- **Permissions:** `AllowAny`
- **Actions:**
  - `signup` (`@action(detail=False, methods=['post'])`):
    - Input: `SignupSerializer`
    - Creates user with `is_verified=False`, generates `CodeTypes.SIGNUP` OTP.
    - Output: HTTP 201 with `{"message": "Account created. Please verify your email.", "email": ...}`
  - `login` (`@action(detail=False, methods=['post'])`):
    - Input: `LoginSerializer`
    - Validates credentials and active/verified status.
    - Output: HTTP 200 with JWT tokens (`access`, `refresh`) and `user` payload.
- **Spectacular Annotation:** `@extend_schema(tags=['Auth'], ...)`

#### 2. `OTPViewSet(viewsets.GenericViewSet)`
- **Permissions:** `AllowAny`
- **Actions:**
  - `send_otp` (`@action(detail=False, methods=['post'], url_path='send-otp')`):
    - Input: `SendOtpSerializer` (`email`, `code_type`)
    - Validates rate-limit (`OTPCode.check_limit(email)`), creates OTP code, sends email.
    - Output: HTTP 200 `{"message": "OTP code sent successfully."}`
  - `verify_otp` (`@action(detail=False, methods=['post'], url_path='verify-otp')`):
    - Input: `VerifyOtpSerializer` (`email`, `code`, `code_type`)
    - Validates code and expiration. Marks `is_used = True`.
    - If `SIGNUP`: sets `is_verified = True`, generates and returns JWT tokens + user.
    - If `RESET_PASSWORD`: generates and returns signed `reset_token`.
  - `forget_password` (`@action(detail=False, methods=['post'], url_path='forget-password')`):
    - Input: `ForgetPasswordSerializer` (`email`)
    - Checks rate limits, generates `RESET_PASSWORD` OTP.
    - Output: HTTP 200 `{"message": "Password reset OTP sent to your email."}`
  - `reset_password` (`@action(detail=False, methods=['post'], url_path='reset-password')`):
    - Input: `ResetPasswordSerializer` (`email`, `code` or `reset_token`, `new_password`, `new_password_confirm`)
    - Updates user password via `set_password()`.
    - Output: HTTP 200 `{"message": "Password reset successfully. You can now log in."}`
- **Spectacular Annotation:** `@extend_schema(tags=['OTP & Password'], ...)`

#### 3. `UserViewSet(viewsets.ModelViewSet)`
- **Queryset:** `CustomUser.objects.all()`
- **Serializer:** `UserSerializer`
- **Permissions:**
  - Standard CRUD: `IsAdminUser` (only admins can list/modify all users).
  - `/me/`: `IsAuthenticated` (any logged in user can view/edit their own profile).
- **Actions:**
  - `me` (`@action(detail=False, methods=['get', 'patch'], permission_classes=[IsAuthenticated])`):
    - `GET`: returns serialized `request.user`.
    - `PATCH`: validates with `UserProfileUpdateSerializer`, updates `request.user`, returns updated `UserSerializer`.
- **Spectacular Annotation:** `@extend_schema(tags=['Users'], ...)`

---

### Step 4: Annotate Product, Category & Unit ViewSets for `drf-spectacular`
1. In `src/tarcom/api/views.py`:
   - Annotate `MaterialViewSet` with `@extend_schema_view(...)` and tag `'Materials (Products)'`.
   - Annotate `MaterialCategoryViewSet` with `@extend_schema_view(...)` and tag `'Categories'`.
   - Annotate `UnitOfMeasureViewSet` with `@extend_schema_view(...)` and tag `'Units of Measure'`.
2. Add explicit parameter documentation for filters (`category`, `is_active`, `parent`, `search`, `ordering`).

---

### Step 5: Configure URLs in `src/tarcom/urls.py` and `src/tarcom/api/urls.py`
1. In `src/tarcom/api/urls.py`:
   - Register viewsets in `DefaultRouter`:
     ```python
     router = DefaultRouter()
     router.register(r'auth', AuthViewSet, basename='auth')
     router.register(r'otp', OTPViewSet, basename='otp')
     router.register(r'users', UserViewSet, basename='users')
     router.register(r'materials', MaterialViewSet, basename='materials')
     ```
   - Retain alias routes or action bindings to guarantee 100% backward compatibility for existing Flutter calls and test suites.
2. In `src/tarcom/urls.py`:
   - Import `SpectacularAPIView`, `SpectacularSwaggerView`, `SpectacularRedocView`.
   - Add routes:
     ```python
     path('api/schema/', SpectacularAPIView.as_view(), name='schema'),
     path('api/docs/', SpectacularSwaggerView.as_view(url_name='schema'), name='swagger-ui'),
     path('api/redoc/', SpectacularRedocView.as_view(url_name='schema'), name='redoc'),
     ```

---

### Step 6: Testing & Verification
1. Run `manage.py check` to verify system integrity and spectacular setup:
   ```powershell
   uv run python src/tarcom/manage.py check
   ```
2. Generate schema via CLI to verify no schema generation warnings or errors:
   ```powershell
   uv run python src/tarcom/manage.py spectacular --file schema.yml
   ```
3. Add unit tests for:
   - `AuthViewSet` (`signup`, `login`)
   - `OTPViewSet` (`send-otp`, `verify-otp`, `forget-password`, `reset-password`)
   - `UserViewSet` (`/me/` retrieval and patch, permission checks)
   - OpenAPI schema endpoint (`/api/schema/`) returning HTTP 200.
4. Run full test suite:
   ```powershell
   uv run python src/tarcom/manage.py test tarcom.api
   ```
