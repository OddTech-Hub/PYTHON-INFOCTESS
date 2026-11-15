from django.db import models

from rest_framework import status, permissions
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework_simplejwt.tokens import RefreshToken
from django.contrib.auth import authenticate
from django.contrib.auth.hashers import check_password

from .models import User
from .serializers import UserSerializer


class LecturerLoginView(APIView):
    permission_classes = [permissions.AllowAny]

    def post(self, request):
        email = request.data.get('email', '').strip().lower()
        password = request.data.get('password', '')

        if not email or not password:
            return Response({
                'success': False,
                'message': 'Email and password are required.'
            }, status=status.HTTP_400_BAD_REQUEST)

        # Lookup user across email, username, and index number
        user = User.objects.filter(
            models.Q(email__iexact=email) |
            models.Q(username__iexact=email) |
            models.Q(index_number__iexact=email)
        ).first()

        if not user or not user.check_password(password):
            return Response({
                'success': False,
                'message': 'Invalid email or password.'
            }, status=status.HTTP_401_UNAUTHORIZED)

        # STRICT ROLE ABSTRACTION: Lecturer portal only admits Lecturers
        if user.role != User.Role.LECTURER and not user.is_staff and not user.is_superuser:
            role_title = user.get_role_display()
            portal_name = "Course Rep Portal" if user.role == User.Role.REP else "Student Portal"
            return Response({
                'success': False,
                'message': f"Access Denied: Your account is registered as a {role_title}. You cannot log into the Lecturer Portal. Please use the {portal_name}."
            }, status=status.HTTP_403_FORBIDDEN)

        refresh = RefreshToken.for_user(user)
        return Response({
            'success': True,
            'message': 'Login successful.',
            'data': {
                'token': {
                    'refresh': str(refresh),
                    'access': str(refresh.access_token),
                },
                'user': UserSerializer(user).data
            }
        })


class RepLoginView(APIView):
    permission_classes = [permissions.AllowAny]

    def post(self, request):
        email_or_index = request.data.get('email', '').strip().lower() or request.data.get('index_number', '').strip().lower()
        password = request.data.get('password', '') or request.data.get('pin', '')

        if not email_or_index or not password:
            return Response({
                'success': False,
                'message': 'Email/Index and password are required.'
            }, status=status.HTTP_400_BAD_REQUEST)

        clean_input = email_or_index
        target_email = clean_input
        if '@' not in target_email:
            target_email = f"{clean_input}@st.uew.edu.gh"

        user = User.objects.filter(
            models.Q(email__iexact=target_email) |
            models.Q(email__iexact=clean_input) |
            models.Q(index_number__iexact=clean_input) |
            models.Q(username__iexact=clean_input)
        ).first()

        if not user or not user.check_password(password):
            return Response({
                'success': False,
                'message': 'Invalid Course Representative credentials.'
            }, status=status.HTTP_401_UNAUTHORIZED)

        # STRICT ROLE ABSTRACTION: Course Rep portal only admits Course Reps
        if user.role != User.Role.REP:
            role_title = user.get_role_display()
            portal_name = "Lecturer Portal" if user.role == User.Role.LECTURER else "Student Portal"
            return Response({
                'success': False,
                'message': f"Access Denied: Your account is registered as a {role_title}. You cannot log into the Course Representative Portal. Please use the {portal_name}."
            }, status=status.HTTP_403_FORBIDDEN)

        # Capture and bind rep device details
        device_id = request.data.get('device_id', '').strip()
        device_name = request.data.get('device_name', '').strip()
        updated_fields = []
        if device_id and user.device_id != device_id:
            user.device_id = device_id
            updated_fields.append('device_id')
        if device_name and user.device_name != device_name:
            user.device_name = device_name
            updated_fields.append('device_name')
        if updated_fields:
            user.save(update_fields=updated_fields)

        refresh = RefreshToken.for_user(user)
        return Response({
            'success': True,
            'message': 'Login successful.',
            'data': {
                'token': {
                    'refresh': str(refresh),
                    'access': str(refresh.access_token),
                },
                'user': UserSerializer(user).data
            }
        })


