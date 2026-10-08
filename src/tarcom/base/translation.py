from modeltranslation.translator import TranslationOptions, register

from .models import *


@register(MaterialCategory)
class MaterialCategoryTranslationOptions(TranslationOptions):
    fields = ("name",)


@register(Material)
class MaterialTranslationOptions(TranslationOptions):
    fields = ("name", "description")


@register(UnitOfMeasure)
class UnitOfMeasureTranslationOptions(TranslationOptions):
    fields = ("name",)


@register(Setting)
class SettingTranslationOptions(TranslationOptions):
    fields = ("key",)
