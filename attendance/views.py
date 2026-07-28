import random
from datetime import datetime
from django.db import models
from django.utils import timezone
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import status, permissions
from courses.models import Course, StudentGroup, CourseRep
from courses.helpers import get_user_rep_group_ids
from accounts.models import User
from .models import AttendanceSession, AttendanceRecord, DeviceAlert
from .serializers import AttendanceSessionSerializer, DeviceAlertSerializer


class CreateSessionView(APIView):
    permission_classes = [permissions.IsAuthenticated]

    def post(self, request):
        if request.user.role not in [User.Role.REP, User.Role.LECTURER]:
            return Response({
                'success': False,
                'message': 'Only course reps or lecturers can start a session.'
            }, status=status.HTTP_403_FORBIDDEN)

        course_id = request.data.get('course_id')
        try:
            time_window = int(request.data.get('time_window', 10))
        except (ValueError, TypeError):
            time_window = 10

        if not course_id:
            return Response({
                'success': False,
                'message': 'course_id is required.'
            }, status=status.HTTP_400_BAD_REQUEST)

        # Robust course lookup (handles numeric id or course code string like 'ICTE125')
        course = None
        if isinstance(course_id, int) or (isinstance(course_id, str) and course_id.isdigit()):
            course = Course.objects.filter(id=int(course_id)).first()
        
        if not course:
            course = Course.objects.filter(code__iexact=str(course_id).strip()).first()

        if not course:
            return Response({
                'success': False,
                'message': f"Course '{course_id}' not found."
            }, status=status.HTTP_404_NOT_FOUND)

        # Determine student group — Course Reps are strictly forced to their assigned group
        group = None
        if request.user.role == User.Role.REP or CourseRep.objects.filter(student=request.user).exists():
            rep_assignment = CourseRep.objects.filter(student=request.user).first()
            if rep_assignment and rep_assignment.group:
                group = rep_assignment.group
            elif request.user.group:
                group = request.user.group
        else:
            group_id = request.data.get('group_id')
            if group_id:
                if isinstance(group_id, int) or (isinstance(group_id, str) and group_id.isdigit()):
                    group = StudentGroup.objects.filter(id=int(group_id)).first()
                if not group:
                    group = StudentGroup.objects.filter(name__iexact=str(group_id).strip()).first()

        if not group:
            group = StudentGroup.objects.filter(level=course.level).first() or StudentGroup.objects.first()

        if not group:
            return Response({
                'success': False,
                'message': 'No Student Group available to create this session.'
            }, status=status.HTTP_400_BAD_REQUEST)

        # Close any active session for this course/group first to prevent duplicates
        AttendanceSession.objects.filter(course=course, group=group, status='active').update(
            status='closed', closed_at=timezone.now()
        )

        # Generate unique code
        code = f"ATT-{random.randint(1000, 9999)}"
        while AttendanceSession.objects.filter(session_code=code).exists():
            code = f"ATT-{random.randint(1000, 9999)}"

        # Generate QR Payload
        qr_payload = f"infoctess://session/{code}"

        session = AttendanceSession.objects.create(
            session_code=code,
            course=course,
            group=group,
            time_window_minutes=time_window,
            status='active',
            created_by=request.user,
            qr_data=qr_payload
        )

        # Auto-mark creator as Present if creator is a Course Rep or Student
        if request.user.role in [User.Role.REP, User.Role.STUDENT] or CourseRep.objects.filter(student=request.user).exists():
            AttendanceRecord.objects.get_or_create(
                session=session,
                student=request.user,
                defaults={
                    'method': 'session_code',
                    'device_id': request.user.device_id or 'rep-creator-device',
                    'device_name': request.user.device_name or 'Course Rep Device'
                }
            )

        serializer = AttendanceSessionSerializer(session)
        return Response({
            'success': True,
            'message': 'Attendance session opened successfully.',
            'data': serializer.data
        })


class CloseSessionView(APIView):
    permission_classes = [permissions.IsAuthenticated]

    def post(self, request, session_code):
        try:
            session = AttendanceSession.objects.get(session_code=session_code)
        except AttendanceSession.DoesNotExist:
            return Response({
                'success': False,
                'message': 'Session not found.'
            }, status=status.HTTP_404_NOT_FOUND)

        session.status = 'closed'
        session.closed_at = timezone.now()
        session.save()

        return Response({
            'success': True,
            'message': 'Session closed successfully.'
        })


