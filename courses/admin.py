from django.contrib import admin, messages
from django.urls import path, reverse
from django.shortcuts import render, redirect
from django import forms
import csv, io
from .models import StudentGroup, Course, LecturerCourse, CourseRep
from accounts.models import User
from attendance.models import AttendanceSession


class GroupCSVImportForm(forms.Form):
    csv_file = forms.FileField(help_text="Upload a CSV with Index Number, First Name, Last Name. All students will be enrolled in this group.")


class StudentInline(admin.TabularInline):
    model = User
    extra = 1
    fields = ['index_number', 'first_name', 'last_name', 'email', 'role']
    show_change_link = True
    verbose_name = "Enrolled Student"
    verbose_name_plural = "Enrolled Students in this Group (Add Single or Edit)"

    def get_formset(self, request, obj=None, **kwargs):
        formset = super().get_formset(request, obj, **kwargs)
        # Auto-fill defaults on save
        return formset


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


class StudentGroupInline(admin.TabularInline):
    model = StudentGroup
    extra = 0
    fields = ['name', 'level', 'lecturer', 'academic_period']
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
    list_display = ['name', 'course', 'level', 'lecturer', 'enrolled_count', 'academic_period']
    list_filter = ['course', 'level', 'academic_period', 'lecturer']
    search_fields = ['name', 'course__code', 'lecturer__email', 'lecturer__username', 'lecturer__first_name']
    inlines = [CourseRepInline, StudentInline]

    @admin.display(description="Students Enrolled")
    def enrolled_count(self, obj):
        return obj.students.count()

    def get_urls(self):
        urls = super().get_urls()
        custom_urls = [
            path('<int:group_id>/import-csv/', self.admin_site.admin_view(self.import_csv_view), name='courses_studentgroup_import_csv'),
        ]
        return custom_urls + urls

    def import_csv_view(self, request, group_id):
        group = self.get_object(request, group_id)
        if not group:
            self.message_user(request, "Group not found.", level=messages.ERROR)
            return redirect("..")

        if request.method == "POST":
            form = GroupCSVImportForm(request.POST, request.FILES)
            if form.is_valid():
                csv_file = request.FILES["csv_file"]
                decoded = csv_file.read().decode('utf-8-sig', errors='ignore')
                reader = csv.reader(io.StringIO(decoded))
                raw_headers = next(reader, None)
                if not raw_headers:
                    self.message_user(request, "CSV file is empty.", level=messages.ERROR)
                    return redirect(".")

                headers = [h.strip().lower().replace(' ', '_').replace('-', '_') for h in raw_headers]
                idx_keys = ['index_number', 'index', 'index_no', 'id', 'student_id', 'matric_no']
                email_keys = ['email', 'gmail', 'mail', 'student_email']
                fname_keys = ['first_name', 'firstname', 'first']
                lname_keys = ['last_name', 'lastname', 'last']
                name_keys = ['name', 'full_name', 'fullname']

                def find_val(row_dict, keys):
                    for k in keys:
                        if k in row_dict and row_dict[k]:
                            return str(row_dict[k]).strip()
                    return ''

                success_count = 0
                for row_data in reader:
                    if not row_data or not any(row_data):
                        continue
                    row = dict(zip(headers, [v.strip() for v in row_data]))
                    index_num = find_val(row, idx_keys)
                    email = find_val(row, email_keys)

                    if not index_num and not email:
                        continue
                    if not email and index_num:
                        email = f"{index_num}@st.uew.edu.gh"
                    if not index_num and email and '@' in email:
                        prefix = email.split('@')[0]
                        if prefix.isdigit():
                            index_num = prefix

                    first_name = find_val(row, fname_keys)
                    last_name = find_val(row, lname_keys)
                    full_name = find_val(row, name_keys)
                    if full_name and (not first_name or not last_name):
                        parts = full_name.split(' ', 1)
                        first_name = parts[0]
                        last_name = parts[1] if len(parts) > 1 else ''

                    if not first_name:
                        first_name = "Student"
                    if not last_name:
                        last_name = index_num or email.split('@')[0]

                    user = User.objects.filter(index_number=index_num).first() if index_num else None
                    if not user and email:
                        user = User.objects.filter(email__iexact=email).first()

                    if user:
                        user.group = group
                        if email:
                            user.email = email
                        user.save()
                    else:
                        new_u = User.objects.create_user(
                            username=email,
                            email=email,
                            first_name=first_name,
                            last_name=last_name,
                            index_number=index_num,
                            role=User.Role.STUDENT,
                            must_change_password=True,
                            group=group
                        )
                        new_u.set_password('password123')
                        new_u.save()

                    success_count += 1

                self.message_user(request, f"Successfully enrolled {success_count} students into {group.name} ({group.level.code}).", level=messages.SUCCESS)
                return redirect(reverse("admin:courses_studentgroup_change", args=[group.id]))
        else:
            form = GroupCSVImportForm()

        context = {
            **self.admin_site.each_context(request),
            "form": form,
            "group": group,
            "title": f"Bulk Import Students into {group.name} ({group.level.code})"
        }
        return render(request, "admin/group_csv_import.html", context)


@admin.register(Course)
class CourseAdmin(admin.ModelAdmin):
    list_display = ['code', 'name', 'level', 'academic_period']
    list_filter = ['level', 'academic_period']
    search_fields = ['code', 'name']
    inlines = [LecturerCourseInline, StudentGroupInline, AttendanceSessionInline]


@admin.register(LecturerCourse)
class LecturerCourseAdmin(admin.ModelAdmin):
    list_display = ['lecturer', 'course', 'academic_period']
    list_filter = ['academic_period']
    search_fields = ['lecturer__email', 'course__code']


@admin.register(CourseRep)
class CourseRepAdmin(admin.ModelAdmin):
    list_display = ['student', 'course', 'group', 'academic_period']
    list_filter = ['academic_period']
    search_fields = ['student__username', 'group__name', 'course__code']
