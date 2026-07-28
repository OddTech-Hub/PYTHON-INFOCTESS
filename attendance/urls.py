from django.urls import path
from .views import (
    CreateSessionView, CloseSessionView, SessionListView,
    SessionDetailView, CheckinView, AlertListView, AlertActionView
)

urlpatterns = [
    path('sessions/create/', CreateSessionView.as_view(), name='create-session'),
    path('sessions/<str:session_code>/close/', CloseSessionView.as_view(), name='close-session'),
    path('sessions/', SessionListView.as_view(), name='session-list'),
    path('sessions/<str:session_code>/', SessionDetailView.as_view(), name='session-detail'),
    path('checkin/', CheckinView.as_view(), name='checkin'),
    path('alerts/', AlertListView.as_view(), name='alert-list'),
    path('alerts/<int:alert_id>/', AlertActionView.as_view(), name='alert-action'),
]
