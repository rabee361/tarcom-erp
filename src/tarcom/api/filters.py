"""Query-string filters for the public API.

Every list endpoint is filtered through
``django_filters.rest_framework.DjangoFilterBackend``; ``rest_framework.filters``
(DRF's ``SearchFilter``/``OrderingFilter``) is not referenced anywhere in this
package. django_filters ships no search backend, so ``SearchableFilterSet``
reproduces DRF's ``?search=`` semantics and each FilterSet declares its own
``django_filters.OrderingFilter``.
"""

import django_filters
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
    ordering = django_filters.OrderingFilter(
        fields=("name", "created_at"), help_text=ORDERING_HELP
    )

    class Meta:
        model = MaterialCategory
        fields = []


# Material specs live in five positional (spec_keyN, spec_valN) column pairs.
SPEC_SLOTS = (1, 2, 3, 4, 5)

SPEC_KEY_HELP = _(
    "Match materials whose specs include this key. Pair it with the same-numbered "
    "spec_valN to require that key and value on the same spec slot."
)
SPEC_VAL_HELP = _(
    "Match materials whose specs include this value. Pair it with the same-numbered "
    "spec_keyN to require that key and value on the same spec slot."
)


class MaterialFilter(SearchableFilterSet):
    search_fields = ("name", "name_en", "name_ar")
    search = django_filters.CharFilter(method="filter_search", help_text=SEARCH_HELP)
    category = django_filters.NumberFilter(help_text=_("Filter by category id."))
    company = django_filters.CharFilter(
        lookup_expr="iexact",
        help_text=_("Filter by exact company name (case-insensitive)."),
    )
    is_active = django_filters.BooleanFilter(
        help_text=_("Filter by active flag (true/false).")
    )
    ordering = django_filters.OrderingFilter(
        fields=("consumer_price", "supplier_price", "created_at", "name"),
        help_text=ORDERING_HELP,
    )

    spec_key1 = django_filters.CharFilter(
        method="filter_spec_key", help_text=SPEC_KEY_HELP
    )
    spec_key2 = django_filters.CharFilter(
        method="filter_spec_key", help_text=SPEC_KEY_HELP
    )
    spec_key3 = django_filters.CharFilter(
        method="filter_spec_key", help_text=SPEC_KEY_HELP
    )
    spec_key4 = django_filters.CharFilter(
        method="filter_spec_key", help_text=SPEC_KEY_HELP
    )
    spec_key5 = django_filters.CharFilter(
        method="filter_spec_key", help_text=SPEC_KEY_HELP
    )
    spec_val1 = django_filters.CharFilter(
        method="filter_spec_val", help_text=SPEC_VAL_HELP
    )
    spec_val2 = django_filters.CharFilter(
        method="filter_spec_val", help_text=SPEC_VAL_HELP
    )
    spec_val3 = django_filters.CharFilter(
        method="filter_spec_val", help_text=SPEC_VAL_HELP
    )
    spec_val4 = django_filters.CharFilter(
        method="filter_spec_val", help_text=SPEC_VAL_HELP
    )
    spec_val5 = django_filters.CharFilter(
        method="filter_spec_val", help_text=SPEC_VAL_HELP
    )

    class Meta:
        model = Material
        fields = ["category", "company", "is_active"]

    def filter_spec_key(self, queryset, name, value):
        # A (spec_keyN, spec_valN) pair must land on the *same* slot, so OR the
        # per-slot ANDs together rather than matching key and value independently.
        slot_value = self.data.get(f"spec_val{name[-1]}")
        condition = Q()
        for slot in SPEC_SLOTS:
            slot_q = Q(**{f"spec_key{slot}__icontains": value})
            if slot_value:
                slot_q &= Q(**{f"spec_val{slot}__icontains": slot_value})
            condition |= slot_q
        return queryset.filter(condition)

    def filter_spec_val(self, queryset, name, value):
        # When the matching spec_keyN is present the key filter already applied the
        # pair; only act here to support value-only lookups across all slots.
        if self.data.get(f"spec_key{name[-1]}"):
            return queryset
        condition = Q()
        for slot in SPEC_SLOTS:
            condition |= Q(**{f"spec_val{slot}__icontains": value})
        return queryset.filter(condition)


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
