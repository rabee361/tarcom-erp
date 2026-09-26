from modeltranslation.translator import register, TranslationOptions
from .models import MaterialCategory, Material, UnitOfMeasure


@register(MaterialCategory)
class MaterialCategoryTranslationOptions(TranslationOptions):
    fields = ('name',)


@register(Material)
class MaterialTranslationOptions(TranslationOptions):
    fields = ('name', 'description')


@register(UnitOfMeasure)
class UnitOfMeasureTranslationOptions(TranslationOptions):
    fields = ('name',)
