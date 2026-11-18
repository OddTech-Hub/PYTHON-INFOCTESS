from django.urls import path
from .views import (
    CreateSessionView, CloseSessionView, ExtendSessionView,
    ManualMarkPresentView, SessionListView,
    SessionDetailView, CheckinView, AlertListView, AlertActionView
)

urlpatterns = [
    path('sessions/create/', CreateSessionView.as_view(), name='create-session'),
    path('sessions/<str:session_code>/close/', CloseSessionView.as_view(), name='close-session'),
    path('sessions/<str:session_code>/extend/', ExtendSessionView.as_view(), name='extend-session'),
    path('sessions/<str:session_code>/manual-mark/', ManualMarkPresentView.as_view(), name='manual-mark-present'),
    path('sessions/', SessionListView.as_view(), name='session-list'),
    path('sessions/<str:session_code>/', SessionDetailView.as_view(), name='session-detail'),
    path('checkin/', CheckinView.as_view(), name='checkin'),
    path('alerts/', AlertListView.as_view(), name='alert-list'),
    path('alerts/<int:alert_id>/', AlertActionView.as_view(), name='alert-action'),
]
