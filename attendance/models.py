from django.db import models
from django.conf import settings
from courses.models import Course, StudentGroup


class AttendanceSession(models.Model):
    STATUS_CHOICES = [
        ('active', 'Active'),
        ('closed', 'Closed'),
    ]

    session_code = models.CharField(max_length=50, unique=True)  # e.g., "ATT-4869"
    course = models.ForeignKey(Course, on_delete=models.CASCADE, related_name='sessions')
    group = models.ForeignKey(StudentGroup, on_delete=models.CASCADE, related_name='sessions')
    opened_at = models.DateTimeField(auto_now_add=True)
    closed_at = models.DateTimeField(null=True, blank=True)
    time_window_minutes = models.IntegerField(default=10)
    status = models.CharField(max_length=10, choices=STATUS_CHOICES, default='active')
    created_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='created_sessions')
    qr_data = models.TextField(blank=True, null=True)

    def __str__(self):
        return f"{self.session_code} - {self.course.code} ({self.status})"


class AttendanceRecord(models.Model):
    METHOD_CHOICES = [
        ('qr_code', 'QR Code'),
        ('session_code', 'Session Code'),
    ]

    session = models.ForeignKey(AttendanceSession, on_delete=models.CASCADE, related_name='records')
    student = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='attendance_records')
    checked_in_at = models.DateTimeField(auto_now_add=True)
    method = models.CharField(max_length=20, choices=METHOD_CHOICES, default='session_code')
    device_id = models.CharField(max_length=100, blank=True, null=True)
    device_name = models.CharField(max_length=100, blank=True, null=True)

    class Meta:
        unique_together = ('session', 'student')

    def __str__(self):
        return f"{self.student.username} checked in to {self.session.session_code}"


class DeviceAlert(models.Model):
    ALERT_TYPE_CHOICES = [
        ('multi_device', 'Multiple Device Login'),
        ('device_change', 'Device Changed'),
    ]

    STATUS_CHOICES = [
        ('open', 'Open'),
        ('confirmed', 'Confirmed'),
        ('dismissed', 'Dismissed'),
    ]

    student = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='device_alerts')
    alert_type = models.CharField(max_length=20, choices=ALERT_TYPE_CHOICES)
    reason = models.TextField()
    detected_at = models.DateTimeField(auto_now_add=True)
    status = models.CharField(max_length=15, choices=STATUS_CHOICES, default='open')

    def __str__(self):
        return f"{self.alert_type} alert for {self.student.username}"
