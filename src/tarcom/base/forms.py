from django import forms
from django.contrib.auth.password_validation import validate_password
from django.core.exceptions import ValidationError
from django.utils.translation import gettext_lazy as _

from tarcom.base.models import CustomUser, Material, MaterialCategory, UnitOfMeasure
from tarcom.utils.enums import OrderStatus, PaymentStatus


class DashboardLoginForm(forms.Form):
    phonenumber = forms.CharField(
        label=_("رقم الهاتف أو البريد الإلكتروني"),
        widget=forms.TextInput(attrs={
            'placeholder': _("رقم الهاتف أو البريد"),
            'class': 'form-control',
            'autofocus': True,
        })
    )
    password = forms.CharField(
        label=_("كلمة المرور"),
        widget=forms.PasswordInput(attrs={
            'placeholder': _("كلمة المرور"),
            'id': 'loginPassword',
            'class': 'form-control',
        })
    )
    remember_me = forms.BooleanField(
        required=False,
        label=_("تذكرني"),
        widget=forms.CheckboxInput(attrs={'id': 'remember-me'})
    )


class DashboardChangePasswordForm(forms.Form):
    old_password = forms.CharField(
        label=_("كلمة المرور الحالية"),
        widget=forms.PasswordInput(attrs={
            'placeholder': _("كلمة المرور الحالية"),
            'id': 'oldPassword',
        })
    )
    new_password1 = forms.CharField(
        label=_("كلمة المرور الجديدة"),
        widget=forms.PasswordInput(attrs={
            'placeholder': _("كلمة المرور الجديدة"),
            'id': 'newPassword1',
        }),
        validators=[validate_password]
    )
    new_password2 = forms.CharField(
        label=_("تأكيد كلمة المرور الجديدة"),
        widget=forms.PasswordInput(attrs={
            'placeholder': _("تأكيد كلمة المرور الجديدة"),
            'id': 'newPassword2',
        })
    )

    def __init__(self, user, *args, **kwargs):
        self.user = user
        super().__init__(*args, **kwargs)

    def clean_old_password(self):
        old_password = self.cleaned_data.get('old_password')
        if not self.user.check_password(old_password):
            raise ValidationError(_("كلمة المرور الحالية غير صحيحة."))
        return old_password

    def clean(self):
        cleaned_data = super().clean()
        p1 = cleaned_data.get('new_password1')
        p2 = cleaned_data.get('new_password2')
        if p1 and p2 and p1 != p2:
            raise ValidationError({'new_password2': _("كلمتا المرور غير متطابقتين.")})
        return cleaned_data

    def save(self):
        self.user.set_password(self.cleaned_data['new_password1'])
        self.user.save()
        return self.user


class UserForm(forms.ModelForm):
    password = forms.CharField(
        label=_("كلمة المرور"),
        required=False,
        widget=forms.PasswordInput(attrs={'placeholder': _("كلمة المرور")})
    )
    confirm_password = forms.CharField(
        label=_("تأكيد كلمة المرور"),
        required=False,
        widget=forms.PasswordInput(attrs={'placeholder': _("تأكيد كلمة المرور")})
    )

    class Meta:
        model = CustomUser
        fields = ['email', 'first_name', 'last_name', 'phone', 'user_type', 'is_active', 'avatar']
        labels = {
            'email': _("البريد الإلكتروني"),
            'first_name': _("الاسم الأول"),
            'last_name': _("اسم العائلة"),
            'phone': _("رقم الهاتف"),
            'user_type': _("نوع المستخدم"),
            'is_active': _("الحساب نشط"),
            'avatar': _("الصورة الشخصية"),
        }

    def clean(self):
        cleaned_data = super().clean()
        password = cleaned_data.get('password')
        confirm = cleaned_data.get('confirm_password')
        if not self.instance.pk and not password:
            self.add_error('password', _("كلمة المرور مطلوبة لإنشاء مستخدم جديد."))
        if password and password != confirm:
            self.add_error('confirm_password', _("كلمتا المرور غير متطابقتين."))
        return cleaned_data

    def save(self, commit=True):
        user = super().save(commit=False)
        password = self.cleaned_data.get('password')
        if password:
            user.set_password(password)
        # CustomUser.username is unique; the form does not expose it.
        if not user.username:
            user.username = user.email
        if commit:
            user.save()
        return user


class MaterialForm(forms.ModelForm):
    class Meta:
        model = Material
        fields = [
            'name', 'name_en', 'name_ar',
            'category', 'uom',
            'supplier_price', 'consumer_price',
            'description', 'description_en', 'description_ar',
            'is_active', 'image1', 'image2'
        ]
        labels = {
            'name': _("اسم المادة"),
            'name_en': _("الاسم بالإنجليزية"),
            'name_ar': _("الاسم بالعربية"),
            'category': _("التصنيف"),
            'uom': _("وحدة القياس"),
            'supplier_price': _("سعر المورد"),
            'consumer_price': _("سعر المستهلك"),
            'description': _("الوصف"),
            'description_en': _("الوصف بالإنجليزية"),
            'description_ar': _("الوصف بالعربية"),
            'is_active': _("نشط"),
            'image1': _("الصورة الرئيسية"),
            'image2': _("صورة إضافية"),
        }


class CategoryForm(forms.ModelForm):
    class Meta:
        model = MaterialCategory
        fields = ['name', 'name_en', 'name_ar', 'parent']
        labels = {
            'name': _("اسم التصنيف"),
            'name_en': _("الاسم بالإنجليزية"),
            'name_ar': _("الاسم بالعربية"),
            'parent': _("التصنيف الرئيسي (اختياري)"),
        }


class UnitOfMeasureForm(forms.ModelForm):
    class Meta:
        model = UnitOfMeasure
        fields = ['name', 'name_en', 'name_ar', 'code']
        labels = {
            'name': _("اسم الوحدة"),
            'name_en': _("الاسم بالإنجليزية"),
            'name_ar': _("الاسم بالعربية"),
            'code': _("رمز الوحدة (Code)"),
        }


class OrderDashboardStatusForm(forms.Form):
    status = forms.ChoiceField(
        choices=OrderStatus.choices,
        label=_("حالة الطلب"),
        widget=forms.Select(attrs={'class': 'form-control'})
    )
    payment_status = forms.ChoiceField(
        choices=PaymentStatus.choices,
        label=_("حالة الدفع"),
        widget=forms.Select(attrs={'class': 'form-control'})
    )
