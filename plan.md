# Tarcom Authentication & OTP API Implementation Plan

## 1. Context & Objectives
Tarcom is an e-store API built with Django and Django REST Framework (DRF) serving a Flutter mobile application.
This plan defines the exact implementation steps for the complete authentication and OTP verification workflow:
- **Signup** (`/api/auth/signup/`)
- **Login** (`/api/auth/login/`)
- **Send OTP** (`/api/auth/send-otp/`)
- **Verify OTP** (`/api/auth/verify-otp/`)
- **Forget Password** (`/api/auth/forget-password/`)
- **Reset Password** (`/api/auth/reset-password/`)
- **Token Refresh** (`/api/auth/token/refresh/`)

---

## 2. Identified Ambiguities & Clarifications

1. **`UserType` vs `CustomUser.is_buyer` mismatch**:
   - In `enums.py`, `UserType` currently defines `CUSTOMER = 'customer'` and `ADMIN = 'admin'`.
   - In `models.py`, `CustomUser.is_buyer` attempts to check `UserType.BUYER` (which does not exist and throws `AttributeError`).
   - In `users_ref.py`, `BUYER` and `SELLER` are both used.
   - **Proposed resolution**: Update `UserType` to include `BUYER = 'buyer'`, `SELLER = 'seller'`, and `ADMIN = 'admin'` (or map `CUSTOMER = 'customer'` and fix `is_buyer`). We recommend:
     `BUYER = 'buyer', 'Buyer'` (or `CUSTOMER = 'customer', 'Customer'`), `SELLER = 'seller', 'Seller'`, `ADMIN = 'admin', 'Admin'`.
2. **`CodeTypes` (`FORGET_PASSWORD` vs `RESET_PASSWORD`)**:
   - `enums.CodeTypes` includes both `RESET_PASSWORD` and `FORGET_PASSWORD`.
   - In `users_ref.py`, `CodeTypes.RESET_PASSWORD` is used when requesting a reset code.
   - **Proposed resolution**: Support both in serializer validation, treating them interchangeably or standardizing on `RESET_PASSWORD` for password recovery.
3. **Reset Password Flow Architecture for Flutter**:
   - Mobile apps benefit from either a 2-step direct flow or a 3-step token flow:
     - *2-Step*: `forget-password` (sends OTP) -> `reset-password` (submits `email`, `code`, `new_password`).
     - *3-Step*: `forget-password` (sends OTP) -> `verify-otp` (returns `reset_token`) -> `reset-password` (submits `reset_token`, `new_password`).
   - **Proposed resolution**: Implement `reset-password` to support **both**: accepting either `(email, code, new_password)` directly OR a verified `reset_token` from `verify-otp`.
4. **Login Behavior for Unverified Users**:
   - If an unverified user logs in, the API returns HTTP 403 Forbidden with `{ "error": "Account not verified", "needs_verification": true, "email": user.email }` so Flutter can navigate directly to the OTP verification screen.
5. **Database State**:
   - Currently, `AUTH_USER_MODEL` was missing from `settings.py`, and initial migrations were run against Django's default `auth.User`. Because `db.sqlite3` has 0 data records, we will configure `AUTH_USER_MODEL = 'base.CustomUser'` and cleanly rebuild the database schema.

---

## 3. Step-by-Step Implementation Steps

### Phase 1: Core Utilities & Configuration Fixes

1. **`src/tarcom/utils/validators.py`**:
   - Implement `PhoneNumberValidator`:
     ```python
     from django.core.validators import RegexValidator
     from django.utils.translation import gettext_lazy as _

     PhoneNumberValidator = RegexValidator(
         regex=r'^\+?[0-9]{7,15}$',
         message=_('Phone number must be entered in the format: "+999999999". Up to 15 digits allowed.')
     )
     ```

2. **`src/tarcom/utils/helper.py`**:
   - Implement `generate_code()` -> returns a 6-digit random int (`random.randint(100000, 999999)`).
   - Implement `get_expiration_time()` -> returns `timezone.now() + timedelta(minutes=10)`.
   - Implement `send_otp_email(email: str, code: int, code_type: str)` -> uses Django's `send_mail` with a clean notification template.

3. **`src/tarcom/utils/enums.py` & `src/tarcom/base/models.py`**:
   - Align `UserType` choices:
     - `BUYER = 'buyer', 'Buyer'`
     - `SELLER = 'seller', 'Seller'`
     - `ADMIN = 'admin', 'Admin'`
     (or keep `CUSTOMER` if preferred, ensuring `is_buyer` references valid attributes).
   - Ensure `CustomUser.is_buyer` and `CustomUser.is_admin` properties match `UserType`.
   - Set `phone` validator to `[PhoneNumberValidator]` on `CustomUser`.

4. **`src/tarcom/settings.py`**:
   - Add `AUTH_USER_MODEL = 'base.CustomUser'`.
   - Ensure `EMAIL_BACKEND = 'django.core.mail.backends.console.EmailBackend'` for local development.
   - Configure `DEFAULT_FROM_EMAIL = 'no-reply@tarcom.com'`.

5. **Database Migration**:
   - Clear existing initial migration / recreate migrations with `AUTH_USER_MODEL = 'base.CustomUser'`.
   - Apply `python src/tarcom/manage.py migrate`.

---

### Phase 2: DRF Serializers (`src/tarcom/api/serializers.py`)

1. **`UserSerializer`**:
   - Fields: `id`, `email`, `first_name`, `last_name`, `phone`, `avatar`, `user_type`, `is_verified`, `created_at`.
   - Read-only representation for profile responses.

