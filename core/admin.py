from django.contrib import admin
from .models import AcademicPeriod, Level
from courses.models import Course, StudentGroup


class CourseInline(admin.TabularInline):
    model = Course
    extra = 0
    fields = ['code', 'name', 'academic_period']
    show_change_link = True


class StudentGroupInline(admin.TabularInline):
    model = StudentGroup
    extra = 0
    fields = ['name', 'lecturer', 'academic_period']
    show_change_link = True


@admin.register(AcademicPeriod)
class AcademicPeriodAdmin(admin.ModelAdmin):
    list_display = ['name', 'start_date', 'end_date', 'is_active']
    list_filter = ['is_active']
    search_fields = ['name']
    inlines = [CourseInline, StudentGroupInline]


@admin.register(Level)
class LevelAdmin(admin.ModelAdmin):
    list_display = ['code', 'label', 'year', 'color']
    search_fields = ['code', 'label']
    inlines = [CourseInline, StudentGroupInline]
