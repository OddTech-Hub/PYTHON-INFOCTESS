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


def _decode_text_bytes(raw_bytes):
    if raw_bytes[:2] in (b'\xff\xfe', b'\xfe\xff'):
        try:
            return raw_bytes.decode('utf-16')
        except Exception:
            pass
    if b'\x00' in raw_bytes[:200]:
        for enc in ('utf-16', 'utf-16-le', 'utf-16-be'):
            try:
                return raw_bytes.decode(enc)
            except Exception:
                pass
    for enc in ('utf-8-sig', 'utf-8', 'cp1252', 'latin-1'):
        try:
            return raw_bytes.decode(enc)
        except Exception:
            continue
    return raw_bytes.decode('utf-8-sig', errors='ignore').replace('\x00', '')


def _read_spreadsheet_rows(uploaded_file):
    import csv
    import io

    raw_bytes = uploaded_file.read()
    filename = (getattr(uploaded_file, 'name', '') or '').lower()

    def read_xlsx():
        import openpyxl
        wb = None
        try:
            wb = openpyxl.load_workbook(io.BytesIO(raw_bytes), data_only=True)
            best_parsed = []
            for ws in wb.worksheets:
                parsed = []
                for row in ws.iter_rows(values_only=True):
                    vals = [_normalize_cell(c) for c in row]
                    if any(vals):
                        parsed.append(vals)
                if len(parsed) > len(best_parsed):
                    best_parsed = parsed
            return best_parsed
        finally:
            if wb is not None:
                try:
                    wb.close()
                except Exception:
                    pass

    def read_xls():
        import xlrd
        book = xlrd.open_workbook(file_contents=raw_bytes)
        for s_idx in range(book.nsheets):
            sheet = book.sheet_by_index(s_idx)
            parsed = []
            for r in range(sheet.nrows):
                vals = [_normalize_cell(sheet.cell_value(r, c)) for c in range(sheet.ncols)]
                if any(vals):
                    parsed.append(vals)
            if parsed:
                return parsed
        return []

    def read_csv_or_text():
        text = _decode_text_bytes(raw_bytes).replace('\x00', '')
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
        non_empty_lines = [ln for ln in text.splitlines() if ln.strip()][:10]
        sample = '\n'.join(non_empty_lines)
        try:
            dialect = csv.Sniffer().sniff(sample, delimiters=',;\t|')
            delimiter = dialect.delimiter
        except Exception:
            if '\t' in sample and ',' not in sample:
                delimiter = '\t'
            elif ';' in sample and ',' not in sample:
                delimiter = ';'
            elif '|' in sample and ',' not in sample:
                delimiter = '|'
        reader = csv.reader(io.StringIO(text), delimiter=delimiter)
        return [[_normalize_cell(c) for c in row] for row in reader if row and any(_normalize_cell(c) for c in row)]

    if raw_bytes[:4] == b'PK\x03\x04':
        try:
            return read_xlsx()
        except Exception:
            pass
    if raw_bytes[:4] == b'\xd0\xcf\x11\xe0':
        try:
            return read_xls()
        except Exception:
            pass

    if filename.endswith(('.xlsx', '.xlsm', '.xltx', '.xltm')):
        try:
            return read_xlsx()
        except Exception:
            return read_csv_or_text()

    if filename.endswith('.xls'):
        try:
            return read_xls()
        except Exception:
            text = _decode_text_bytes(raw_bytes)
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
            return read_csv_or_text()

    return read_csv_or_text()


