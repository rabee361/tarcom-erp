import logging

from django.conf import settings
from django.utils import translation as django_translation

logger = logging.getLogger(__name__)


def get_language_codes():
    try:
        codes = getattr(settings, 'MODELTRANSLATION_LANGUAGES', None)
        if isinstance(codes, str):
            codes = [codes]
        if not codes:
            languages = getattr(settings, 'LANGUAGES', None)
            if isinstance(languages, str):
                languages = [languages]
            if languages:
                codes = [lang[0] if isinstance(lang, (tuple, list)) else str(lang) for lang in languages]
        if not codes:
            codes = ['en']
        return [str(code) for code in codes]
    except Exception as exc:
        logger.warning("get_language_codes falling back to ['en']: %s", exc)
        return ['en']


def translate_message(message, lang_code):
    try:
        with django_translation.override(lang_code):
            return str(django_translation.gettext(message))
    except Exception as exc:
        logger.warning("translate_message(%r, %r) failed: %s", message, lang_code, exc)
        return str(message)
