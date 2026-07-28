from rest_framework import serializers
from .models import AttendanceSession, AttendanceRecord, DeviceAlert
from accounts.serializers import UserSerializer
from courses.serializers import CourseSerializer


class AttendanceRecordSerializer(serializers.ModelSerializer):
    name = serializers.SerializerMethodField()
    index = serializers.SerializerMethodField()
    time = serializers.SerializerMethodField()
    avatar = serializers.SerializerMethodField()
    method = serializers.SerializerMethodField()

    class Meta:
        model = AttendanceRecord
        fields = ['id', 'name', 'index', 'time', 'avatar', 'method', 'device_name', 'device_id']

    def get_name(self, obj):
        return f"{obj.student.first_name} {obj.student.last_name}"

    def get_index(self, obj):
        return obj.student.index_number

    def get_time(self, obj):
        # Convert check-in time to local-like format (e.g., 2:48:13 PM)
        return obj.checked_in_at.strftime('%I:%M:%S %p') if obj.checked_in_at else ""

    def get_avatar(self, obj):
        first = obj.student.first_name[0] if obj.student.first_name else ""
        last = obj.student.last_name[0] if obj.student.last_name else ""
        return f"{first}{last}".upper()

    def get_method(self, obj):
        return "QR Code" if obj.method == 'qr_code' else "Session Code"


class AttendanceSessionSerializer(serializers.ModelSerializer):
    id = serializers.CharField(source='session_code')
    courseCode = serializers.CharField(source='course.code', read_only=True)
    courseName = serializers.CharField(source='course.name', read_only=True)
    date = serializers.SerializerMethodField()
    checkins = serializers.SerializerMethodField()
    students = AttendanceRecordSerializer(source='records', many=True, read_only=True)
    timeWindow = serializers.IntegerField(source='time_window_minutes')

    class Meta:
        model = AttendanceSession
        fields = [
            'id', 'course', 'courseCode', 'courseName', 'group',
            'date', 'checkins', 'status', 'timeWindow', 'students', 'qr_data'
        ]

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

    class Meta:
        model = DeviceAlert
        fields = ['id', 'name', 'index', 'alertType', 'flagReason', 'pct', 'attended', 'total', 'status']

    def get_name(self, obj):
        return f"{obj.student.first_name} {obj.student.last_name}"

    def get_index(self, obj):
        return obj.student.index_number

    def get_pct(self, obj):
        # Calculate attendance percentage for this student
        # We can implement a utility or just look up total records / sessions
        total_sessions = AttendanceSession.objects.filter(group=obj.student.group).count()
        if total_sessions == 0:
            return 100
        attended_sessions = AttendanceRecord.objects.filter(student=obj.student).count()
        return int((attended_sessions / total_sessions) * 100)

    def get_attended(self, obj):
        return AttendanceRecord.objects.filter(student=obj.student).count()

    def get_total(self, obj):
        return AttendanceSession.objects.filter(group=obj.student.group).count()
