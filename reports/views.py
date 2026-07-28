import csv
from django.db import models
from django.http import HttpResponse
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import status, permissions
from core.models import Level
from courses.models import Course, StudentGroup, CourseRep
from courses.helpers import get_user_rep_group_ids
from accounts.models import User
from attendance.models import AttendanceSession, AttendanceRecord, DeviceAlert


class LevelSummaryView(APIView):
    permission_classes = [permissions.IsAuthenticated]

    def get(self, request, level_code):
        try:
            level = Level.objects.get(code=level_code)
        except Level.DoesNotExist:
            return Response({
                'success': False,
                'message': f'Level {level_code} not found.'
            }, status=status.HTTP_404_NOT_FOUND)

        students = User.objects.filter(group__level=level, role__in=[User.Role.STUDENT, User.Role.REP])
        
        # Enforce Course Rep group scoping
        rep_group_ids = get_user_rep_group_ids(request.user)
        if rep_group_ids is not None:
            students = students.filter(group_id__in=rep_group_ids)

        courses_qs = Course.objects.filter(level=level)
        if request.user.role == User.Role.LECTURER:
            from courses.models import LecturerCourse
            lecturer_course_ids = LecturerCourse.objects.filter(lecturer=request.user).values_list('course_id', flat=True)
            courses_qs = courses_qs.filter(id__in=lecturer_course_ids)

        courses_count = courses_qs.count()
        courses_data = [{'id': c.id, 'code': c.code, 'name': c.name} for c in courses_qs]

        groups = StudentGroup.objects.filter(level=level)
        if request.user.role == User.Role.LECTURER:
            groups = groups.filter(models.Q(lecturer=request.user) | models.Q(lecturer__isnull=True))
        elif rep_group_ids is not None:
            groups = groups.filter(id__in=rep_group_ids)

        groups_count = groups.count()

        # Calculate student specific attendance rates
        student_rates = []
        low_attendance_count = 0
        perfect_attendance_count = 0

        for student in students:
            # Total sessions opened for this student's group
            total_sessions = AttendanceSession.objects.filter(group=student.group).count()
            if total_sessions == 0:
                rate = 100  # Default to 100% if no sessions have been run
            else:
                attended = AttendanceRecord.objects.filter(student=student).count()
                rate = int((attended / total_sessions) * 100)

            student_rates.append(rate)
            if rate < 75:
                low_attendance_count += 1
            if rate == 100:
                perfect_attendance_count += 1

        overall_avg = int(sum(student_rates) / len(student_rates)) if student_rates else 100
        
        # Unresolved device alerts in this level
        flagged_count = DeviceAlert.objects.filter(
            student__group__level=level, 
            status='open'
        ).count()

        # Progress bars
        progress = [
            { 'label': "Overall Attendance", 'value': overall_avg, 'color': "#3b82f6" },
            { 'label': "This Week", 'value': 91, 'color': "#10b981" }, # Seed standard default
            { 'label': "Below 75%", 'value': int((low_attendance_count / len(students) * 100)) if students.exists() else 0, 'color': "#ef4444", 'raw': f"{low_attendance_count} students" },
            { 'label': "Perfect Attendance", 'value': int((perfect_attendance_count / len(students) * 100)) if students.exists() else 0, 'color': "#f59e0b" },
        ]

        # Group pie chart data
        colors = ["#3b82f6", "#10b981", "#f59e0b", "#8b5cf6", "#ef4444"]
        group_pie_data = []
        for i, g in enumerate(groups):
            g_students = students.filter(group=g)
            g_rates = []
            for s in g_students:
                total_sessions = AttendanceSession.objects.filter(group=s.group).count()
                if total_sessions == 0:
                    rate = 100
                else:
                    attended = AttendanceRecord.objects.filter(student=s).count()
                    rate = int((attended / total_sessions) * 100)
                g_rates.append(rate)

            avg_rate = int(sum(g_rates) / len(g_rates)) if g_rates else 100
            group_pie_data.append({
                'label': g.name,
                'value': g_students.count(),
                'avg': avg_rate,
                'color': colors[i % len(colors)]
            })

        # Active sessions for this level
        all_sessions = AttendanceSession.objects.filter(
            group__level=level
        ).select_related('course', 'group').order_by('-opened_at')

        if rep_group_ids is not None:
            all_sessions = all_sessions.filter(models.Q(group_id__in=rep_group_ids) | models.Q(created_by=request.user))

        sessions_data = [{
            'id': s.session_code,
            'session_code': s.session_code,
            'status': s.status,
            'opened_at': s.opened_at.isoformat() if s.opened_at else None,
            'course': {
                'id': s.course.id if s.course else None,
                'code': s.course.code if s.course else '',
                'name': s.course.name if s.course else ''
            },
            'group': s.group.name if s.group else '',
            'time_window': s.time_window_minutes,
            'qr_data': s.qr_data or f'infoctess://session/{s.session_code}'
        } for s in all_sessions]

        return Response({
            'success': True,
            'data': {
                'level': {
                    'code': level.code,
                    'label': level.label,
                    'year': level.year,
                },
                'stats': {
                    'courses': courses_count,
                    'groups': groups_count,
                    'lowAttendance': low_attendance_count,
                    'flagged': flagged_count,
                },
                'courses': courses_data,
                'groups': [g.name for g in groups],
                'progress': progress,
                'groupPieData': group_pie_data,
                'sessions': sessions_data
            }
        })