class StudentLoginView(APIView):
    permission_classes = [permissions.AllowAny]

    def post(self, request):
        email_or_index = request.data.get('email', '').strip().lower() or request.data.get('index_number', '').strip().lower()
        password = request.data.get('password', '') or request.data.get('pin', '')

        if not email_or_index or not password:
            return Response({
                'success': False,
                'message': 'Index number/Gmail and password are required.'
            }, status=status.HTTP_400_BAD_REQUEST)

        clean_input = email_or_index
        target_email = clean_input
        if '@' not in target_email:
            target_email = f"{clean_input}@st.uew.edu.gh"

        user = User.objects.filter(
            models.Q(email__iexact=target_email) |
            models.Q(email__iexact=clean_input) |
            models.Q(index_number__iexact=clean_input) |
            models.Q(username__iexact=clean_input)
        ).first()

        if not user or not user.check_password(password):
            return Response({
                'success': False,
                'message': 'Invalid index number, Gmail, or password.'
            }, status=status.HTTP_401_UNAUTHORIZED)

        # ROLE ABSTRACTION: Student portal admits Students AND Course Reps (since Course Reps are students who attend class)
        if user.role not in [User.Role.STUDENT, User.Role.REP]:
            role_title = user.get_role_display()
            return Response({
                'success': False,
                'message': f"Access Denied: Your account is registered as a {role_title}. Lecturers cannot log into the Student Portal. Please use the Lecturer Portal."
            }, status=status.HTTP_403_FORBIDDEN)

        # Capture and bind student device details
        device_id = request.data.get('device_id', '').strip()
        device_name = request.data.get('device_name', '').strip()
        updated_fields = []
        if device_id and user.device_id != device_id:
            user.device_id = device_id
            updated_fields.append('device_id')
        if device_name and user.device_name != device_name:
            user.device_name = device_name
            updated_fields.append('device_name')
        if updated_fields:
            user.save(update_fields=updated_fields)

        refresh = RefreshToken.for_user(user)
        return Response({
            'success': True,
            'message': 'Login successful.',
            'data': {
                'token': {
                    'refresh': str(refresh),
                    'access': str(refresh.access_token),
                },
                'user': UserSerializer(user).data
            }
        })


class UserProfileView(APIView):
    permission_classes = [permissions.IsAuthenticated]

    def get(self, request):
        serializer = UserSerializer(request.user)
        return Response({
            'success': True,
            'data': serializer.data
        })


class AdminUserListCreateView(APIView):
    permission_classes = [permissions.IsAdminUser]

    def get(self, request):
        users = User.objects.all().order_by('-date_joined')
        serializer = UserSerializer(users, many=True)
        return Response({
            'success': True,
            'data': serializer.data
        })

    def post(self, request):
        email = request.data.get('email', '').strip().lower()
        raw_password = request.data.get('password', '').strip()
        password = raw_password or 'password123'
        first_name = request.data.get('first_name', '')
        last_name = request.data.get('last_name', '')
        role = request.data.get('role', User.Role.LECTURER)

        if not email:
            return Response({
                'success': False,
                'message': 'Email is required.'
            }, status=status.HTTP_400_BAD_REQUEST)

        if User.objects.filter(email=email).exists():
            return Response({
                'success': False,
                'message': 'User with this email already exists.'
            }, status=status.HTTP_400_BAD_REQUEST)

        user = User(
            email=email,
            username=email,
            first_name=first_name,
            last_name=last_name,
            role=role,
            must_change_password=True
        )
        user.set_password(password)
        user.save()

        return Response({
            'success': True,
            'message': 'User created successfully.',
            'data': UserSerializer(user).data
        }, status=status.HTTP_201_CREATED)


