from datetime import timedelta
from rest_framework import serializers
from .models import AttendanceSession, AttendanceRecord, DeviceAlert
from .utils import get_session_host_info, get_session_remaining_seconds


class AttendanceRecordSerializer(serializers.ModelSerializer):
    name = serializers.SerializerMethodField()
    index = serializers.SerializerMethodField()
    time = serializers.SerializerMethodField()
    avatar = serializers.SerializerMethodField()
    method = serializers.SerializerMethodField()

    class Meta:
        model = AttendanceRecord
        fields = ['id', 'name', 'index', 'time', 'avatar', 'method', 'status', 'receipt_code', 'device_name', 'device_id']

    def get_name(self, obj):
        return f"{obj.student.first_name} {obj.student.last_name}".strip() or obj.student.username

    def get_index(self, obj):
        return obj.student.index_number

    def get_time(self, obj):
        return obj.checked_in_at.strftime('%I:%M:%S %p') if obj.checked_in_at else ""

    def get_avatar(self, obj):
        first = obj.student.first_name[0] if obj.student.first_name else ""
        last = obj.student.last_name[0] if obj.student.last_name else ""
        return f"{first}{last}".upper() or "ST"

    def get_method(self, obj):
        if obj.method == 'qr_code':
            return "QR Code"
        if obj.method == 'manual_lecturer':
            return "Manual (Lecturer)"
        return "Session Code"


class AttendanceSessionSerializer(serializers.ModelSerializer):
    id = serializers.SerializerMethodField()
    courseCode = serializers.CharField(source='course.code', read_only=True)
    courseName = serializers.CharField(source='course.name', read_only=True)
    group_name = serializers.CharField(source='group.name', read_only=True)
    group_display = serializers.SerializerMethodField()
    host_name = serializers.SerializerMethodField()
    host_role = serializers.SerializerMethodField()
    qr_data = serializers.SerializerMethodField()
    date = serializers.SerializerMethodField()
    checkins = serializers.SerializerMethodField()
    students = AttendanceRecordSerializer(source='records', many=True, read_only=True)
    timeWindow = serializers.IntegerField(source='time_window_minutes')
    expires_at = serializers.SerializerMethodField()
    remaining_seconds = serializers.SerializerMethodField()

    class Meta:
        model = AttendanceSession
        fields = [
            'id', 'course', 'courseCode', 'courseName', 'group', 'group_name', 'group_display',
            'host_name', 'host_role', 'latitude', 'longitude', 'allowed_radius',
            'date', 'checkins', 'status', 'timeWindow', 'expires_at', 'remaining_seconds',
            'students', 'qr_data'
        ]

    def get_expires_at(self, obj):
        if not obj.opened_at:
            return None
        expiry = obj.opened_at + timedelta(minutes=max(1, obj.time_window_minutes or 10))
        return expiry.isoformat()

    def get_remaining_seconds(self, obj):
        return get_session_remaining_seconds(obj)

    def _should_hide_code(self, obj):
        return bool(self.context.get('hide_code') and obj.status == 'active')

    def get_id(self, obj):
        if self._should_hide_code(obj):
            return f"session-{obj.id}"
        return obj.session_code

    def get_qr_data(self, obj):
        if self._should_hide_code(obj):
            return None
        return obj.qr_data

    def get_group_display(self, obj):
        return str(obj.group) if obj.group else ""

    def get_host_name(self, obj):
        return get_session_host_info(obj)[0]

    def get_host_role(self, obj):
        return get_session_host_info(obj)[1]

    def get_date(self, obj):
        return obj.opened_at.strftime('%m/%d/%Y') if obj.opened_at else ""

    def get_checkins(self, obj):
        return obj.records.count()


class DeviceAlertSerializer(serializers.ModelSerializer):
    name = serializers.SerializerMethodField()
    index = serializers.SerializerMethodField()
    alertType = serializers.CharField(source='alert_type')
    flagReason = serializers.CharField(source='reason')
    pct = serializers.SerializerMethodField()
    attended = serializers.SerializerMethodField()
    total = serializers.SerializerMethodField()
    session_code = serializers.SerializerMethodField()
    course_code = serializers.SerializerMethodField()
    receipt_code = serializers.SerializerMethodField()
    record_status = serializers.SerializerMethodField()
    created_by_host = serializers.SerializerMethodField()

    class Meta:
        model = DeviceAlert
        fields = [
            'id', 'name', 'index', 'alertType', 'flagReason',
            'pct', 'attended', 'total', 'status',
            'session_code', 'course_code', 'receipt_code', 'record_status', 'created_by_host'
        ]

    def get_name(self, obj):
        return f"{obj.student.first_name} {obj.student.last_name}".strip() or obj.student.username

    def get_index(self, obj):
        return obj.student.index_number

    def get_session_code(self, obj):
        return obj.session.session_code if obj.session else None

    def get_course_code(self, obj):
        return obj.session.course.code if (obj.session and obj.session.course) else None

    def get_receipt_code(self, obj):
        return obj.attendance_record.receipt_code if obj.attendance_record else None

    def get_record_status(self, obj):
        return obj.attendance_record.status if obj.attendance_record else None

    def get_created_by_host(self, obj):
        return get_session_host_info(obj.session)[0] if obj.session else None

    def get_pct(self, obj):
        total_sessions = AttendanceSession.objects.filter(group=obj.student.group).count()
        if total_sessions == 0:
            return 0
        attended_sessions = AttendanceRecord.objects.filter(student=obj.student, status='confirmed').count()
        return int((attended_sessions / total_sessions) * 100)

    def get_attended(self, obj):
        return AttendanceRecord.objects.filter(student=obj.student, status='confirmed').count()

    def get_total(self, obj):
        return AttendanceSession.objects.filter(group=obj.student.group).count()
