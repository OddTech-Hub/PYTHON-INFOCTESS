import csv
import io
from django import forms
from django.contrib import admin, messages
from django.contrib.auth.admin import UserAdmin
from django.urls import path, reverse
from django.shortcuts import render, redirect
from .models import User

class CSVImportForm(forms.Form):
    csv_file = forms.FileField()

class CustomUserAdmin(UserAdmin):
    model = User
    fieldsets = UserAdmin.fieldsets + (
        ('Custom Fields', {'fields': ('role', 'index_number', 'group', 'device_id', 'device_name')}),
    )
    add_fieldsets = UserAdmin.add_fieldsets + (
        ('Custom Fields', {'fields': ('role', 'index_number', 'group', 'device_id', 'device_name')}),
    )
    list_display = ['username', 'email', 'first_name', 'last_name', 'role', 'index_number', 'group', 'is_staff']
    list_filter = ['role', 'group', 'is_staff', 'is_superuser']
    search_fields = ['username', 'email', 'first_name', 'last_name', 'index_number']

    class Media:
        js = ('admin/js/toggle_fields.js',)

    def get_urls(self):
        urls = super().get_urls()
        my_urls = [
            path('import-csv/', self.admin_site.admin_view(self.import_csv), name='accounts_user_import_csv'),
        ]
        return my_urls + urls

    def import_csv(self, request):
        if request.method == "POST":
            form = CSVImportForm(request.POST, request.FILES)
            if form.is_valid():
                csv_file = request.FILES["csv_file"]
                decoded_file = csv_file.read().decode('utf-8')
                io_string = io.StringIO(decoded_file)
                reader = csv.reader(io_string, delimiter=',')
                
                # Parse headers flexibly (supports simple Index, Gmail CSVs)
                raw_headers = next(reader, None)
                if not raw_headers:
                    self.message_user(request, "Error: CSV is empty.", level=messages.ERROR)
                    return redirect("..")

                headers = [h.strip().lower().replace(' ', '_').replace('-', '_') for h in raw_headers]

                idx_keys = ['index_number', 'index', 'index_no', 'id', 'student_id', 'matric_no']
                email_keys = ['email', 'gmail', 'mail', 'student_email', 'google_mail']
                fname_keys = ['first_name', 'firstname', 'first', 'given_name']
                lname_keys = ['last_name', 'lastname', 'last', 'surname']
                name_keys = ['name', 'full_name', 'fullname', 'student_name']
                role_keys = ['role', 'user_role', 'type']

                def find_v(row_d, keys):
                    for k in keys:
                        if k in row_d and row_d[k]:
                            return str(row_d[k]).strip()
                    return ''

                success_count = 0
                error_count = 0
                for row_data in reader:
                    if not row_data or not any(row_data):
                        continue
                    row = dict(zip(headers, [v.strip() for v in row_data]))
                    index_number = find_v(row, idx_keys)
                    email = find_v(row, email_keys)

                    if not email and index_number:
                        email = f"{index_number}@st.uew.edu.gh"
                    if not index_number and email and '@' in email:
                        prefix = email.split('@')[0]
                        if prefix.isdigit():
                            index_number = prefix

                    if not email and not index_number:
                        error_count += 1
                        continue

                    first_name = find_v(row, fname_keys)
                    last_name = find_v(row, lname_keys)
                    full_name = find_v(row, name_keys)
                    if full_name and (not first_name or not last_name):
                        parts = full_name.split(' ', 1)
                        first_name = parts[0]
                        last_name = parts[1] if len(parts) > 1 else ''

                    if not first_name:
                        first_name = "Student"
                    if not last_name:
                        last_name = index_number or email.split('@')[0]

                    role_raw = find_v(row, role_keys).lower()
                    if role_raw in ['course_rep', 'rep']:
                        db_role = User.Role.REP
                    elif role_raw in ['lecturer', 'faculty']:
                        db_role = User.Role.LECTURER
                    else:
                        db_role = User.Role.STUDENT

                    password = row.get('password', 'password123') or 'password123'
                    level_id = row.get('level_id', 'L100')

                    if not email and index_number:
                        email = f"{index_number}@st.uew.edu.gh"

                    if not email:
                        error_count += 1
                        continue

                    # Check if already exists - update email and must_change_password
                    existing_user = User.objects.filter(index_number=index_number).first() if index_number else None
                    if not existing_user and email:
                        existing_user = User.objects.filter(email__iexact=email).first()

                    if existing_user:
                        if email:
                            existing_user.email = email
                        existing_user.must_change_password = True
                        existing_user.save()
                        success_count += 1
                        continue

                    try:
                        if role in ['course_rep', 'rep']:
                            db_role = User.Role.REP
                        elif role in ['lecturer', 'faculty']:
                            db_role = User.Role.LECTURER
                        else:
                            db_role = User.Role.STUDENT

                        user = User(
                            email=email,
                            username=email,
                            first_name=first_name,
                            last_name=last_name,
                            index_number=index_number if index_number else None,
                            role=db_role,
                            must_change_password=True
                        )
                        user.set_password(password)

                        from courses.models import StudentGroup
                        group = StudentGroup.objects.filter(level__code=level_id).first()
                        if group:
                            user.group = group

                        user.save()
                        success_count += 1
                    except Exception as e:
                        error_count += 1

                self.message_user(request, f"Successfully imported {success_count} users. Failed on {error_count} users.", level=messages.SUCCESS)
                return redirect(reverse("admin:accounts_user_changelist"))
        else:
            form = CSVImportForm()

        context = {
            **self.admin_site.each_context(request),
            "form": form,
            "title": "Import Users from CSV"
        }
        return render(request, "admin/csv_import.html", context)

admin.site.register(User, CustomUserAdmin)
