"""Query-string filters for the public API.

Every list endpoint is filtered through
``django_filters.rest_framework.DjangoFilterBackend``; ``rest_framework.filters``
(DRF's ``SearchFilter``/``OrderingFilter``) is not referenced anywhere in this
package. django_filters ships no search backend, so ``SearchableFilterSet``
reproduces DRF's ``?search=`` semantics and each FilterSet declares its own
``django_filters.OrderingFilter``.
"""

import django_filters
from django import forms
from django.db.models import Q
from django.utils.translation import gettext_lazy as _
from django_filters.fields import ChoiceField

from tarcom.base.models import (
    FavouriteItem,
    Material,
    MaterialCategory,
    Order,
    Setting,
    UnitOfMeasure,
)
from tarcom.utils.enums import OrderStatus, PaymentStatus

SEARCH_HELP = _("A search term.")
ORDERING_HELP = _("Which field to use when ordering the results.")

# Accepted by the `parent` filter as shorthand for "categories without a parent".
TOP_LEVEL_KEYWORDS = ("null", "none", "root")


class SearchableFilterSet(django_filters.FilterSet):
    """Recreates DRF's ``SearchFilter``: one ``icontains`` per field, OR'd together.

    Subclasses opt in by declaring ``search_fields`` plus a ``search`` filter
    bound to ``filter_search``. FilterSets that expose no ``?search=`` simply
    don't declare one, so the parameter never reaches the OpenAPI schema.
    """

    search_fields = ()

    def filter_search(self, queryset, name, value):
        if not self.search_fields:
            return queryset
        condition = Q()
        for field in self.search_fields:
            condition |= Q(**{"%s__icontains" % field: value})
        return queryset.filter(condition)


class _CaseInsensitiveChoiceField(ChoiceField):
    """Resolve a submitted choice without regard to casing, then validate the
    canonical value, so ``?status=pending`` and ``?status=PENDING`` both mean
    ``PENDING`` while an unknown value still raises a form error (HTTP 400)."""

    def clean(self, value):
        if isinstance(value, str) and value:
            wanted = value.casefold()
            for choice, _label in list(self.choices):
                if choice and str(choice).casefold() == wanted:
                    value = choice
                    break
        return super().clean(value)


class CaseInsensitiveChoiceFilter(django_filters.ChoiceFilter):
    """``ChoiceFilter`` that accepts its choices in any casing."""

    field_class = _CaseInsensitiveChoiceField


class _ParentCategoryField(forms.CharField):
    """Validate a category id (or a top-level keyword) at form level, so a
    malformed ``?parent=`` is a 400 instead of a 500 from the ORM."""

    def clean(self, value):
        value = super().clean(value)
        if not value or value.lower() in TOP_LEVEL_KEYWORDS:
            return value
        if not value.isdigit():
            raise forms.ValidationError(
                _("Must be a category id, or one of `null`/`none`/`root`.")
            )
        return value


class ParentCategoryFilter(django_filters.CharFilter):
    """``CharFilter`` restricted to numeric ids and the top-level keywords."""

    field_class = _ParentCategoryField


class UnitOfMeasureFilter(SearchableFilterSet):
    search_fields = ("name", "name_en", "name_ar", "code")
    search = django_filters.CharFilter(method="filter_search", help_text=SEARCH_HELP)
    ordering = django_filters.OrderingFilter(
        fields=("name", "code", "created_at"), help_text=ORDERING_HELP
    )

    class Meta:
        model = UnitOfMeasure
        fields = []


class MaterialCategoryFilter(SearchableFilterSet):
    search_fields = ("name", "name_en", "name_ar")
    search = django_filters.CharFilter(method="filter_search", help_text=SEARCH_HELP)
    parent = ParentCategoryFilter(
        method="filter_parent",
        help_text=_(
            "Filter by parent category id, or one of `null`/`none`/`root` for top-level categories."
        ),
    )
    ordering = django_filters.OrderingFilter(
        fields=("name", "created_at"), help_text=ORDERING_HELP
    )

    class Meta:
        model = MaterialCategory
        fields = ["parent"]

    def filter_parent(self, queryset, name, value):
        if value.lower() in TOP_LEVEL_KEYWORDS:
            return queryset.filter(parent__isnull=True)
        return queryset.filter(parent_id=value)


class MaterialFilter(SearchableFilterSet):
    search_fields = ("name", "name_en", "name_ar")
    search = django_filters.CharFilter(method="filter_search", help_text=SEARCH_HELP)
    category = django_filters.NumberFilter(help_text=_("Filter by category id."))
    is_active = django_filters.BooleanFilter(
        help_text=_("Filter by active flag (true/false).")
    )
    ordering = django_filters.OrderingFilter(
        fields=("consumer_price", "supplier_price", "created_at", "name"),
        help_text=ORDERING_HELP,
    )

    class Meta:
        model = Material
        fields = ["category", "is_active"]


class SettingFilter(SearchableFilterSet):
    search_fields = ("key", "key_en", "key_ar")
    search = django_filters.CharFilter(method="filter_search", help_text=SEARCH_HELP)
    ordering = django_filters.OrderingFilter(fields=("key",), help_text=ORDERING_HELP)

    class Meta:
        model = Setting
        fields = []


class OrderFilter(SearchableFilterSet):
    search_fields = ("order_number", "shipping_phone", "user__email")
    search = django_filters.CharFilter(method="filter_search", help_text=SEARCH_HELP)
    status = CaseInsensitiveChoiceFilter(
        choices=OrderStatus.choices, help_text=_("Filter by order status.")
    )
    payment_status = CaseInsensitiveChoiceFilter(
        choices=PaymentStatus.choices, help_text=_("Filter by payment status.")
    )
    ordering = django_filters.OrderingFilter(
        fields=("created_at", "total_amount", "status"), help_text=ORDERING_HELP
    )

    class Meta:
        model = Order
        fields = ["status", "payment_status"]


class FavouriteItemFilter(django_filters.FilterSet):
    name = django_filters.CharFilter(
        field_name="material__name",
        lookup_expr="icontains",
        help_text=_("Filter by favourite item name."),
    )
    ordering = django_filters.OrderingFilter(
        fields=("created_at",), help_text=ORDERING_HELP
    )

    class Meta:
        model = FavouriteItem
        fields = []
