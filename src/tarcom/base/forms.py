from django import forms
from django.contrib.auth.password_validation import validate_password
from django.core.exceptions import ValidationError
from django.utils.translation import gettext_lazy as _

from tarcom.base.models import CustomUser, Material, MaterialCategory, UnitOfMeasure
from tarcom.utils.enums import OrderStatus, PaymentStatus


class DashboardLoginForm(forms.Form):
    phonenumber = forms.CharField(
        label=_("رقم الهاتف أو البريد الإلكتروني"),
        widget=forms.TextInput(
            attrs={
                "placeholder": _("رقم الهاتف أو البريد"),
                "class": "form-control",
                "autofocus": True,
            }
        ),
    )
    password = forms.CharField(
        label=_("كلمة المرور"),
        widget=forms.PasswordInput(
            attrs={
                "placeholder": _("كلمة المرور"),
                "id": "loginPassword",
                "class": "form-control",
            }
        ),
    )
    remember_me = forms.BooleanField(
        required=False,
        label=_("تذكرني"),
        widget=forms.CheckboxInput(attrs={"id": "remember-me"}),
    )


class DashboardChangePasswordForm(forms.Form):
    old_password = forms.CharField(
        label=_("كلمة المرور الحالية"),
        widget=forms.PasswordInput(
            attrs={
                "placeholder": _("كلمة المرور الحالية"),
                "id": "oldPassword",
            }
        ),
    )
    new_password1 = forms.CharField(
        label=_("كلمة المرور الجديدة"),
        widget=forms.PasswordInput(
            attrs={
                "placeholder": _("كلمة المرور الجديدة"),
                "id": "newPassword1",
            }
        ),
        validators=[validate_password],
    )
    new_password2 = forms.CharField(
        label=_("تأكيد كلمة المرور الجديدة"),
        widget=forms.PasswordInput(
            attrs={
                "placeholder": _("تأكيد كلمة المرور الجديدة"),
                "id": "newPassword2",
            }
        ),
    )

    def __init__(self, user, *args, **kwargs):
        self.user = user
        super().__init__(*args, **kwargs)

    def clean_old_password(self):
        old_password = self.cleaned_data.get("old_password")
        if not self.user.check_password(old_password):
            raise ValidationError(_("Current password is incorrect."))
        return old_password

    def clean(self):
        cleaned_data = super().clean()
        p1 = cleaned_data.get("new_password1")
        p2 = cleaned_data.get("new_password2")
        if p1 and p2 and p1 != p2:
            raise ValidationError({"new_password2": _("Passwords do not match.")})
        return cleaned_data

    def save(self):
        self.user.set_password(self.cleaned_data["new_password1"])
        self.user.save()
        return self.user


class UserForm(forms.ModelForm):
    password = forms.CharField(
        label=_("كلمة المرور"),
        required=False,
        widget=forms.PasswordInput(attrs={"placeholder": _("كلمة المرور")}),
    )
    confirm_password = forms.CharField(
        label=_("تأكيد كلمة المرور"),
        required=False,
        widget=forms.PasswordInput(attrs={"placeholder": _("تأكيد كلمة المرور")}),
    )

    class Meta:
        model = CustomUser
        fields = [
            "email",
            "first_name",
            "last_name",
            "phone",
            "user_type",
            "is_active",
            "avatar",
        ]
        labels = {
            "email": _("البريد الإلكتروني"),
            "first_name": _("الاسم الأول"),
            "last_name": _("اسم العائلة"),
            "phone": _("رقم الهاتف"),
            "user_type": _("نوع المستخدم"),
            "is_active": _("الحساب نشط"),
            "avatar": _("الصورة الشخصية"),
        }

    def clean(self):
        cleaned_data = super().clean()
        password = cleaned_data.get("password")
        confirm = cleaned_data.get("confirm_password")
        if not self.instance.pk and not password:
            self.add_error(
                "password", _("A password is required to create a new user.")
            )
        if password and password != confirm:
            self.add_error("confirm_password", _("Passwords do not match."))
        return cleaned_data

    def save(self, commit=True):
        user = super().save(commit=False)
        password = self.cleaned_data.get("password")
        if password:
            user.set_password(password)
        # CustomUser.username is unique; the form does not expose it.
        user.username = user.email
        if commit:
            user.save()
        return user


