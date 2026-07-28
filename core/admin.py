from django.contrib import admin
from .models import AcademicPeriod, Level

@admin.register(AcademicPeriod)
class AcademicPeriodAdmin(admin.ModelAdmin):
    list_display = ['name', 'start_date', 'end_date', 'is_active']
    list_filter = ['is_active']
    search_fields = ['name']

@admin.register(Level)
class LevelAdmin(admin.ModelAdmin):
    list_display = ['code', 'label', 'year', 'color']
    search_fields = ['code', 'label']
