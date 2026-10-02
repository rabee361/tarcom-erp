from django.core.validators import RegexValidator
from django.utils.translation import gettext_lazy as _

PhoneNumberValidator = RegexValidator(
    regex=r'^\+963[0-9]{9}$',
    message=_('Phone number must start with +963 followed by 9 digits: +963XXXXXXXXX.')
)