class SessionListView(APIView):
    permission_classes = [permissions.IsAuthenticated]

    def get(self, request):
        created_by_me = request.query_params.get('created_by')
        level_id = request.query_params.get('level_id')
        course_id = request.query_params.get('course_id')

        queryset = AttendanceSession.objects.all().order_by('-opened_at')

        # Enforce Course Rep group scoping
        rep_group_ids = get_user_rep_group_ids(request.user)
        if rep_group_ids is not None:
            queryset = queryset.filter(models.Q(group_id__in=rep_group_ids) | models.Q(created_by=request.user))

        if created_by_me == 'me':
            queryset = queryset.filter(created_by=request.user)
        
        if level_id:
            queryset = queryset.filter(course__level_id=level_id)
            
        if course_id:
            queryset = queryset.filter(course_id=course_id)

        serializer = AttendanceSessionSerializer(queryset, many=True)
        return Response({
            'success': True,
            'data': serializer.data
        })


class SessionDetailView(APIView):
    permission_classes = [permissions.IsAuthenticated]

    def get(self, request, session_code):
        try:
            session = AttendanceSession.objects.get(session_code=session_code)
        except AttendanceSession.DoesNotExist:
            return Response({
                'success': False,
                'message': 'Session not found.'
            }, status=status.HTTP_404_NOT_FOUND)

        rep_group_ids = get_user_rep_group_ids(request.user)
        if rep_group_ids is not None and session.group_id not in rep_group_ids and session.created_by != request.user:
            return Response({
                'success': False,
                'message': 'You do not have permission to view session details for another class.'
            }, status=status.HTTP_403_FORBIDDEN)

        serializer = AttendanceSessionSerializer(session)
        return Response({
            'success': True,
            'data': serializer.data
        })

    def delete(self, request, session_code):
        try:
            session = AttendanceSession.objects.get(session_code=session_code)
        except AttendanceSession.DoesNotExist:
            return Response({
                'success': False,
                'message': 'Session not found.'
            }, status=status.HTTP_404_NOT_FOUND)

        session.delete()
        return Response({
            'success': True,
            'message': 'Session deleted successfully.'
        })


