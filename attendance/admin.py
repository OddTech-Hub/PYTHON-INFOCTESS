from django.contrib import admin
from .models import AttendanceSession, AttendanceRecord, DeviceAlert

@admin.register(AttendanceSession)
class AttendanceSessionAdmin(admin.ModelAdmin):
    list_display = ['session_code', 'course', 'group', 'opened_at', 'closed_at', 'status', 'created_by']
    list_filter = ['status', 'opened_at']
    search_fields = ['session_code', 'course__code', 'group__name']

@admin.register(AttendanceRecord)
class AttendanceRecordAdmin(admin.ModelAdmin):
    list_display = ['session', 'student', 'checked_in_at', 'method', 'device_name']
    list_filter = ['method', 'checked_in_at']
    search_fields = ['student__username', 'session__session_code', 'device_name']

@admin.register(DeviceAlert)
class DeviceAlertAdmin(admin.ModelAdmin):
    list_display = ['student', 'alert_type', 'reason', 'detected_at', 'status']
    list_filter = ['alert_type', 'status', 'detected_at']
    search_fields = ['student__username', 'reason']