2. **`SignupSerializer`**:
   - Fields: `email`, `password`, `first_name`, `last_name`, `phone`, `user_type` (default `BUYER`).
   - Validates email uniqueness and Django password validators.
   - `create()` creates user with `is_verified=False`.

3. **`LoginSerializer`**:
   - Fields: `email`, `password`.
   - Authenticates credentials.
   - Validates whether `is_verified` is true; if false, raises `ValidationError` with code `unverified_account`.

4. **`SendOtpSerializer`**:
   - Fields: `email`, `code_type`.
   - Validates `email` exists (for password reset / existing user verification).
   - Enforces rate-limit using `OTPCode.check_limit(email)`.

5. **`VerifyOtpSerializer`**:
   - Fields: `email`, `code`, `code_type`.
   - Validates existence of unexpired, unused OTP record.

6. **`ForgetPasswordSerializer`**:
   - Fields: `email`.
   - Checks if `CustomUser` exists for the given email.

7. **`ResetPasswordSerializer`**:
   - Fields: `email`, `code` (or `reset_token`), `new_password`, `new_password_confirm`.
   - Validates matching passwords, checks password policy, verifies OTP / token validity.

---

### Phase 3: API Views (`src/tarcom/api/views.py`)

1. **`SignupView` (`POST /api/auth/signup/`)**:
   - Creates the user in unverified state (`is_verified=False`).
   - Invokes `user.create_otp(code_type=CodeTypes.SIGNUP)`.
   - Calls `send_otp_email(user.email, code, CodeTypes.SIGNUP)`.
   - Returns HTTP 201 with `{ "message": "...", "email": user.email }`.

2. **`LoginView` (`POST /api/auth/login/`)**:
   - Validates credentials via `authenticate(email=email, password=password)`.
   - If user is unverified, returns HTTP 403 Forbidden with `{ "error": "Account not verified", "needs_verification": true, "email": email }`.
   - If verified, generates JWT tokens via `RefreshToken.for_user(user)`:
     ```json
     {
       "tokens": { "access": "...", "refresh": "..." },
       "user": { ... }
     }
     ```

3. **`SendOtpView` (`POST /api/auth/send-otp/`)**:
   - Checks `OTPCode.check_limit(email)` (returns HTTP 429 if exceeded).
   - Creates new OTP of specified `code_type`.
   - Dispatches OTP email.
   - Returns HTTP 200 `{ "message": "OTP code sent successfully." }`.

4. **`VerifyOtpView` (`POST /api/auth/verify-otp/`)**:
   - Queries `OTPCode.objects.filter(email=email, code=code, code_type=code_type, is_used=False).first()`.
   - Checks `otp.is_expired`. If expired or invalid, returns HTTP 400.
   - Marks `otp.is_used = True; otp.save()`.
   - **For `SIGNUP`**:
     - Sets `user.is_verified = True; user.save()`.
     - Issues JWT tokens (`access`, `refresh`) and returns user payload so Flutter logs the user in immediately.
   - **For `FORGET_PASSWORD` / `RESET_PASSWORD`**:
     - Returns a signed one-time reset token (using Django's `signing.TimestampSigner`) or status code allowing immediate password reset.

5. **`ForgetPasswordView` (`POST /api/auth/forget-password/`)**:
   - Finds user by email (returns 404 or safe 200).
   - Checks rate limits via `OTPCode.check_limit(email)`.
   - Calls `user.create_otp(code_type=CodeTypes.RESET_PASSWORD)`.
   - Sends email and returns HTTP 200 `{ "message": "Password reset OTP sent to your email." }`.

6. **`ResetPasswordView` (`POST /api/auth/reset-password/`)**:
   - Validates OTP code or `reset_token`.
   - Updates user password: `user.set_password(new_password); user.save()`.
   - Marks OTP as used.
   - Returns HTTP 200 `{ "message": "Password reset successfully. You can now log in." }`.

---

### Phase 4: URL Configuration (`src/tarcom/api/urls.py` & `src/tarcom/urls.py`)

1. In `src/tarcom/api/urls.py`:
   ```python
   from django.urls import path
   from rest_framework_simplejwt.views import TokenRefreshView
   from .views import (
       SignupView, LoginView, SendOtpView,
       VerifyOtpView, ForgetPasswordView, ResetPasswordView
   )

   urlpatterns = [
       path('signup/', SignupView.as_view(), name='auth_signup'),
       path('login/', LoginView.as_view(), name='auth_login'),
       path('send-otp/', SendOtpView.as_view(), name='auth_send_otp'),
       path('verify-otp/', VerifyOtpView.as_view(), name='auth_verify_otp'),
       path('forget-password/', ForgetPasswordView.as_view(), name='auth_forget_password'),
       path('reset-password/', ResetPasswordView.as_view(), name='auth_reset_password'),
       path('token/refresh/', TokenRefreshView.as_view(), name='token_refresh'),
   ]
   ```

2. In `src/tarcom/urls.py`:
   ```python
   urlpatterns = [
       path('admin/', admin.site.urls),
       path('api/auth/', include('api.urls')),
       path('api/', include('base.urls')),
       path('silk/', include('silk.urls', namespace='silk')),
   ]
   ```

---

### Phase 5: Verification & Automated Tests

1. **`src/tarcom/api/tests.py`**:
   - Test Signup creates unverified user and OTP.
   - Test Login fails for unverified user (returns 403).
   - Test Verify OTP marks user verified and returns JWT tokens.
   - Test Login succeeds for verified user and returns tokens.
   - Test OTP expiration and rate limiting (max 5 per 15 min).
   - Test Forget Password generates OTP.
   - Test Reset Password resets password and allows subsequent login with new credentials.
2. Run test suite: `python src/tarcom/manage.py test api`.