class CheckinView(APIView):
    # This simulates student check-ins
    permission_classes = [permissions.IsAuthenticated]

    def post(self, request):
        session_code_raw = request.data.get('session_code', '')
        student_index = request.data.get('index_number')
        method = request.data.get('method', 'session_code')  # or qr_code
        device_id = request.data.get('device_id', 'dev-default')
        device_name = request.data.get('device_name', 'Mobile Phone')

        # Clean session code (strip spaces, handle QR payload infoctess://session/ATT-XXXX)
        session_code = str(session_code_raw).strip()
        if 'session/' in session_code:
            session_code = session_code.split('session/')[-1].strip()
        if '/' in session_code:
            session_code = session_code.split('/')[-1].strip()

        # Strict session code match — must be an exact active session code
        if not session_code:
            return Response({
                'success': False,
                'message': 'Session code is required.'
            }, status=status.HTTP_400_BAD_REQUEST)

        import logging
        logger = logging.getLogger(__name__)
        logger.warning(f"[CHECKIN] Received code='{session_code}' from student={student_index}")

        session = AttendanceSession.objects.filter(session_code__iexact=session_code, status='active').first()

        if not session:
            active_codes = list(AttendanceSession.objects.filter(status='active').values_list('session_code', flat=True))
            if active_codes:
                hint = f"Active session(s): {', '.join(active_codes)}. You entered: '{session_code}'"
            else:
                hint = "There are NO active sessions right now. Ask your Course Rep or Lecturer to open a session first."
            logger.warning(f"[CHECKIN] REJECTED: {hint}")
            return Response({
                'success': False,
                'message': hint
            }, status=status.HTTP_404_NOT_FOUND)

        # Flexible student lookup
        student = None
        if student_index:
            student_str = str(student_index).strip()
            student = User.objects.filter(index_number=student_str).first() or \
                      User.objects.filter(email__iexact=student_str).first() or \
                      User.objects.filter(username__iexact=student_str).first()

        if not student and request.user.is_authenticated:
            student = request.user

        if not student:
            return Response({
                'success': False,
                'message': 'Student record not found.'
            }, status=status.HTTP_404_NOT_FOUND)

        # Check if already checked in
        if AttendanceRecord.objects.filter(session=session, student=student).exists():
            return Response({
                'success': False,
                'message': 'Student has already checked in.'
            }, status=status.HTTP_400_BAD_REQUEST)

        # ── Check for device alerts (proxy detection) ──
        
        # 1. Multi Device Login:
        # Check if another student has checked in using this device in this session
        other_checkin = AttendanceRecord.objects.filter(session=session, device_id=device_id).exclude(student=student).first()
        if other_checkin:
            reason = f"Logged in from same device as student: {other_checkin.student.first_name} {other_checkin.student.last_name} ({other_checkin.student.index_number})"
            DeviceAlert.objects.get_or_create(
                student=student,
                alert_type='multi_device',
                reason=reason,
                status='open'
            )

        # 2. Device Change:
        # Check if the student's primary device_id is different from the current device
        if student.device_id and student.device_id != device_id:
            reason = f"Device changed: {student.device_name} → {device_name}"
            DeviceAlert.objects.get_or_create(
                student=student,
                alert_type='device_change',
                reason=reason,
                status='open'
            )
        elif not student.device_id:
            # Set this as the student's primary device
            student.device_id = device_id
            student.device_name = device_name
            student.save()

        # Record check-in
        record = AttendanceRecord.objects.create(
            session=session,
            student=student,
            method=method,
            device_id=device_id,
            device_name=device_name
        )

        return Response({
            'success': True,
            'message': 'Checked in successfully.',
            'data': {
                'name': f"{student.first_name} {student.last_name}",
                'index': student.index_number,
                'time': record.checked_in_at.strftime('%I:%M:%S %p'),
                'avatar': f"{student.first_name[0]}{student.last_name[0]}".upper(),
                'method': "QR Code" if method == 'qr_code' else "Session Code",
                'session_code': session.session_code,
                'courseCode': session.course.code if session.course else '',
                'courseName': session.course.name if session.course else 'Attendance Session',
                'group': session.group.name if session.group else ''
            }
        })


class AlertListView(APIView):
    permission_classes = [permissions.IsAuthenticated]

    def get(self, request):
        level_id = request.query_params.get('level_id')
        queryset = DeviceAlert.objects.all().order_by('-detected_at')

        rep_group_ids = get_user_rep_group_ids(request.user)
        if rep_group_ids is not None:
            queryset = queryset.filter(student__group_id__in=rep_group_ids)
        elif level_id:
            queryset = queryset.filter(student__group__level_id=level_id)

        serializer = DeviceAlertSerializer(queryset, many=True)
        return Response({
            'success': True,
            'data': serializer.data
        })


class AlertActionView(APIView):
    permission_classes = [permissions.IsAuthenticated]

    def post(self, request, alert_id):
        action = request.data.get('action')  # confirm or dismiss

        alert = DeviceAlert.objects.filter(id=alert_id).first()
        if not alert:
            alert = DeviceAlert.objects.filter(student_id=alert_id, status='open').first()

        if not alert:
            return Response({
                'success': False,
                'message': 'Alert not found.'
            }, status=status.HTTP_404_NOT_FOUND)

        if action in ['confirm', 'confirmed']:
            alert.status = 'confirmed'
            alert.save()
        elif action in ['dismiss', 'dismissed']:
            alert.status = 'dismissed'
            alert.save()
        else:
            return Response({
                'success': False,
                'message': 'Invalid action. Must be confirm or dismiss.'
            }, status=status.HTTP_400_BAD_REQUEST)

        return Response({
            'success': True,
            'message': f'Alert marked as {alert.status}.'
        })

    def delete(self, request, alert_id):
        alert = DeviceAlert.objects.filter(id=alert_id).first()
        if not alert:
            alert = DeviceAlert.objects.filter(student_id=alert_id, status='open').first()

        if not alert:
            return Response({
                'success': False,
                'message': 'Alert not found.'
            }, status=status.HTTP_404_NOT_FOUND)

        alert.delete()
        return Response({
            'success': True,
            'message': 'Alert deleted successfully.'
        })
