from django.contrib import admin
from .models import StudentGroup, Course, LecturerCourse, CourseRep

@admin.register(StudentGroup)
class StudentGroupAdmin(admin.ModelAdmin):
    list_display = ['name', 'level', 'academic_period']
    list_filter = ['level', 'academic_period']
    search_fields = ['name']

@admin.register(Course)
class CourseAdmin(admin.ModelAdmin):
    list_display = ['code', 'name', 'level', 'academic_period']
    list_filter = ['level', 'academic_period']
    search_fields = ['code', 'name']

@admin.register(LecturerCourse)
class LecturerCourseAdmin(admin.ModelAdmin):
    list_display = ['lecturer', 'course', 'academic_period']
    list_filter = ['academic_period']
    search_fields = ['lecturer__email', 'course__code']

@admin.register(CourseRep)
class CourseRepAdmin(admin.ModelAdmin):
    list_display = ['student', 'group', 'academic_period']
    list_filter = ['academic_period']
    search_fields = ['student__username', 'group__name']
