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


def _group_label(g):
    if not g:
        return ''
    if getattr(g, 'course', None):
        return f"{g.course.code} - {g.name}"
    if getattr(g, 'level', None):
        return f"{g.level.code} - {g.name}"
    return g.name or ''


def _natural_group_sort_key(g):
    import re
    m = re.search(r'(\d+)\s*$', getattr(g, 'name', '') or '')
    num = int(m.group(1)) if m else 999999
    c_code = g.course.code if getattr(g, 'course', None) else ''
    return (c_code, num, getattr(g, 'name', '') or '')


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

        rep_group_ids = get_user_rep_group_ids(request.user)
        is_student = request.user.is_authenticated and getattr(request.user, 'role', None) == User.Role.STUDENT

        level_groups = StudentGroup.objects.filter(level=level).select_related('course', 'level', 'lecturer')
        students = User.objects.filter(
            role__in=[User.Role.STUDENT, User.Role.REP]
        ).filter(
            models.Q(group__level=level) | models.Q(enrolled_groups__level=level)
        ).distinct()

        if request.user.role == User.Role.LECTURER:
            lec_groups = level_groups.filter(lecturer=request.user)
            if lec_groups.exists():
                students = students.filter(
                    models.Q(group__in=lec_groups) | models.Q(enrolled_groups__in=lec_groups)
                ).distinct()
            else:
                students = User.objects.none()
        elif rep_group_ids is not None:
            students = students.filter(
                models.Q(group_id__in=rep_group_ids) | models.Q(enrolled_groups__id__in=rep_group_ids)
            ).distinct()

        all_level_courses = Course.objects.filter(level=level)
        courses_qs = all_level_courses
        student_groups_qs = StudentGroup.objects.none()
        if request.user.role == User.Role.LECTURER:
            from courses.models import LecturerCourse
            # Strictly scope courses to those explicitly assigned to this lecturer in this level
            lecturer_course_ids = LecturerCourse.objects.filter(lecturer=request.user).values_list('course_id', flat=True)
            courses_qs = courses_qs.filter(id__in=lecturer_course_ids)
        elif is_student:
            student_groups_qs = level_groups.filter(
                models.Q(id=request.user.group_id) | models.Q(members=request.user)
            ).distinct()
            enrolled_course_ids = list(
                student_groups_qs.exclude(course__isnull=True).values_list('course_id', flat=True)
            )
            if enrolled_course_ids:
                courses_qs = all_level_courses.filter(id__in=enrolled_course_ids)

        courses_count = courses_qs.count()
        # Attach assigned lecturer names for courses
        lecturer_by_course = {}
        for g_item in level_groups:
            if g_item.course_id and g_item.lecturer and g_item.course_id not in lecturer_by_course:
                lecturer_by_course[g_item.course_id] = f"{g_item.lecturer.first_name} {g_item.lecturer.last_name}".strip() or g_item.lecturer.username
        from courses.models import LecturerCourse
        for lc in LecturerCourse.objects.filter(course__in=courses_qs).select_related('lecturer'):
            if lc.course_id not in lecturer_by_course and lc.lecturer:
                lecturer_by_course[lc.course_id] = f"{lc.lecturer.first_name} {lc.lecturer.last_name}".strip() or lc.lecturer.username

        courses_data = [
            {
                'id': c.id,
                'code': c.code,
                'name': c.name,
                'lecturer_name': lecturer_by_course.get(c.id, '')
            }
            for c in courses_qs
        ]
        all_courses_data = [{'id': c.id, 'code': c.code, 'name': c.name} for c in all_level_courses]

        groups = level_groups
        if request.user.role == User.Role.LECTURER:
            groups = groups.filter(lecturer=request.user)
            # Auto-create Group 1 ONLY if lecturer actually teaches at least 1 course in this level
            if not groups.exists() and courses_qs.exists():
                from core.models import AcademicPeriod
                period = AcademicPeriod.objects.filter(is_active=True).first() or AcademicPeriod.objects.first()
                if period:
                    grp, _ = StudentGroup.objects.get_or_create(
                        name="Group 1",
                        course=courses_qs.first(),
                        level=level,
                        academic_period=period,
                        lecturer=request.user
                    )
                    groups = StudentGroup.objects.filter(id=grp.id).select_related('course', 'level', 'lecturer')
        elif rep_group_ids is not None:
            groups = groups.filter(id__in=rep_group_ids)
        elif is_student and student_groups_qs.exists():
            groups = student_groups_qs

        ordered_groups = sorted(list(groups), key=_natural_group_sort_key)
        groups_count = len(ordered_groups)

        # Calculate student specific attendance rates
        student_rates = []
        low_attendance_count = 0
        perfect_attendance_count = 0

        for student in students:
            s_group_ids = list(student.enrolled_groups.filter(level=level).values_list('id', flat=True))
            if student.group_id and student.group_id not in s_group_ids:
                s_group_ids.append(student.group_id)
            if request.user.role == User.Role.LECTURER:
                lec_group_ids = [g.id for g in ordered_groups]
                s_group_ids = [gid for gid in s_group_ids if gid in lec_group_ids] or lec_group_ids
            total_sessions = AttendanceSession.objects.filter(group_id__in=s_group_ids).count() if s_group_ids else 0
            if total_sessions == 0:
                rate = 100
            else:
                attended = AttendanceRecord.objects.filter(student=student, session__group_id__in=s_group_ids).count()
                rate = int((attended / total_sessions) * 100)

            student_rates.append(rate)
            if rate < 75:
                low_attendance_count += 1
            if rate == 100:
                perfect_attendance_count += 1

        overall_avg = int(sum(student_rates) / len(student_rates)) if student_rates else 100

        # Unresolved device alerts in this level (scoped to this cohort)
        flagged_alerts = DeviceAlert.objects.filter(
            student__in=students,
            status='open'
        )
        flagged_count = flagged_alerts.count() if students.exists() else 0

        # Progress bars
        student_total = students.count()
        progress = [
            { 'label': "Overall Attendance", 'value': overall_avg, 'color': "#3b82f6" },
            { 'label': "This Week", 'value': overall_avg if student_total > 0 else 100, 'color': "#10b981" },
            { 'label': "Below 75%", 'value': int((low_attendance_count / student_total * 100)) if student_total > 0 else 0, 'color': "#ef4444", 'raw': f"{low_attendance_count} students" },
            { 'label': "Perfect Attendance", 'value': int((perfect_attendance_count / student_total * 100)) if student_total > 0 else 0, 'color': "#f59e0b" },
        ]

        # Group pie chart data
        colors = ["#3b82f6", "#10b981", "#f59e0b", "#8b5cf6", "#ef4444"]
        group_pie_data = []
        for i, g in enumerate(ordered_groups):
            g_students = students.filter(models.Q(group=g) | models.Q(enrolled_groups=g)).distinct()
            g_rates = []
            g_total_sessions = AttendanceSession.objects.filter(group=g).count()
            for s in g_students:
                if g_total_sessions == 0:
                    rate = 100
                else:
                    attended = AttendanceRecord.objects.filter(student=s, session__group=g).count()
                    rate = int((attended / g_total_sessions) * 100)
                g_rates.append(rate)

            avg_rate = int(sum(g_rates) / len(g_rates)) if g_rates else 100
            group_pie_data.append({
                'label': _group_label(g),
                'value': g_students.count(),
                'avg': avg_rate,
                'color': colors[i % len(colors)]
            })

        # Active & historical sessions for this level
        all_sessions = AttendanceSession.objects.filter(
            group__level=level
        ).select_related('course', 'group', 'group__lecturer').order_by('-opened_at')

        if request.user.role == User.Role.LECTURER:
            lec_group_ids = [g.id for g in ordered_groups]
            all_sessions = all_sessions.filter(models.Q(group_id__in=lec_group_ids) | models.Q(created_by=request.user)).distinct()
        elif rep_group_ids is not None:
            all_sessions = all_sessions.filter(models.Q(group_id__in=rep_group_ids) | models.Q(created_by=request.user)).distinct()
        elif is_student and student_groups_qs.exists():
            all_sessions = all_sessions.filter(group__in=student_groups_qs).distinct()

        student_records_map = {}
        if is_student or request.user.role == User.Role.REP:
            for rec in AttendanceRecord.objects.filter(student=request.user, session__in=all_sessions):
                student_records_map[rec.session_id] = rec

        sessions_data = []
        for s in all_sessions:
            rec = student_records_map.get(s.id)
            lec_user = s.group.lecturer if (s.group and s.group.lecturer) else None
            lec_name = f"{lec_user.first_name} {lec_user.last_name}".strip() if lec_user else ''
            item = {
                'id': s.session_code if (s.status != 'active' or not is_student) else f"session-{s.id}",
                'status': s.status,
                'opened_at': s.opened_at.isoformat() if s.opened_at else None,
                'course': {
                    'id': s.course.id if s.course else None,
                    'code': s.course.code if s.course else '',
                    'name': s.course.name if s.course else ''
                },
                'group': s.group.name if s.group else '',
                'group_display': _group_label(s.group),
                'lecturer_name': lec_name,
                'time_window': s.time_window_minutes,
                'checked_in': rec is not None,
                'checked_in_at': rec.checked_in_at.isoformat() if (rec and rec.checked_in_at) else None,
                'record_status': rec.status if rec else ('Pending' if s.status == 'active' else 'Absent'),
                'receipt_code': rec.receipt_code if rec else None,
                'method': rec.method if rec else None,
            }
            # Conceal active session code and QR payload from students to prevent remote check-ins
            if s.status != 'active' or not is_student:
                item['session_code'] = s.session_code
                item['qr_data'] = s.qr_data or f'infoctess://session/{s.session_code}'
            sessions_data.append(item)

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
                'allCourses': all_courses_data,
                'groups': [_group_label(g) for g in ordered_groups],
                'groups_detail': [
                    {
                        'id': g.id,
                        'name': g.name,
                        'display_name': _group_label(g),
                        'course_code': g.course.code if g.course else '',
                        'course_name': g.course.name if g.course else '',
                        'lecturer_name': f"{g.lecturer.first_name} {g.lecturer.last_name}".strip() if g.lecturer else ''
                    }
                    for g in ordered_groups
                ],
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

        rep_group_ids = get_user_rep_group_ids(request.user)
        students = User.objects.filter(
            role__in=[User.Role.STUDENT, User.Role.REP]
        ).filter(
            models.Q(group__level=level) | models.Q(enrolled_groups__level=level)
        ).distinct()

        scoped_groups = StudentGroup.objects.filter(level=level)
        if request.user.role == User.Role.LECTURER:
            lec_groups = scoped_groups.filter(lecturer=request.user)
            if lec_groups.exists():
                scoped_groups = lec_groups
                students = students.filter(
                    models.Q(group__in=lec_groups) | models.Q(enrolled_groups__in=lec_groups)
                ).distinct()
            else:
                scoped_groups = StudentGroup.objects.none()
                students = User.objects.none()
        elif rep_group_ids is not None:
            scoped_groups = scoped_groups.filter(id__in=rep_group_ids)
            students = students.filter(
                models.Q(group_id__in=rep_group_ids) | models.Q(enrolled_groups__id__in=rep_group_ids)
            ).distinct()

        selected_group_objs = None
        if group_name:
            if " - " in group_name:
                c_code, g_name = [p.strip() for p in group_name.split('-', 1)]
                matched = scoped_groups.filter(
                    models.Q(course__code__iexact=c_code, name__iexact=g_name) |
                    models.Q(level__code__iexact=c_code, name__iexact=g_name)
                )
            else:
                matched = scoped_groups.filter(name__iexact=group_name)
            selected_group_objs = matched
            students = students.filter(
                models.Q(group__in=matched) | models.Q(enrolled_groups__in=matched)
            ).distinct()

        course = None
        if course_code:
            course = Course.objects.filter(code=course_code, level=level).first()

        # Serialize students with their attendance for this specific course or level
        data = []
        scoped_group_ids = list(scoped_groups.values_list('id', flat=True))
        for s in students:
            s_groups = list(
                StudentGroup.objects.filter(id__in=scoped_group_ids)
                .filter(models.Q(id=s.group_id) | models.Q(members=s))
                .select_related('course', 'level')
                .distinct()
            )
            if selected_group_objs is not None:
                sess_group_ids = list(selected_group_objs.values_list('id', flat=True))
            else:
                sess_group_ids = [g.id for g in s_groups] if s_groups else ([s.group_id] if s.group_id else [])

            sessions_query = AttendanceSession.objects.filter(group_id__in=sess_group_ids)
            if course:
                sessions_query = sessions_query.filter(course=course)

            total_sessions = sessions_query.count()

            records_query = AttendanceRecord.objects.filter(student=s, session__group_id__in=sess_group_ids)
            if course:
                records_query = records_query.filter(session__course=course)

            attended = records_query.count()
            rate = int((attended / total_sessions) * 100) if total_sessions > 0 else 100

            # Find recent alert if any
            alert = DeviceAlert.objects.filter(student=s, status='open').first()
            group_labels = [_group_label(g) for g in s_groups]

            data.append({
                'id': s.id,
                'name': f"{s.first_name} {s.last_name}".strip(),
                'index': s.index_number,
                'email': s.email,
                'attended': attended,
                'total': total_sessions,
                'pct': rate,
                'device': s.device_name or "Not Registered",
                'deviceId': s.device_id,
                'flagged': alert is not None,
                'alertId': alert.id if alert else None,
                'alertType': alert.alert_type if alert else None,
                'flagReason': alert.reason if alert else None,
                'group': group_labels[0] if group_labels else (_group_label(s.group) if s.group else ""),
                'groups': group_labels
            })

        # Sort all students alphabetically by name (A to Z)
        data.sort(key=lambda s: str(s.get('name', '')).lower())
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
