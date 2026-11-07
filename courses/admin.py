from django.contrib import admin
from .models import StudentGroup, Course, LecturerCourse, CourseRep
from accounts.models import User
from attendance.models import AttendanceSession


class StudentInline(admin.TabularInline):
    model = User
    extra = 0
    fields = ['username', 'first_name', 'last_name', 'index_number', 'role']
    readonly_fields = ['username', 'first_name', 'last_name', 'index_number', 'role']
    can_delete = False
    show_change_link = True
    verbose_name = "Enrolled Student"
    verbose_name_plural = "Enrolled Students in this Group"


class CourseRepInline(admin.TabularInline):
    model = CourseRep
    extra = 0
    fields = ['student', 'academic_period']
    show_change_link = True


class LecturerCourseInline(admin.TabularInline):
    model = LecturerCourse
    extra = 0
    fields = ['lecturer', 'academic_period']
    show_change_link = True


class AttendanceSessionInline(admin.TabularInline):
    model = AttendanceSession
    extra = 0
    fields = ['session_code', 'group', 'opened_at', 'status', 'created_by']
    readonly_fields = ['session_code', 'group', 'opened_at', 'status', 'created_by']
    can_delete = False
    show_change_link = True


@admin.register(StudentGroup)
class StudentGroupAdmin(admin.ModelAdmin):
    list_display = ['name', 'level', 'lecturer', 'academic_period']
    list_filter = ['level', 'academic_period']
    search_fields = ['name']
    inlines = [CourseRepInline, StudentInline]


@admin.register(Course)
class CourseAdmin(admin.ModelAdmin):
    list_display = ['code', 'name', 'level', 'academic_period']
    list_filter = ['level', 'academic_period']
    search_fields = ['code', 'name']
    inlines = [LecturerCourseInline, AttendanceSessionInline]


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