class UserLogoutView(APIView):
    permission_classes = [permissions.AllowAny]

    def post(self, request):
        return Response({
            'success': True,
            'message': 'Logged out successfully.'
        })


class ChangePasswordView(APIView):
    permission_classes = [permissions.IsAuthenticated]

    def post(self, request):
        new_password = request.data.get('new_password', '').strip()
        confirm_password = request.data.get('confirm_password', '').strip()

        if not new_password:
            return Response({
                'success': False,
                'message': 'New password is required.'
            }, status=status.HTTP_400_BAD_REQUEST)

        if len(new_password) < 6:
            return Response({
                'success': False,
                'message': 'Password must be at least 6 characters long.'
            }, status=status.HTTP_400_BAD_REQUEST)

        if confirm_password and new_password != confirm_password:
            return Response({
                'success': False,
                'message': 'Passwords do not match.'
            }, status=status.HTTP_400_BAD_REQUEST)

        user = request.user
        user.set_password(new_password)
        user.must_change_password = False
        user.save()

        return Response({
            'success': True,
            'message': 'Password updated successfully.',
            'data': UserSerializer(user).data
        })


class AdminUserDeleteView(APIView):
    permission_classes = [permissions.IsAdminUser]

    def delete(self, request, pk):
        try:
            user = User.objects.get(pk=pk)
            user.delete()
            return Response({
                'success': True,
                'message': 'User deleted successfully.'
            })
        except User.DoesNotExist:
            return Response({
                'success': False,
                'message': 'User not found.'
            }, status=status.HTTP_404_NOT_FOUND)


def _normalize_cell(val):
    if val is None:
        return ''
    if isinstance(val, bool):
        return str(val).strip()
    if isinstance(val, int):
        return str(val).strip()
    if isinstance(val, float):
        if val.is_integer():
            return str(int(val))
        return str(val).strip()
    return str(val).strip()


def _parse_html_table_rows(text):
    import html
    import re
    rows = []
    for tr in re.findall(r'<tr[^>]*>(.*?)</tr>', text, flags=re.IGNORECASE | re.DOTALL):
        cells = re.findall(r'<t[hd][^>]*>(.*?)</t[hd]>', tr, flags=re.IGNORECASE | re.DOTALL)
        if cells:
            cleaned = [html.unescape(re.sub(r'<[^>]+>', ' ', c)).strip() for c in cells]
            cleaned = [re.sub(r'\s+', ' ', c) for c in cleaned]
            if any(cleaned):
                rows.append(cleaned)
    return rows


def _parse_spreadsheetml_rows(raw_bytes):
    import xml.etree.ElementTree as ET
    root = ET.fromstring(raw_bytes)
    rows = []
    for elem in root.iter():
        if elem.tag.lower().endswith('row'):
            row_vals = []
            for cell in elem:
                if cell.tag.lower().endswith('cell'):
                    text_parts = [t.strip() for t in cell.itertext() if t and t.strip()]
                    row_vals.append(' '.join(text_parts))
            if any(row_vals):
                rows.append(row_vals)
    return rows