class CustomerUserForm(UserForm):
    class Meta(UserForm.Meta):
        widgets = {"user_type": forms.HiddenInput()}


class SupplierUserForm(UserForm):
    class Meta(UserForm.Meta):
        widgets = {"user_type": forms.HiddenInput()}


class MaterialForm(forms.ModelForm):
    category = forms.ModelChoiceField(
        queryset=MaterialCategory.objects.all(),
        label=_("التصنيف"),
        empty_label=None,
    )

    uom = forms.ModelChoiceField(
        queryset=UnitOfMeasure.objects.all(),
        label=_("وحدة القياس"),
        empty_label=None,
    )

    class Meta:
        model = Material
        fields = [
            "name_en",
            "name_ar",
            "category",
            "uom",
            "company",
            "supplier_price",
            "consumer_price",
            "description_en",
            "description_ar",
            "spec_key1",
            "spec_val1",
            "spec_key2",
            "spec_val2",
            "spec_key3",
            "spec_val3",
            "spec_key4",
            "spec_val4",
            "spec_key5",
            "spec_val5",
            "is_active",
            "image1",
            "image2",
            "image3",
            "image4",
            "image5",
        ]
        labels = {
            "name_en": _("الاسم بالإنجليزية"),
            "name_ar": _("الاسم بالعربية"),
            "category": _("التصنيف"),
            "uom": _("وحدة القياس"),
            "company": _("الشركة"),
            "supplier_price": _("سعر المورد"),
            "consumer_price": _("سعر المستهلك"),
            "description_en": _("الوصف بالإنجليزية"),
            "description_ar": _("الوصف بالعربية"),
            "spec_key1": _("اسم المواصفة 1"),
            "spec_val1": _("قيمة المواصفة 1"),
            "spec_key2": _("اسم المواصفة 2"),
            "spec_val2": _("قيمة المواصفة 2"),
            "spec_key3": _("اسم المواصفة 3"),
            "spec_val3": _("قيمة المواصفة 3"),
            "spec_key4": _("اسم المواصفة 4"),
            "spec_val4": _("قيمة المواصفة 4"),
            "spec_key5": _("اسم المواصفة 5"),
            "spec_val5": _("قيمة المواصفة 5"),
            "is_active": _("نشط"),
            "image1": _("الصورة الرئيسية"),
            "image2": _("صورة إضافية 1"),
            "image3": _("صورة إضافية 2"),
            "image4": _("صورة إضافية 3"),
            "image5": _("صورة إضافية 4"),
        }
        widgets = {
            "image1": forms.ClearableFileInput(attrs={"accept": "image/*"}),
            "image2": forms.ClearableFileInput(attrs={"accept": "image/*"}),
            "image3": forms.ClearableFileInput(attrs={"accept": "image/*"}),
            "image4": forms.ClearableFileInput(attrs={"accept": "image/*"}),
            "image5": forms.ClearableFileInput(attrs={"accept": "image/*"}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

        self.fields["category"].label_from_instance = lambda obj: obj.name_ar
        self.fields["uom"].label_from_instance = lambda obj: obj.name_ar


class CategoryForm(forms.ModelForm):
    class Meta:
        model = MaterialCategory
        fields = ["name_en", "name_ar", "image"]
        labels = {
            "name_en": _("الاسم بالإنجليزية"),
            "name_ar": _("الاسم بالعربية"),
            "image": _("صورة التصنيف"),
        }
        widgets = {
            "image": forms.ClearableFileInput(attrs={"accept": "image/*"}),
        }


class UnitOfMeasureForm(forms.ModelForm):
    class Meta:
        model = UnitOfMeasure
        fields = ["name_en", "name_ar", "code"]
        labels = {
            "name_en": _("الاسم بالإنجليزية"),
            "name_ar": _("الاسم بالعربية"),
            "code": _("رمز الوحدة (Code)"),
        }


class OrderDashboardStatusForm(forms.Form):
    status = forms.ChoiceField(
        choices=OrderStatus.choices,
        label=_("حالة الطلب"),
        widget=forms.Select(attrs={"class": "form-control"}),
    )
    payment_status = forms.ChoiceField(
        choices=PaymentStatus.choices,
        label=_("حالة الدفع"),
        widget=forms.Select(attrs={"class": "form-control"}),
    )
