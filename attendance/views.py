import random
from django.db import models
from django.utils import timezone
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import status, permissions
from courses.models import Course, StudentGroup, CourseRep, LecturerCourse
from courses.helpers import get_user_rep_group_ids, get_rep_scope_q
from accounts.models import User
from .models import AttendanceSession, AttendanceRecord, DeviceAlert
from .serializers import AttendanceSessionSerializer, DeviceAlertSerializer
from .utils import (
    validate_rotating_code,
    close_expired_sessions,
    haversine_meters,
    get_session_host_info,
    assign_next_receipt_code,
)


class CreateSessionView(APIView):
    permission_classes = [permissions.IsAuthenticated]

    def post(self, request):
        close_expired_sessions()
        if request.user.role not in [User.Role.REP, User.Role.LECTURER]:
            return Response({
                'success': False,
                'message': 'Only course reps or lecturers can start a session.'
            }, status=status.HTTP_403_FORBIDDEN)

        course_id = request.data.get('course_id')
        try:
            time_window = max(1, min(180, int(request.data.get('time_window', 10))))
        except (ValueError, TypeError):
            time_window = 10

        try:
            allowed_radius = max(15, min(1000, int(request.data.get('allowed_radius', 50))))
        except (ValueError, TypeError):
            allowed_radius = 50

        lat_raw = request.data.get('latitude', request.data.get('lat'))
        lng_raw = request.data.get('longitude', request.data.get('lng'))
        try:
            session_lat = float(lat_raw) if lat_raw is not None and lat_raw != '' else None
            session_lng = float(lng_raw) if lng_raw is not None and lng_raw != '' else None
        except (ValueError, TypeError):
            session_lat, session_lng = None, None

        if session_lat is None or session_lng is None:
            return Response({
                'success': False,
                'message': 'Classroom GPS location is required before starting a session. Please turn on Location/GPS in your browser and try again.'
            }, status=status.HTTP_400_BAD_REQUEST)

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

        # Determine student group — Course Reps are strictly forced to their assigned course and group
        group = None
        if request.user.role == User.Role.REP:
            rep_qs = CourseRep.objects.filter(student=request.user).filter(
                models.Q(course=course) | models.Q(group__course=course)
            ).select_related('group')
            requested_gid = request.data.get('group_id')
            if requested_gid:
                if isinstance(requested_gid, int) or str(requested_gid).isdigit():
                    rep_qs = rep_qs.filter(group_id=int(requested_gid))
                else:
                    raw_g = str(requested_gid).strip()
                    g_part = raw_g.split('-', 1)[1].strip() if ' - ' in raw_g else raw_g
                    rep_qs = rep_qs.filter(group__name__iexact=g_part)
            rep_assignment = rep_qs.first()
            if not rep_assignment or not rep_assignment.group:
                return Response({
                    'success': False,
                    'message': f"Access Denied: You are only permitted to start sessions for your specifically assigned course and group (not {course.code})."
                }, status=status.HTTP_403_FORBIDDEN)
            group = rep_assignment.group
        else:
            group_id = request.data.get('group_id')
            if group_id:
                if isinstance(group_id, int) or (isinstance(group_id, str) and group_id.isdigit()):
                    group = StudentGroup.objects.filter(id=int(group_id)).first()
                if not group and " - " in str(group_id):
                    c_code, g_name = [p.strip() for p in str(group_id).split('-', 1)]
                    group = StudentGroup.objects.filter(course__code__iexact=c_code, name__iexact=g_name).first()
                if not group:
                    group = StudentGroup.objects.filter(course=course, name__iexact=str(group_id).strip()).first() or \
                            StudentGroup.objects.filter(name__iexact=str(group_id).strip()).first()

        if not group:
            group = StudentGroup.objects.filter(course=course, lecturer=request.user).first() or \
                    StudentGroup.objects.filter(course=course, level=course.level).first() or \
                    StudentGroup.objects.filter(course=course).first()

        if not group and request.user.role == User.Role.LECTURER:
            from core.models import AcademicPeriod
            period = AcademicPeriod.objects.filter(is_active=True).first() or AcademicPeriod.objects.first()
            if not period:
                period = AcademicPeriod.objects.create(name='2025/2026 Academic Year — Semester 2', is_active=True)
            group, _ = StudentGroup.objects.get_or_create(
                name="Group 1",
                course=course,
                level=course.level,
                lecturer=request.user,
                defaults={'academic_period': period}
            )
            LecturerCourse.objects.get_or_create(
                lecturer=request.user,
                course=course,
                defaults={'academic_period': period}
            )

        if not group:
            return Response({
                'success': False,
                'message': 'No Student Group available to create this session.'
            }, status=status.HTTP_400_BAD_REQUEST)

        # Close any active session for this course/group first to prevent duplicates
        AttendanceSession.objects.filter(course=course, group=group, status='active').update(
            status='closed', closed_at=timezone.now()
        )

        # Generate unique base session code
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
            qr_data=qr_payload,
            latitude=session_lat,
            longitude=session_lng,
            allowed_radius=allowed_radius
        )

        # Auto-mark creator as Present if creator is a Course Rep or Student
        if request.user.role in [User.Role.REP, User.Role.STUDENT] or CourseRep.objects.filter(student=request.user).exists():
            existing_creator_rec = AttendanceRecord.objects.filter(session=session, student=request.user).first()
            if not existing_creator_rec:
                receipt_code = assign_next_receipt_code(session, request.user)
                AttendanceRecord.objects.create(
                    session=session,
                    student=request.user,
                    method='session_code',
                    status='confirmed',
                    device_id=request.user.device_id or 'rep-creator-device',
                    device_name=request.user.device_name or 'Course Rep Device',
                    receipt_code=receipt_code
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


class ExtendSessionView(APIView):
    """Extends an active session's time window (e.g. +5 mins) cleanly."""
    permission_classes = [permissions.IsAuthenticated]

    def post(self, request, session_code):
        close_expired_sessions()
        if request.user.role not in [User.Role.REP, User.Role.LECTURER] and not request.user.is_staff:
            return Response({'success': False, 'message': 'Permission denied.'}, status=status.HTTP_403_FORBIDDEN)

        session = AttendanceSession.objects.filter(session_code=session_code).select_related('course', 'group', 'created_by').first()
        if not session:
            return Response({'success': False, 'message': 'Session not found.'}, status=status.HTTP_404_NOT_FOUND)
        if session.status != 'active':
            return Response({'success': False, 'message': 'This session has already closed and cannot be extended.'}, status=status.HTTP_400_BAD_REQUEST)

        if request.user.role == User.Role.REP and session.created_by != request.user:
            return Response({'success': False, 'message': 'You can only extend sessions you created.'}, status=status.HTTP_403_FORBIDDEN)

        try:
            extra_minutes = max(1, min(30, int(request.data.get('minutes', 5))))
        except (ValueError, TypeError):
            extra_minutes = 5

        session.time_window_minutes = min(240, (session.time_window_minutes or 10) + extra_minutes)
        session.save(update_fields=['time_window_minutes'])

        serializer = AttendanceSessionSerializer(session)
        return Response({
            'success': True,
            'message': f'Session extended by +{extra_minutes} minutes.',
            'data': serializer.data
        })


class ManualMarkPresentView(APIView):
    """Allows a Lecturer to manually mark a student present (e.g. phone GPS failure), logged transparently."""
    permission_classes = [permissions.IsAuthenticated]

    def post(self, request, session_code):
        if request.user.role != User.Role.LECTURER and not request.user.is_staff:
            return Response({
                'success': False,
                'message': 'Only Lecturers can manually mark a student present.'
            }, status=status.HTTP_403_FORBIDDEN)

        session = AttendanceSession.objects.filter(session_code=session_code).select_related('course', 'group').first()
        if not session:
            return Response({'success': False, 'message': 'Session not found.'}, status=status.HTTP_404_NOT_FOUND)

        student_id = request.data.get('student_id')
        index_number = str(request.data.get('index_number') or '').strip()

        student = None
        if student_id:
            student = User.objects.filter(id=student_id).first()
        if not student and index_number:
            student = User.objects.filter(
                models.Q(index_number__iexact=index_number) |
                models.Q(email__iexact=index_number) |
                models.Q(username__iexact=index_number)
            ).first()

        if not student:
            return Response({'success': False, 'message': 'Student not found.'}, status=status.HTTP_404_NOT_FOUND)

        existing = AttendanceRecord.objects.filter(session=session, student=student).first()
        if existing:
            if existing.status == 'flagged':
                if not existing.receipt_code:
                    existing.receipt_code = assign_next_receipt_code(session, student)
                existing.status = 'confirmed'
                existing.save(update_fields=['status', 'receipt_code'])
                DeviceAlert.objects.filter(student=student, session=session, status='open').update(status='confirmed')
            return Response({
                'success': True,
                'message': f'{student.first_name} {student.last_name} is marked Present ({existing.receipt_code}).',
                'data': {
                    'name': f"{student.first_name} {student.last_name}".strip(),
                    'index': student.index_number,
                    'receipt_code': existing.receipt_code,
                    'method': 'Manual (Lecturer)',
                    'status': 'confirmed'
                }
            })

        lec_label = f"{request.user.first_name} {request.user.last_name}".strip() or request.user.username
        receipt_code = assign_next_receipt_code(session, student)
        record = AttendanceRecord.objects.create(
            session=session,
            student=student,
            method='manual_lecturer',
            status='confirmed',
            device_id='manual-lecturer',
            device_name=f"Manual by {lec_label}"[:100],
            receipt_code=receipt_code
        )
        return Response({
            'success': True,
            'message': f'Manually marked {student.first_name} {student.last_name} Present ({receipt_code}).',
            'data': {
                'id': record.id,
                'name': f"{student.first_name} {student.last_name}".strip(),
                'index': student.index_number,
                'time': record.checked_in_at.strftime('%I:%M:%S %p'),
                'receipt_code': receipt_code,
                'method': 'Manual (Lecturer)',
                'status': 'confirmed'
            }
        })


class SessionListView(APIView):
    permission_classes = [permissions.IsAuthenticated]

    def get(self, request):
        close_expired_sessions()
        created_by_me = request.query_params.get('created_by')
        level_id = request.query_params.get('level_id')
        course_id = request.query_params.get('course_id')

        queryset = AttendanceSession.objects.select_related(
            'course', 'group', 'created_by'
        ).prefetch_related('records__student').order_by('-opened_at')

        # Enforce strict Course Rep (course, group) scoping
        if request.user.role == User.Role.REP:
            queryset = queryset.filter(get_rep_scope_q(request.user, course_field='course_id', group_field='group_id'))
        elif request.user.role == User.Role.LECTURER:
            queryset = queryset.filter(
                models.Q(created_by=request.user) |
                models.Q(group__lecturer=request.user) |
                models.Q(course__lecturers__lecturer=request.user)
            ).distinct()
        else:
            rep_group_ids = get_user_rep_group_ids(request.user)
            if rep_group_ids is not None:
                queryset = queryset.filter(models.Q(group_id__in=rep_group_ids) | models.Q(created_by=request.user))

        if created_by_me == 'me':
            queryset = queryset.filter(created_by=request.user)
        
        if level_id:
            queryset = queryset.filter(course__level_id=level_id)
            
        if course_id:
            queryset = queryset.filter(course_id=course_id)

        serializer = AttendanceSessionSerializer(
            queryset,
            many=True,
            context={'hide_code': request.user.role == User.Role.STUDENT}
        )
        return Response({
            'success': True,
            'data': serializer.data
        })


class SessionDetailView(APIView):
    permission_classes = [permissions.IsAuthenticated]

    def get(self, request, session_code):
        close_expired_sessions()
        try:
            session = AttendanceSession.objects.get(session_code=session_code)
        except AttendanceSession.DoesNotExist:
            return Response({
                'success': False,
                'message': 'Session not found.'
            }, status=status.HTTP_404_NOT_FOUND)

        if request.user.role == User.Role.REP:
            if not AttendanceSession.objects.filter(pk=session.pk).filter(
                get_rep_scope_q(request.user, course_field='course_id', group_field='group_id')
            ).exists():
                return Response({
                    'success': False,
                    'message': 'You do not have permission to view session details for another course or group.'
                }, status=status.HTTP_403_FORBIDDEN)
        else:
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
    permission_classes = [permissions.IsAuthenticated]

    def post(self, request):
        close_expired_sessions()
        session_code_raw = request.data.get('session_code', '')
        student_index = request.data.get('index_number')
        method = request.data.get('method', 'session_code')
        device_id = str(request.data.get('device_id') or '').strip() or 'dev-default'
        device_name = str(request.data.get('device_name') or 'Mobile Phone').strip()[:100]

        lat_raw = request.data.get('lat', request.data.get('latitude'))
        lng_raw = request.data.get('lng', request.data.get('longitude'))
        acc_raw = request.data.get('accuracy')
        try:
            student_lat = float(lat_raw) if lat_raw is not None and lat_raw != '' else None
            student_lng = float(lng_raw) if lng_raw is not None and lng_raw != '' else None
            gps_accuracy = float(acc_raw) if acc_raw is not None and acc_raw != '' else 0.0
        except (ValueError, TypeError):
            student_lat, student_lng, gps_accuracy = None, None, 0.0

        if not str(session_code_raw).strip():
            return Response({
                'success': False,
                'message': 'Session code is required.'
            }, status=status.HTTP_400_BAD_REQUEST)

        # Resolve student safely (authenticated student/rep takes precedence)
        student = None
        if request.user.is_authenticated and request.user.role in [User.Role.STUDENT, User.Role.REP]:
            student = request.user
        elif student_index:
            student_str = str(student_index).strip()
            student = (
                User.objects.filter(index_number=student_str).first() or
                User.objects.filter(email__iexact=student_str).first() or
                User.objects.filter(username__iexact=student_str).first()
            )
        elif request.user.is_authenticated:
            student = request.user

        if not student:
            return Response({
                'success': False,
                'message': 'Student record not found.'
            }, status=status.HTTP_404_NOT_FOUND)

        # Validate strictly against currently ACTIVE sessions' live 90s rotating code
        active_sessions = list(
            AttendanceSession.objects.filter(status='active')
            .select_related('course', 'group', 'created_by')
            .order_by('-opened_at')
        )
        matching_sessions = [
            s for s in active_sessions
            if validate_rotating_code(session_code_raw, s.session_code)
        ]

        if not matching_sessions:
            return Response({
                'success': False,
                'message': 'Invalid or expired session code. Please scan or enter the active code shown on your Lecturer or Course Rep dashboard.'
            }, status=status.HTTP_404_NOT_FOUND)

        # Prefer an active session matching the student's enrolled group if multiple exist
        student_group_ids = set(student.enrolled_groups.values_list('id', flat=True))
        if student.group_id:
            student_group_ids.add(student.group_id)

        session = next((s for s in matching_sessions if s.group_id in student_group_ids), None)
        if not session:
            # If the student belongs to another group in the same course or another class,
            # use first match if group has no strict enrollment list, else enforce group check
            candidate = matching_sessions[0]
            has_roster = candidate.group and (
                User.objects.filter(group=candidate.group).exists() or
                candidate.group.members.exists()
            )
            if has_roster and student_group_ids and candidate.group_id not in student_group_ids:
                return Response({
                    'success': False,
                    'message': f"This active session is for {candidate.group}, which you are not enrolled in."
                }, status=status.HTTP_403_FORBIDDEN)
            session = candidate

        host_display, host_role = get_session_host_info(session)

        # Enforce STRICT classroom geofencing distance set by session creator (no inflated buffer)
        if session.latitude is not None and session.longitude is not None:
            if student_lat is None or student_lng is None:
                return Response({
                    'success': False,
                    'message': 'Location access is required to verify you are in the lecture hall. Please enable GPS and try again.'
                }, status=status.HTTP_403_FORBIDDEN)
            dist_m = haversine_meters(session.latitude, session.longitude, student_lat, student_lng)
            allowed_m = float(session.allowed_radius or 50)
            if dist_m > allowed_m:
                return Response({
                    'success': False,
                    'message': f"You are not in the lecture hall ({int(round(dist_m))}m away; allowed radius is {int(allowed_m)}m). Please go there to check in."
                }, status=status.HTTP_403_FORBIDDEN)

        # Check duplicate check-in
        existing_record = AttendanceRecord.objects.filter(session=session, student=student).first()
        if existing_record:
            if existing_record.status == 'flagged':
                return Response({
                    'success': True,
                    'flagged': True,
                    'status': 'flagged',
                    'message': 'Your attendance on this shared/new device is already Flagged. Please contact your Lecturer to confirm it before your sequential attendance code is issued.',
                    'data': {
                        'name': f"{student.first_name} {student.last_name}".strip(),
                        'index': student.index_number,
                        'time': existing_record.checked_in_at.strftime('%I:%M:%S %p'),
                        'avatar': f"{student.first_name[:1]}{student.last_name[:1]}".upper() or 'ST',
                        'method': "QR Code" if existing_record.method == 'qr_code' else "Session Code",
                        'session_code': session.session_code,
                        'receipt_code': None,
                        'ref_id': None,
                        'status': 'flagged',
                        'flagged': True,
                        'host': host_display,
                        'host_role': host_role,
                        'courseCode': session.course.code if session.course else '',
                        'courseName': session.course.name if session.course else 'Attendance Session',
                        'group': session.group.name if session.group else ''
                    }
                })
            return Response({
                'success': False,
                'message': f"You have already marked attendance for this session ({existing_record.receipt_code or 'Confirmed'})."
            }, status=status.HTTP_400_BAD_REQUEST)

        # Shared / changed device check BEFORE mutating student.device_id
        has_real_device = device_id and device_id != 'dev-default'
        other_in_session = (
            AttendanceRecord.objects.filter(session=session, device_id=device_id)
            .exclude(student=student)
            .select_related('student')
            .first()
            if has_real_device else None
        )
        other_bound_user = (
            User.objects.filter(device_id=device_id).exclude(id=student.id).first()
            if has_real_device else None
        )
        student_changed_device = bool(has_real_device and student.device_id and student.device_id != device_id)

        if other_in_session or other_bound_user or student_changed_device:
            if other_in_session:
                alert_type = 'multi_device'
                reason = f"Device already used in {session.course.code} by {other_in_session.student.first_name} {other_in_session.student.last_name} ({other_in_session.student.index_number})"
            elif other_bound_user:
                alert_type = 'multi_device'
                reason = f"Device is already registered to {other_bound_user.first_name} {other_bound_user.last_name} ({other_bound_user.index_number})"
            else:
                alert_type = 'device_change'
                reason = f"Device changed: {student.device_name or student.device_id} → {device_name}"

            record = AttendanceRecord.objects.create(
                session=session,
                student=student,
                method=method,
                status='flagged',
                device_id=device_id,
                device_name=device_name,
                receipt_code=None
            )
            DeviceAlert.objects.create(
                student=student,
                session=session,
                attendance_record=record,
                alert_type=alert_type,
                reason=reason,
                status='open'
            )

            return Response({
                'success': True,
                'flagged': True,
                'status': 'flagged',
                'message': 'This device has already been used or registered by another student. Your attendance has been flagged — contact your Lecturer to confirm it in Device Alerts before your sequential attendance code is issued.',
                'data': {
                    'name': f"{student.first_name} {student.last_name}".strip(),
                    'index': student.index_number,
                    'time': record.checked_in_at.strftime('%I:%M:%S %p'),
                    'avatar': f"{student.first_name[:1]}{student.last_name[:1]}".upper() or 'ST',
                    'method': "QR Code" if method == 'qr_code' else "Session Code",
                    'session_code': session.session_code,
                    'receipt_code': None,
                    'ref_id': None,
                    'status': 'flagged',
                    'flagged': True,
                    'host': host_display,
                    'host_role': host_role,
                    'courseCode': session.course.code if session.course else '',
                    'courseName': session.course.name if session.course else 'Attendance Session',
                    'group': session.group.name if session.group else ''
                }
            })

        # Clean verified device: bind if unregistered, issue atomic 4-digit sequential code
        if has_real_device and not student.device_id:
            student.device_id = device_id
            student.device_name = device_name
            student.save(update_fields=['device_id', 'device_name'])

        receipt_code = assign_next_receipt_code(session, student)
        record = AttendanceRecord.objects.create(
            session=session,
            student=student,
            method=method,
            status='confirmed',
            device_id=device_id,
            device_name=device_name,
            receipt_code=receipt_code
        )

        return Response({
            'success': True,
            'flagged': False,
            'status': 'confirmed',
            'message': 'Checked in successfully.',
            'data': {
                'name': f"{student.first_name} {student.last_name}".strip(),
                'index': student.index_number,
                'time': record.checked_in_at.strftime('%I:%M:%S %p'),
                'avatar': f"{student.first_name[:1]}{student.last_name[:1]}".upper() or 'ST',
                'method': "QR Code" if method == 'qr_code' else "Session Code",
                'session_code': session.session_code,
                'receipt_code': receipt_code,
                'ref_id': receipt_code,
                'status': 'confirmed',
                'flagged': False,
                'host': host_display,
                'host_role': host_role,
                'courseCode': session.course.code if session.course else '',
                'courseName': session.course.name if session.course else 'Attendance Session',
                'group': session.group.name if session.group else ''
            }
        })


class AlertListView(APIView):
    permission_classes = [permissions.IsAuthenticated]

    def get(self, request):
        if request.user.role != User.Role.LECTURER and not request.user.is_staff:
            return Response({'success': True, 'data': []})

        level_id = request.query_params.get('level_id')
        queryset = DeviceAlert.objects.select_related(
            'student', 'student__group', 'session', 'session__course', 'session__created_by', 'attendance_record'
        ).order_by('-detected_at')

        if request.user.role == User.Role.LECTURER:
            lec_groups = StudentGroup.objects.filter(lecturer=request.user)
            if level_id:
                if str(level_id).isdigit():
                    lec_groups = lec_groups.filter(
                        models.Q(level_id=int(level_id)) | models.Q(level__code__iexact=str(level_id))
                    )
                else:
                    lec_groups = lec_groups.filter(level__code__iexact=str(level_id))
            queryset = queryset.filter(
                models.Q(student__group__in=lec_groups) |
                models.Q(student__enrolled_groups__in=lec_groups) |
                models.Q(session__group__in=lec_groups) |
                models.Q(session__created_by=request.user)
            ).distinct()
        elif level_id:
            if str(level_id).isdigit():
                queryset = queryset.filter(
                    models.Q(student__group__level_id=int(level_id)) |
                    models.Q(student__enrolled_groups__level_id=int(level_id))
                ).distinct()
            else:
                queryset = queryset.filter(
                    models.Q(student__group__level__code__iexact=str(level_id)) |
                    models.Q(student__enrolled_groups__level__code__iexact=str(level_id))
                ).distinct()

        serializer = DeviceAlertSerializer(queryset, many=True)
        return Response({
            'success': True,
            'data': serializer.data
        })


class AlertActionView(APIView):
    permission_classes = [permissions.IsAuthenticated]

    def post(self, request, alert_id):
        if request.user.role != User.Role.LECTURER and not request.user.is_staff:
            return Response({
                'success': False,
                'message': 'Only the Lecturer can confirm or dismiss device alerts.'
            }, status=status.HTTP_403_FORBIDDEN)

        action = request.data.get('action')

        alert = DeviceAlert.objects.select_related('student', 'session', 'attendance_record').filter(id=alert_id).first()
        if not alert:
            alert = DeviceAlert.objects.select_related('student', 'session', 'attendance_record').filter(
                student_id=alert_id, status='open'
            ).order_by('-id').first()

        if not alert:
            return Response({
                'success': False,
                'message': 'Alert not found.'
            }, status=status.HTTP_404_NOT_FOUND)

        if action in ['confirm', 'confirmed']:
            alert.status = 'confirmed'
            alert.save(update_fields=['status'])

            # Also confirm any other open alerts for this student/session
            if alert.session_id:
                DeviceAlert.objects.filter(
                    student=alert.student, session_id=alert.session_id, status='open'
                ).update(status='confirmed')

            rec = alert.attendance_record or AttendanceRecord.objects.filter(
                student=alert.student, status='flagged'
            ).order_by('-checked_in_at').first()

            issued_code = None
            if rec:
                if not rec.receipt_code:
                    rec.receipt_code = assign_next_receipt_code(rec.session, rec.student)
                rec.status = 'confirmed'
                rec.save(update_fields=['status', 'receipt_code'])
                issued_code = rec.receipt_code

                if alert.alert_type == 'device_change' and rec.device_id and rec.device_id != 'dev-default':
                    alert.student.device_id = rec.device_id
                    alert.student.device_name = rec.device_name
                    alert.student.save(update_fields=['device_id', 'device_name'])

            return Response({
                'success': True,
                'message': f"Alert confirmed{f' — Issued code {issued_code}' if issued_code else ''}.",
                'data': {'receipt_code': issued_code}
            })
        elif action in ['dismiss', 'dismissed']:
            alert.status = 'dismissed'
            alert.save(update_fields=['status'])
            return Response({
                'success': True,
                'message': 'Alert marked as dismissed.'
            })
        else:
            return Response({
                'success': False,
                'message': 'Invalid action. Must be confirm or dismiss.'
            }, status=status.HTTP_400_BAD_REQUEST)

    def delete(self, request, alert_id):
        if request.user.role != User.Role.LECTURER and not request.user.is_staff:
            return Response({
                'success': False,
                'message': 'Only the Lecturer can delete flagged attendance records.'
            }, status=status.HTTP_403_FORBIDDEN)

        alert = DeviceAlert.objects.select_related('attendance_record').filter(id=alert_id).first()
        if not alert:
            alert = DeviceAlert.objects.select_related('attendance_record').filter(
                student_id=alert_id, status='open'
            ).order_by('-id').first()

        if not alert:
            return Response({
                'success': False,
                'message': 'Alert not found.'
            }, status=status.HTTP_404_NOT_FOUND)

        if alert.attendance_record:
            alert.attendance_record.delete()
        elif alert.session_id:
            AttendanceRecord.objects.filter(
                session_id=alert.session_id, student=alert.student, status='flagged'
            ).delete()

        alert.delete()
        return Response({
            'success': True,
            'message': 'Flagged attendance record and alert deleted.'
        })
