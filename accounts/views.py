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

        user = User.objects.filter(email__iexact=email, role=User.Role.LECTURER).first()
        if not user:
            user = User.objects.filter(username__iexact=email, role=User.Role.LECTURER).first()

        if not user or not user.check_password(password):
            return Response({
                'success': False,
                'message': 'Invalid email or password.'
            }, status=status.HTTP_401_UNAUTHORIZED)

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

        user = User.objects.filter(email__iexact=target_email).first()
        if not user:
            user = User.objects.filter(email__iexact=clean_input).first()
        if not user:
            user = User.objects.filter(index_number__iexact=clean_input).first()
        if not user:
            user = User.objects.filter(username__iexact=clean_input).first()

        if not user or not user.check_password(password):
            return Response({
                'success': False,
                'message': 'Invalid student or course rep credentials.'
            }, status=status.HTTP_401_UNAUTHORIZED)

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
        password = request.data.get('password', '')
        first_name = request.data.get('first_name', '')
        last_name = request.data.get('last_name', '')
        role = request.data.get('role', User.Role.LECTURER)

        if not email or not password:
            return Response({
                'success': False,
                'message': 'Email and password are required.'
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
            role=role
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


class StudentBulkImportView(APIView):
    permission_classes = [permissions.IsAuthenticated]

    def post(self, request):
        if request.user.role not in [User.Role.LECTURER, User.Role.REP] and not request.user.is_staff:
            return Response({
                'success': False,
                'message': 'Only lecturers or administrators can bulk upload students.'
            }, status=status.HTTP_403_FORBIDDEN)

        csv_file = request.FILES.get('file') or request.FILES.get('csv_file')
        if not csv_file:
            return Response({
                'success': False,
                'message': 'CSV file is required.'
            }, status=status.HTTP_400_BAD_REQUEST)

        import csv
        import io
        from courses.models import StudentGroup

        try:
            decoded = csv_file.read().decode('utf-8-sig', errors='ignore')
            reader = csv.reader(io.StringIO(decoded))
            raw_headers = next(reader, None)
            if not raw_headers:
                return Response({'success': False, 'message': 'CSV file is empty.'}, status=status.HTTP_400_BAD_REQUEST)

            headers = [h.strip().lower().replace(' ', '_').replace('-', '_') for h in raw_headers]

            # Flexible column matching
            idx_keys = ['index_number', 'index', 'index_no', 'id', 'student_id', 'matric_no']
            email_keys = ['email', 'gmail', 'mail', 'student_email', 'google_mail']
            fname_keys = ['first_name', 'firstname', 'first', 'given_name']
            lname_keys = ['last_name', 'lastname', 'last', 'surname']
            name_keys = ['name', 'full_name', 'fullname', 'student_name']
            group_keys = ['group', 'student_group', 'group_name', 'level', 'level_id']

            def find_val(row_dict, candidate_keys):
                for k in candidate_keys:
                    if k in row_dict and row_dict[k]:
                        return str(row_dict[k]).strip()
                return ''

            default_group = StudentGroup.objects.first()
            created_count = 0
            updated_count = 0
            skipped_count = 0

            for row_arr in reader:
                if not row_arr or not any(row_arr):
                    continue
                row = dict(zip(headers, row_arr))
                index_num = find_val(row, idx_keys)
                email = find_val(row, email_keys)

                if not index_num and not email:
                    skipped_count += 1
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

                # Check if user already exists
                user = User.objects.filter(index_number=index_num).first() if index_num else None
                if not user and email:
                    user = User.objects.filter(email__iexact=email).first()

                if user:
                    if email:
                        user.email = email
                    user.must_change_password = True
                    user.save()
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
                        group=default_group
                    )
                    # Default password is set to infoctess123; student must set their own upon first login
                    new_user.set_password('password123')
                    new_user.save()
                    created_count += 1

            return Response({
                'success': True,
                'message': f'Successfully processed students: {created_count} new registered, {updated_count} updated, {skipped_count} skipped.',
                'data': {
                    'created': created_count,
                    'updated': updated_count,
                    'skipped': skipped_count
                }
            })
        except Exception as err:
            return Response({
                'success': False,
                'message': f'CSV parsing error: {str(err)}'
            }, status=status.HTTP_400_BAD_REQUEST)
