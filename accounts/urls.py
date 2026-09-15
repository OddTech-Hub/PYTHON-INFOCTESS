from django.urls import path
from .views import (
    LecturerLoginView, RepLoginView, UserProfileView, UserLogoutView,
    AdminUserListCreateView, AdminUserDeleteView, ChangePasswordView
)

urlpatterns = [
    path('lecturer/login/', LecturerLoginView.as_view(), name='lecturer-login'),
    path('rep/login/', RepLoginView.as_view(), name='rep-login'),
    path('change-password/', ChangePasswordView.as_view(), name='change-password'),
    path('logout/', UserLogoutView.as_view(), name='logout'),
    path('me/', UserProfileView.as_view(), name='user-profile'),
    path('admin/users/', AdminUserListCreateView.as_view(), name='admin-users-list-create'),
    path('admin/users/<int:pk>/', AdminUserDeleteView.as_view(), name='admin-users-delete'),
]
