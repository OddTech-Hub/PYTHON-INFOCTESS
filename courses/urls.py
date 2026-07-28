from django.urls import path
from .views import (
    LevelListView, CourseListView, CourseDetailView, GroupListView,
    StudentListView, CourseRepView
)

urlpatterns = [
    path('levels/', LevelListView.as_view(), name='levels-list'),
    path('courses/', CourseListView.as_view(), name='courses-list'),
    path('courses/<str:code>/', CourseDetailView.as_view(), name='course-detail'),
    path('groups/', GroupListView.as_view(), name='groups-list'),
    path('students/', StudentListView.as_view(), name='students-list'),
    path('course-reps/', CourseRepView.as_view(), name='course-reps-list'),
]