def _classify_header_token(h):
    if not h:
        return None
    serial_tokens = {'s_n', 'sn', 'no', 'num', 'sr_no', 'serial', 'serial_no', 'serial_number', 'row', 'item'}
    if h in serial_tokens:
        return 'serial'

    idx_exact = {
        'index_number', 'index_numbers', 'index', 'index_no', 'index_nos', 'indexno',
        'idx', 'id_number', 'id_no', 'student_id', 'student_ids', 'student_no', 'student_nos',
        'std_id', 'std_no', 'stud_id', 'stud_no', 'matric_no', 'matric_number', 'matric_numbers',
        'reg_no', 'registration_number', 'registration_no', 'uew_id', 'candidate_no', 'id'
    }
    if h in idx_exact or any(sub in h for sub in ('index', 'matric', 'student_id', 'std_id', 'student_no', 'std_no', 'reg_no', 'id_no', 'id_number', 'uew_id')):
        return 'index'

    email_exact = {'email', 'emails', 'email_address', 'email_addresses', 'e_mail', 'gmail', 'g_mail', 'mail', 'student_email', 'google_mail', 'uew_email'}
    if h in email_exact or any(sub in h for sub in ('email', 'e_mail', 'gmail', 'g_mail', 'mail')):
        return 'email'

    fname_exact = {'first_name', 'first_names', 'firstname', 'first', 'given_name', 'given_names', 'forename', 'other_names', 'other_name', 'middle_name'}
    if h in fname_exact or any(sub in h for sub in ('first_name', 'firstname', 'given_name', 'other_name', 'forename')):
        return 'first_name'

    lname_exact = {'last_name', 'last_names', 'lastname', 'last', 'surname', 'surnames', 'family_name'}
    if h in lname_exact or any(sub in h for sub in ('last_name', 'lastname', 'surname', 'family_name')):
        return 'last_name'

    if h in {'group', 'student_group', 'group_name', 'class_group'}:
        return 'group'
    if h in {'level', 'level_id', 'level_code'}:
        return 'level'

    name_exact = {'name', 'names', 'full_name', 'full_names', 'fullname', 'student_name', 'student_names', 'students_name', 'candidate_name', 'student', 'students', 'learner', 'learners', 'candidate'}
    if h in name_exact or ('name' in h and not any(x in h for x in ('group', 'course', 'level', 'file', 'user', 'dept', 'department'))):
        return 'full_name'

    return None


