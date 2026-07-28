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
