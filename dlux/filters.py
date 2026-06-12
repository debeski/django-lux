# Imports of the required python modules and libraries
######################################################
import django_filters
from django.contrib.auth import get_user_model
from crispy_forms.helper import FormHelper
from crispy_forms.layout import Layout, Row, Column, Field, HTML, Hidden
from django.db.models import Q
from django.apps import apps
from dlux.utils import is_scope_enabled, set_first_choice
from dlux.translations import get_strings
from django.conf import settings as django_settings

User = get_user_model()


class UserFilter(django_filters.FilterSet):
    keyword = django_filters.CharFilter(
        method='filter_keyword',
        label='',
    )
    class Meta:
        model = User
        fields = []
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        # Placeholder for setup_filter_helper which handles layout
        pass

    def filter_keyword(self, queryset, name, value):
        return queryset.filter(
            Q(username__icontains=value) |
            Q(email__icontains=value) |
            Q(profile__phone__icontains=value) | # Updated lookup
            Q(profile__scope__name__icontains=value) | # Updated lookup
            Q(first_name__icontains=value) |
            Q(last_name__icontains=value)
        )


class UserActivityLogFilter(django_filters.FilterSet):
    keyword = django_filters.CharFilter(
        method='filter_keyword',
        label='',
    )
    year = django_filters.ChoiceFilter(
        field_name="created_at__year",
        lookup_expr="exact",
        choices=[],
        empty_label="السنة",
    )
    scope = django_filters.ModelChoiceFilter(
        queryset=apps.get_model('dlux', 'Scope').objects.all(),
        field_name='created_by__profile__scope',
        label="النطاق",
        empty_label="الكل",
        required=False
    )
    class Meta:
        model = apps.get_model('dlux', 'UserActivityLog')
        fields = {
            'created_at': ['gte', 'lte'],
        }
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        s = get_strings()

        # Update labels from translations
        year_label = s.get('filter_year', 'السنة')
        self.filters['year'].label = year_label
        self.filters['year'].extra['empty_label'] = year_label
        if 'scope' in self.filters:
            scope_label = s.get('filter_scope', 'النطاق')
            self.filters['scope'].extra['empty_label'] = s.get('filter_all', 'الكل')
            self.filters['scope'].label = scope_label
        
        years = self.Meta.model.objects.dates('created_at', 'year').distinct()
        self.filters['year'].extra['choices'] = [(year.year, year.year) for year in years]
        self.filters['year'].field.widget.attrs.update({
            'class': 'auto-submit-filter'
        })
        set_first_choice(self.filters['year'].field, year_label)
        if 'scope' in self.filters:
            self.filters['scope'].field.widget.attrs.update({
                'class': 'auto-submit-filter'
            })
        
        # Layout handled by setup_filter_helper in the view
        pass

    def filter_keyword(self, queryset, name, value):
        return queryset.filter(
            Q(created_by__username__icontains=value) |
            Q(created_by__email__icontains=value) |
            Q(created_by__profile__phone__icontains=value) |
            Q(action__icontains=value) |
            Q(model_name__icontains=value) |
            Q(number__icontains=value) |
            Q(ip_address__icontains=value)
        )