class StudentBulkImportView(APIView):
    permission_classes = [permissions.IsAuthenticated]
    from rest_framework.parsers import MultiPartParser, FormParser, JSONParser
    parser_classes = [MultiPartParser, FormParser, JSONParser]

    def post(self, request):
        if request.user.role not in [User.Role.LECTURER, User.Role.REP] and not request.user.is_staff:
            return Response({
                'success': False,
                'message': 'Only lecturers or administrators can bulk upload students.'
            }, status=status.HTTP_403_FORBIDDEN)

        uploaded_file = request.FILES.get('file') or request.FILES.get('csv_file')
        if not uploaded_file and hasattr(request, 'FILES') and len(request.FILES) > 0:
            uploaded_file = next(iter(request.FILES.values()))
        if not uploaded_file:
            return Response({
                'success': False,
                'message': 'CSV or Excel (.xlsx / .xls) file is required.'
            }, status=status.HTTP_400_BAD_REQUEST)

        import re
        from django.db import models as django_models, transaction
        from courses.models import StudentGroup

        try:
            all_rows = _read_spreadsheet_rows(uploaded_file)
            if not all_rows:
                return Response({'success': False, 'message': 'Uploaded file is empty or unreadable.'}, status=status.HTTP_400_BAD_REQUEST)

            def norm_header(h):
                return re.sub(r'[^a-z0-9]+', '_', str(h).strip().lower()).strip('_')

            def looks_like_index(val):
                s = str(val).strip()
                if s.endswith('.0') and s[:-2].isdigit():
                    s = s[:-2]
                s_clean = s.replace(' ', '').replace('-', '').replace('/', '')
                if s.isdigit() and 5 <= len(s) <= 15:
                    return True
                if len(s_clean) >= 6 and sum(ch.isdigit() for ch in s_clean) >= 5 and '@' not in s:
                    return True
                return False

            def looks_like_email(val):
                s = str(val).strip()
                return bool(re.match(r'^[^@\s]+@[^@\s]+\.[^@\s]+$', s))

            def looks_like_name(val):
                s = str(val).strip()
                if not s or '@' in s or looks_like_index(s):
                    return False
                letters = sum(ch.isalpha() for ch in s)
                digits = sum(ch.isdigit() for ch in s)
                return letters >= 2 and digits == 0

            # 1. Detect header row within first 15 rows using exact + substring classification
            header_idx = None
            best_score = 0
            for r_idx, r_vals in enumerate(all_rows[:15]):
                normed = [norm_header(c) for c in r_vals if str(c).strip()]
                roles_found = [_classify_header_token(col) for col in normed]
                score = sum(1 for rf in roles_found if rf in ('index', 'email', 'first_name', 'last_name', 'full_name'))
                if score > best_score:
                    best_score = score
                    header_idx = r_idx

            col_map = {
                'index': None,
                'email': None,
                'first_name': None,
                'last_name': None,
                'full_name': None,
                'group': None,
                'level': None,
            }

            if header_idx is not None and best_score > 0:
                raw_headers = all_rows[header_idx]
                for c_idx, h_cell in enumerate(raw_headers):
                    role = _classify_header_token(norm_header(h_cell))
                    if role in col_map and col_map[role] is None:
                        col_map[role] = c_idx
                data_rows = all_rows[header_idx + 1:]
            else:
                # No recognized header keywords: check if row 0 is already student data or a custom header
                first_row = all_rows[0]
                row0_has_data = any(looks_like_index(c) or looks_like_email(c) for c in first_row)
                data_rows = all_rows if row0_has_data else (all_rows[1:] if len(all_rows) > 1 else all_rows)

            # 2. Content-pattern auto-detection fallback for any unmapped columns (Index, Email, Name)
            sample_rows = [r for r in data_rows if r and any(str(c).strip() for c in r)][:15]
            if sample_rows:
                max_cols = max(len(r) for r in sample_rows)
                used_cols = {c for c in col_map.values() if c is not None}

                # Detect Email column by cell values if not mapped
                if col_map['email'] is None:
                    best_c, best_hits = None, 0
                    for c_idx in range(max_cols):
                        if c_idx in used_cols:
                            continue
                        vals = [str(r[c_idx]).strip() for r in sample_rows if c_idx < len(r) and str(r[c_idx]).strip()]
                        hits = sum(1 for v in vals if looks_like_email(v))
                        if hits > best_hits:
                            best_hits = hits
                            best_c = c_idx
                    if best_c is not None and best_hits > 0:
                        col_map['email'] = best_c
                        used_cols.add(best_c)

                # Detect Index Number column by cell values if not mapped
                if col_map['index'] is None:
                    best_c, best_hits = None, 0
                    for c_idx in range(max_cols):
                        if c_idx in used_cols:
                            continue
                        vals = [str(r[c_idx]).strip() for r in sample_rows if c_idx < len(r) and str(r[c_idx]).strip()]
                        if not vals:
                            continue
                        # Ignore simple 1, 2, 3 serial number columns
                        norm_ints = [int(float(v)) for v in vals if re.match(r'^\d+(\.0)?$', v)]
                        if len(norm_ints) >= 2 and norm_ints == list(range(norm_ints[0], norm_ints[0] + len(norm_ints))) and max(norm_ints) < 1000:
                            continue
                        hits = sum(1 for v in vals if looks_like_index(v))
                        if hits > best_hits:
                            best_hits = hits
                            best_c = c_idx
                    if best_c is not None and best_hits > 0:
                        col_map['index'] = best_c
                        used_cols.add(best_c)

                # Detect Name column(s) by cell values if no name column mapped
                if col_map['full_name'] is None and col_map['first_name'] is None and col_map['last_name'] is None:
                    name_candidate_cols = []
                    for c_idx in range(max_cols):
                        if c_idx in used_cols:
                            continue
                        vals = [str(r[c_idx]).strip() for r in sample_rows if c_idx < len(r) and str(r[c_idx]).strip()]
                        hits = sum(1 for v in vals if looks_like_name(v))
                        if vals and hits >= max(1, len(vals) // 2):
                            has_spaces = sum(1 for v in vals if ' ' in v) >= max(1, len(vals) // 3)
                            name_candidate_cols.append((c_idx, hits, has_spaces))
                    if name_candidate_cols:
                        spaced = [c for c in name_candidate_cols if c[2]]
                        if spaced:
                            col_map['full_name'] = spaced[0][0]
                        elif len(name_candidate_cols) >= 2:
                            col_map['first_name'] = name_candidate_cols[0][0]
                            col_map['last_name'] = name_candidate_cols[1][0]
                        else:
                            col_map['full_name'] = name_candidate_cols[0][0]

            if not data_rows:
                return Response({'success': False, 'message': 'No student data rows found in the uploaded file.'}, status=status.HTTP_400_BAD_REQUEST)

            def get_col(row_arr, key):
                c_idx = col_map.get(key)
                if c_idx is not None and c_idx < len(row_arr):
                    return str(row_arr[c_idx]).strip()
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

            from django.contrib.auth.hashers import make_password
            default_password_hash = make_password('password123')

            # Pre-fetch existing users in 1 query to avoid N+1 database round-trips and Heroku 30s timeouts
            all_existing_users = list(User.objects.all())
            users_by_index = {}
            users_by_email = {}
            users_by_username = {}
            for u in all_existing_users:
                if u.index_number:
                    users_by_index[str(u.index_number).strip().lower()] = u
                if u.email:
                    users_by_email[u.email.strip().lower()] = u
                if u.username:
                    users_by_username[u.username.strip().lower()] = u

            group_members_map = {}  # group_id -> (group_obj, list of User)
            users_to_update = {}    # user.id -> User
            users_to_create = []    # list of (new_user, group_obj)

            for row_arr in data_rows:
                if not row_arr or not any(str(c).strip() for c in row_arr):
                    continue

                index_num = get_col(row_arr, 'index')
                provided_email = get_col(row_arr, 'email')

                # Row-level fallback scan if a cell was shifted or unmapped
                if not index_num and not provided_email:
                    for cell in row_arr:
                        c_str = str(cell).strip()
                        if not provided_email and looks_like_email(c_str):
                            provided_email = c_str
                        elif not index_num and looks_like_index(c_str):
                            index_num = c_str

                # Normalize index numbers like "5261000018.0"
                if index_num.endswith('.0') and index_num[:-2].isdigit():
                    index_num = index_num[:-2]
                index_num = index_num.strip()
                provided_email = provided_email.strip()

                # Skip accidental repeated header rows mid-sheet (never skip actual index numbers or email addresses)
                if (index_num and not looks_like_index(index_num) and _classify_header_token(norm_header(index_num)) == 'index') or (
                    provided_email and not looks_like_email(provided_email) and _classify_header_token(norm_header(provided_email)) == 'email'
                ):
                    continue

                if not index_num and not provided_email:
                    skipped_count += 1
                    continue

                # Automatic bi-directional generation: Index <-> Student Email/Gmail
                email = provided_email
                if not email and index_num:
                    clean_idx = re.sub(r'\s+', '', index_num)
                    email = f"{clean_idx}@st.uew.edu.gh"
                if not index_num and email and '@' in email:
                    prefix = email.split('@')[0].strip()
                    if prefix.isdigit():
                        index_num = prefix
                    else:
                        digits_match = re.search(r'(\d{5,15})', prefix)
                        if digits_match:
                            index_num = digits_match.group(1)

                first_name = get_col(row_arr, 'first_name')
                last_name = get_col(row_arr, 'last_name')
                full_name = get_col(row_arr, 'full_name')

                if not first_name and not last_name and not full_name:
                    for cell in row_arr:
                        c_str = str(cell).strip()
                        if c_str and c_str != index_num and c_str != provided_email and looks_like_name(c_str):
                            full_name = c_str
                            break

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

                if not first_name and email and '@' in email:
                    email_prefix = email.split('@')[0]
                    if not email_prefix.isdigit():
                        name_parts = [p.capitalize() for p in re.split(r'[._\-]+', email_prefix) if p and not p.isdigit()]
                        if name_parts:
                            first_name = name_parts[0]
                            if len(name_parts) > 1 and not last_name:
                                last_name = ' '.join(name_parts[1:])

                if not first_name:
                    first_name = "Student"
                if not last_name:
                    last_name = index_num or email.split('@')[0]

                # Resolve student group dynamically (selected dashboard group always takes priority)
                group_obj = default_group
                if explicit_target_group:
                    group_obj = explicit_target_group
                else:
                    row_group_name = get_col(row_arr, 'group')
                    level_str = get_col(row_arr, 'level') or str(level_hint or 'L100')
                    if row_group_name:
                        found_grp = base_group_qs.filter(name__iexact=row_group_name, level__code__iexact=level_str).first()
                        if not found_grp:
                            found_grp = base_group_qs.filter(name__icontains=row_group_name).first()
                        if found_grp:
                            group_obj = found_grp

                try:
                    idx_key = index_num.lower() if index_num else ''
                    p_email_key = provided_email.lower() if provided_email else ''
                    email_key = email.lower() if email else ''

                    user = None
                    if idx_key:
                        user = users_by_index.get(idx_key)
                    if not user and p_email_key:
                        user = users_by_email.get(p_email_key) or users_by_username.get(p_email_key)
                    if not user and email_key:
                        user = users_by_email.get(email_key) or users_by_username.get(email_key)
                    if not user and idx_key:
                        user = users_by_username.get(idx_key)

                    if user:
                        changed = False
                        if index_num and not user.index_number and idx_key not in users_by_index:
                            user.index_number = index_num
                            users_by_index[idx_key] = user
                            changed = True
                        if provided_email and p_email_key != (user.email or '').lower() and p_email_key not in users_by_email:
                            user.email = provided_email
                            users_by_email[p_email_key] = user
                            changed = True
                        if (not user.first_name or user.first_name == "Student") and first_name != "Student":
                            user.first_name = first_name
                            changed = True
                        if (not user.last_name or user.last_name == (user.index_number or '')) and last_name:
                            user.last_name = last_name
                            changed = True
                        if group_obj and user.group_id != group_obj.id:
                            user.group = group_obj
                            changed = True
                        if changed and user.id:
                            users_to_update[user.id] = user
                        elif changed and not user.id:
                            pass
                        if group_obj and user.id:
                            group_members_map.setdefault(group_obj.id, (group_obj, []))[1].append(user)
                        updated_count += 1
                    else:
                        uname = email or index_num
                        if uname.lower() in users_by_username:
                            uname = f"{index_num or uname.split('@')[0]}_{len(users_by_username) + 1}"
                        new_user = User(
                            username=uname,
                            email=email,
                            password=default_password_hash,
                            index_number=index_num if index_num else None,
                            first_name=first_name,
                            last_name=last_name,
                            role=User.Role.STUDENT,
                            must_change_password=True,
                            group=group_obj
                        )
                        if idx_key:
                            users_by_index[idx_key] = new_user
                        if email_key:
                            users_by_email[email_key] = new_user
                        users_by_username[uname.lower()] = new_user
                        users_to_create.append((new_user, group_obj))
                        created_count += 1
                except Exception:
                    skipped_count += 1
                    continue

            if users_to_update:
                User.objects.bulk_update(
                    list(users_to_update.values()),
                    ['index_number', 'email', 'first_name', 'last_name', 'group'],
                    batch_size=200
                )

            if users_to_create:
                new_objs = [pair[0] for pair in users_to_create]
                created_objs = User.objects.bulk_create(new_objs, batch_size=200)
                for created_u, (_, g_obj) in zip(created_objs, users_to_create):
                    if g_obj and created_u.id:
                        group_members_map.setdefault(g_obj.id, (g_obj, []))[1].append(created_u)

            for _, (g_obj, member_list) in group_members_map.items():
                if member_list:
                    g_obj.members.add(*member_list)

            if created_count == 0 and updated_count == 0:
                return Response({
                    'success': False,
                    'message': 'Could not find valid student Index Numbers or Emails in the uploaded file. Please ensure the sheet has an Index Number or Email column.'
                }, status=status.HTTP_400_BAD_REQUEST)

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