def _read_spreadsheet_rows(uploaded_file):
    import csv
    import io

    raw_bytes = uploaded_file.read()
    filename = (getattr(uploaded_file, 'name', '') or '').lower()

    def read_xlsx():
        import openpyxl
        wb = openpyxl.load_workbook(io.BytesIO(raw_bytes), data_only=True, read_only=True)
        try:
            ws = wb.active
            parsed = []
            for row in ws.iter_rows(values_only=True):
                vals = [_normalize_cell(c) for c in row]
                if any(vals):
                    parsed.append(vals)
            return parsed
        finally:
            wb.close()

    def read_xls():
        import xlrd
        book = xlrd.open_workbook(file_contents=raw_bytes)
        sheet = book.sheet_by_index(0)
        parsed = []
        for r in range(sheet.nrows):
            vals = [_normalize_cell(sheet.cell_value(r, c)) for c in range(sheet.ncols)]
            if any(vals):
                parsed.append(vals)
        return parsed

    def read_csv_or_text():
        text = raw_bytes.decode('utf-8-sig', errors='ignore')
        low = text.lower()
        if '<table' in low and '<tr' in low:
            html_rows = _parse_html_table_rows(text)
            if html_rows:
                return html_rows
        if '<?xml' in low and '<row' in low:
            try:
                xml_rows = _parse_spreadsheetml_rows(raw_bytes)
                if xml_rows:
                    return xml_rows
            except Exception:
                pass
        delimiter = ','
        sample = '\n'.join(text.splitlines()[:10])
        try:
            dialect = csv.Sniffer().sniff(sample, delimiters=',;\t|')
            delimiter = dialect.delimiter
        except Exception:
            if '\t' in sample and ',' not in sample:
                delimiter = '\t'
            elif ';' in sample and ',' not in sample:
                delimiter = ';'
        reader = csv.reader(io.StringIO(text), delimiter=delimiter)
        return [[_normalize_cell(c) for c in row] for row in reader if row and any(_normalize_cell(c) for c in row)]

    if filename.endswith(('.xlsx', '.xlsm', '.xltx', '.xltm')):
        return read_xlsx()

    if filename.endswith('.xls'):
        try:
            return read_xls()
        except Exception:
            text = raw_bytes.decode('utf-8-sig', errors='ignore')
            low = text.lower()
            if '<tr' in low:
                html_rows = _parse_html_table_rows(text)
                if html_rows:
                    return html_rows
            if '<row' in low:
                try:
                    xml_rows = _parse_spreadsheetml_rows(raw_bytes)
                    if xml_rows:
                        return xml_rows
                except Exception:
                    pass
            if raw_bytes[:2] == b'PK':
                return read_xlsx()
            return read_csv_or_text()

    if raw_bytes[:4] == b'PK\x03\x04':
        return read_xlsx()
    if raw_bytes[:4] == b'\xd0\xcf\x11\xe0':
        return read_xls()
    return read_csv_or_text()


