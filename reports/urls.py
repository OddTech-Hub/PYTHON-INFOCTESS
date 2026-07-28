from django.urls import path
from .views import LevelSummaryView, CourseBreakdownView, CSVExportView

urlpatterns = [
    path('summary/<str:level_code>/', LevelSummaryView.as_view(), name='level-summary'),
    path('breakdown/', CourseBreakdownView.as_view(), name='course-breakdown'),
    path('export/', CSVExportView.as_view(), name='csv-export'),
]
