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
                
                # Parse headers
                headers = [h.strip().lower() for h in next(reader)]
                required = ['email', 'password', 'first_name', 'last_name', 'role']
                missing = [r for r in required if r not in headers]
                if missing:
                    self.message_user(request, f"Error: CSV missing columns: {', '.join(missing)}", level=messages.ERROR)
                    return redirect("..")

                success_count = 0
                error_count = 0
                for row_data in reader:
                    if not row_data:
                        continue
                    row = dict(zip(headers, [v.strip() for v in row_data]))
                    email = row.get('email', '')
                    password = row.get('password', 'infoctess123') or 'infoctess123'
                    first_name = row.get('first_name', '')
                    last_name = row.get('last_name', '')
                    role = row.get('role', 'student').lower()
                    index_number = row.get('index_number', '') or row.get('index', '')
                    level_id = row.get('level_id', 'L100')

                    if not email and index_number:
                        email = f"{index_number}@st.uew.edu.gh"

                    if not email:
                        error_count += 1
                        continue

                    # Check if already exists
                    if User.objects.filter(email__iexact=email).exists() or User.objects.filter(username__iexact=email).exists():
                        error_count += 1
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