class StudentBulkImportView(APIView):
    permission_classes = [permissions.IsAuthenticated]

    def post(self, request):
        if request.user.role not in [User.Role.LECTURER, User.Role.REP] and not request.user.is_staff:
            return Response({
                'success': False,
                'message': 'Only lecturers or administrators can bulk upload students.'
            }, status=status.HTTP_403_FORBIDDEN)

        uploaded_file = request.FILES.get('file') or request.FILES.get('csv_file')
        if not uploaded_file:
            return Response({
                'success': False,
                'message': 'CSV or Excel (.xlsx / .xls) file is required.'
            }, status=status.HTTP_400_BAD_REQUEST)

        import re
        from django.db import models as django_models
        from courses.models import StudentGroup

        try:
            all_rows = _read_spreadsheet_rows(uploaded_file)
            if not all_rows:
                return Response({'success': False, 'message': 'Uploaded file is empty.'}, status=status.HTTP_400_BAD_REQUEST)

            def norm_header(h):
                cleaned = re.sub(r'[^a-z0-9]+', '_', str(h).strip().lower()).strip('_')
                return cleaned

            # Flexible column matching (singular + plural university spreadsheet headers)
            idx_keys = [
                'index_number', 'index_numbers', 'index', 'index_no', 'index_nos', 'indexno',
                'idx', 'id_number', 'student_id', 'student_ids', 'student_no', 'student_nos',
                'matric_no', 'matric_number', 'matric_numbers', 'reg_no', 'registration_number', 'id'
            ]
            email_keys = ['email', 'emails', 'email_address', 'email_addresses', 'e_mail', 'gmail', 'mail', 'student_email', 'google_mail', 'uew_email']
            fname_keys = ['first_name', 'first_names', 'firstname', 'first', 'given_name', 'other_names', 'other_name', 'middle_name']
            lname_keys = ['last_name', 'last_names', 'lastname', 'last', 'surname', 'surnames', 'family_name']
            name_keys = ['name', 'names', 'full_name', 'full_names', 'fullname', 'student_name', 'student_names', 'students_name', 'candidate_name']
            known_header_tokens = set(idx_keys + email_keys + fname_keys + lname_keys + name_keys)

            # Detect header row within first 15 rows (handles university letterhead / title rows above table)
            header_idx = 0
            best_score = -1
            for r_idx, r_vals in enumerate(all_rows[:15]):
                normed = [norm_header(c) for c in r_vals if str(c).strip()]
                score = sum(1 for col in normed if col in known_header_tokens)
                if score > best_score:
                    best_score = score
                    header_idx = r_idx

            if best_score <= 0:
                header_idx = 0

            raw_headers = all_rows[header_idx]
            headers = [norm_header(h) for h in raw_headers]
            data_rows = all_rows[header_idx + 1:]

            if not data_rows:
                return Response({'success': False, 'message': 'No student data rows found below the header row.'}, status=status.HTTP_400_BAD_REQUEST)

            def find_val(row_dict, candidate_keys):
                for k in candidate_keys:
                    if k in row_dict and row_dict[k]:
                        return str(row_dict[k]).strip()
                return ''

            target_group_id = request.data.get('group_id') or request.query_params.get('group_id')
            target_group_name = request.data.get('group_name') or request.query_params.get('group_name')
            level_hint = request.data.get('level_code') or request.data.get('level_id') or request.query_params.get('level_code') or request.query_params.get('level_id')

            base_group_qs = StudentGroup.objects.select_related('course', 'level', 'lecturer').all()
            if request.user.role == User.Role.LECTURER:
                lec_group_qs = base_group_qs.filter(lecturer=request.user)
                if lec_group_qs.exists():
                    base_group_qs = lec_group_qs

            if level_hint:
                if str(level_hint).isdigit():
                    scoped = base_group_qs.filter(django_models.Q(level_id=int(level_hint)) | django_models.Q(level__code__iexact=str(level_hint)))
                else:
                    scoped = base_group_qs.filter(level__code__iexact=str(level_hint))
                if scoped.exists():
                    base_group_qs = scoped

            explicit_target_group = None
            if target_group_id:
                explicit_target_group = StudentGroup.objects.filter(id=target_group_id).first()
            elif target_group_name:
                if " - " in target_group_name:
                    prefix, g_name = [p.strip() for p in target_group_name.split('-', 1)]
                    explicit_target_group = base_group_qs.filter(course__code__iexact=prefix, name__iexact=g_name).first()
                    if not explicit_target_group:
                        explicit_target_group = base_group_qs.filter(level__code__iexact=prefix, name__iexact=g_name).first()
                    if not explicit_target_group:
                        explicit_target_group = StudentGroup.objects.filter(course__code__iexact=prefix, name__iexact=g_name).first()
                    if not explicit_target_group:
                        explicit_target_group = StudentGroup.objects.filter(level__code__iexact=prefix, name__iexact=g_name).first()
                if not explicit_target_group:
                    explicit_target_group = base_group_qs.filter(name__iexact=target_group_name).first()
                if not explicit_target_group:
                    explicit_target_group = StudentGroup.objects.filter(name__iexact=target_group_name).first()

            default_group = explicit_target_group or base_group_qs.first() or StudentGroup.objects.first()
            created_count = 0
            updated_count = 0
            skipped_count = 0

            for row_arr in data_rows:
                if not row_arr or not any(str(c).strip() for c in row_arr):
                    continue
                padded = list(row_arr) + [''] * max(0, len(headers) - len(row_arr))
                row = {}
                for h_key, cell_val in zip(headers, padded):
                    if h_key and (h_key not in row or not row[h_key]):
                        row[h_key] = cell_val
                index_num = find_val(row, idx_keys)
                provided_email = find_val(row, email_keys)

                # Normalize index numbers like "5261000018.0" if read as string float
                if index_num.endswith('.0') and index_num[:-2].isdigit():
                    index_num = index_num[:-2]

                if not index_num and not provided_email:
                    skipped_count += 1
                    continue

                email = provided_email
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
                    if ',' in full_name:
                        surname_part, other_part = [p.strip() for p in full_name.split(',', 1)]
                        if not last_name:
                            last_name = surname_part
                        if not first_name:
                            first_name = other_part
                    else:
                        parts = full_name.split(' ', 1)
                        if not first_name:
                            first_name = parts[0]
                        if not last_name:
                            last_name = parts[1] if len(parts) > 1 else ''

                if not first_name:
                    first_name = "Student"
                if not last_name:
                    last_name = index_num or email.split('@')[0]

                # Resolve student group dynamically (selected dashboard group always takes priority)
                group_obj = default_group
                if explicit_target_group:
                    group_obj = explicit_target_group
                else:
                    row_group_name = find_val(row, ['group', 'student_group', 'group_name', 'class_group'])
                    level_str = find_val(row, ['level_id', 'level']) or str(level_hint or 'L100')
                    if row_group_name:
                        found_grp = base_group_qs.filter(name__iexact=row_group_name, level__code__iexact=level_str).first()
                        if not found_grp:
                            found_grp = base_group_qs.filter(name__icontains=row_group_name).first()
                        if found_grp:
                            group_obj = found_grp

                # Check if user already exists
                user = User.objects.filter(index_number=index_num).first() if index_num else None
                if not user and provided_email:
                    user = User.objects.filter(email__iexact=provided_email).first()
                if not user and email:
                    user = User.objects.filter(email__iexact=email).first()

                if user:
                    # Only update email if explicitly supplied in the sheet and not colliding
                    if provided_email and provided_email.lower() != (user.email or '').lower():
                        if not User.objects.filter(email__iexact=provided_email).exclude(id=user.id).exists():
                            user.email = provided_email
                    if (not user.first_name or user.first_name == "Student") and first_name != "Student":
                        user.first_name = first_name
                    if (not user.last_name or user.last_name == (user.index_number or '')) and last_name:
                        user.last_name = last_name
                    if group_obj:
                        user.group = group_obj
                    # Preserve existing student's password and must_change_password flag
                    user.save()
                    if group_obj:
                        group_obj.members.add(user)
                    updated_count += 1
                else:
                    new_user = User(
                        username=email,
                        email=email,
                        index_number=index_num if index_num else None,
                        first_name=first_name,
                        last_name=last_name,
                        role=User.Role.STUDENT,
                        must_change_password=True,
                        group=group_obj
                    )
                    # Default password is password123; student sets their own upon first login
                    new_user.set_password('password123')
                    new_user.save()
                    if group_obj:
                        group_obj.members.add(new_user)
                    created_count += 1

            target_label = explicit_target_group.name if explicit_target_group else (default_group.name if default_group else 'Default')
            if explicit_target_group and explicit_target_group.course:
                target_label = f"{explicit_target_group.course.code} - {explicit_target_group.name}"
            elif explicit_target_group and explicit_target_group.level:
                target_label = f"{explicit_target_group.level.code} - {explicit_target_group.name}"

            return Response({
                'success': True,
                'message': f'Imported into {target_label}: {created_count} new students registered, {updated_count} updated, {skipped_count} skipped.',
                'data': {
                    'created': created_count,
                    'updated': updated_count,
                    'skipped': skipped_count,
                    'group_name': target_label,
                    'group_id': explicit_target_group.id if explicit_target_group else (default_group.id if default_group else None)
                }
            })
        except Exception as err:
            return Response({
                'success': False,
                'message': f'File parsing error: {str(err)}'
            }, status=status.HTTP_400_BAD_REQUEST)