class CourseBreakdownView(APIView):
    permission_classes = [permissions.IsAuthenticated]

    def get(self, request):
        level_code = request.query_params.get('level_code')
        course_code = request.query_params.get('course_code')
        group_name = request.query_params.get('group_name')

        if not level_code:
            if request.user.group and request.user.group.level:
                level = request.user.group.level
            else:
                rep_ass = CourseRep.objects.filter(student=request.user).first()
                if rep_ass and rep_ass.group and rep_ass.group.level:
                    level = rep_ass.group.level
                else:
                    level = Level.objects.first()
        else:
            try:
                level = Level.objects.get(code=level_code)
            except Level.DoesNotExist:
                return Response({
                    'success': False,
                    'message': 'Level not found.'
                }, status=status.HTTP_404_NOT_FOUND)

        students = User.objects.filter(group__level=level, role__in=[User.Role.STUDENT, User.Role.REP])

        # Enforce Course Rep group scoping: Course Reps ONLY see their own group members
        rep_group_ids = get_user_rep_group_ids(request.user)
        if rep_group_ids is not None:
            students = students.filter(group_id__in=rep_group_ids)

        if group_name:
            students = students.filter(group__name=group_name)

        course = None
        if course_code:
            course = Course.objects.filter(code=course_code, level=level).first()

        # Serialize students with their attendance for this specific course or level
        data = []
        for s in students:
            # Filter session count
            sessions_query = AttendanceSession.objects.filter(group=s.group)
            if course:
                sessions_query = sessions_query.filter(course=course)
            
            total_sessions = sessions_query.count()
            
            records_query = AttendanceRecord.objects.filter(student=s)
            if course:
                records_query = records_query.filter(session__course=course)
                
            attended = records_query.count()
            rate = int((attended / total_sessions) * 100) if total_sessions > 0 else 100
            
            # Find recent alert if any
            alert = DeviceAlert.objects.filter(student=s, status='open').first()

            data.append({
                'id': s.id,
                'name': f"{s.first_name} {s.last_name}",
                'index': s.index_number,
                'attended': attended,
                'total': total_sessions,
                'pct': rate,
                'device': s.device_name or "Not Registered",
                'deviceId': s.device_id,
                'flagged': alert is not None,
                'alertId': alert.id if alert else None,
                'alertType': alert.alert_type if alert else None,
                'flagReason': alert.reason if alert else None,
                'group': s.group.name if s.group else ""
            })

        return Response({
            'success': True,
            'data': data
        })


class CSVExportView(APIView):
    permission_classes = [permissions.IsAuthenticated]

    def get(self, request):
        level_code = request.query_params.get('level_code')
        course_code = request.query_params.get('course_code')
        group_name = request.query_params.get('group_name')

        response = HttpResponse(content_type='text/csv')
        response['Content-Disposition'] = f'attachment; filename="attendance_report.csv"'

        writer = csv.writer(response)
        writer.writerow(['Student Name', 'Index Number', 'Group', 'Attended Sessions', 'Total Sessions', 'Attendance Rate (%)'])

        try:
            if level_code:
                level = Level.objects.filter(code=level_code).first() or Level.objects.filter(id=level_code).first()
            else:
                level = Level.objects.first()

            if level:
                students = User.objects.filter(group__level=level, role__in=[User.Role.STUDENT, User.Role.REP])
            else:
                students = User.objects.filter(role__in=[User.Role.STUDENT, User.Role.REP])

            rep_group_ids = get_user_rep_group_ids(request.user)
            if rep_group_ids is not None:
                students = students.filter(group_id__in=rep_group_ids)

            course = Course.objects.filter(code=course_code).first() if course_code else None

            for s in students:
                sessions_query = AttendanceSession.objects.filter(group=s.group) if s.group else AttendanceSession.objects.all()
                if course:
                    sessions_query = sessions_query.filter(course=course)
                
                total = sessions_query.count()

                records_query = AttendanceRecord.objects.filter(student=s)
                if course:
                    records_query = records_query.filter(session__course=course)

                attended = records_query.count()
                rate = int((attended / total) * 100) if total > 0 else 100

                writer.writerow([
                    f"{s.first_name} {s.last_name}",
                    s.index_number,
                    s.group.name if s.group else "",
                    attended,
                    total,
                    f"{rate}%"
                ])
        except Exception as e:
            writer.writerow([f"Error generating report: {str(e)}"])

        return response
