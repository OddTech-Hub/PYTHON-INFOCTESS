import csv
from datetime import timedelta
from django.db import models
from django.http import HttpResponse
from django.utils import timezone
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import status, permissions
from core.models import Level
from courses.models import Course, StudentGroup, CourseRep
from courses.helpers import get_user_rep_group_ids, get_user_rep_course_ids, get_rep_scope_q
from accounts.models import User
from attendance.models import AttendanceSession, AttendanceRecord, DeviceAlert
from attendance.utils import get_session_host_info, close_expired_sessions


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
        close_expired_sessions()
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
        elif request.user.role == User.Role.REP:
            rep_course_ids = get_user_rep_course_ids(request.user)
            courses_qs = courses_qs.filter(id__in=rep_course_ids) if rep_course_ids else Course.objects.none()
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

        # Pre-fetch students, group memberships, session counts, and attendance counts in bulk
        student_list = list(
            students.only('id', 'group_id', 'first_name', 'last_name', 'index_number', 'email')
        )
        student_ids = [s.id for s in student_list]
        ordered_group_ids = [g.id for g in ordered_groups]
        level_group_ids = [g.id for g in level_groups]
        relevant_group_ids = ordered_group_ids if request.user.role == User.Role.LECTURER else (level_group_ids or ordered_group_ids)
        relevant_group_ids_set = set(relevant_group_ids)

        through_model = StudentGroup.members.through
        student_groups_map = {sid: set() for sid in student_ids}
        group_students_map = {gid: set() for gid in ordered_group_ids}

        if student_ids and relevant_group_ids:
            for sg_id, u_id in through_model.objects.filter(
                studentgroup_id__in=relevant_group_ids,
                user_id__in=student_ids
            ).values_list('studentgroup_id', 'user_id'):
                if u_id in student_groups_map:
                    student_groups_map[u_id].add(sg_id)
                if sg_id in group_students_map:
                    group_students_map[sg_id].add(u_id)

        for s in student_list:
            if s.group_id and s.group_id in relevant_group_ids_set:
                student_groups_map[s.id].add(s.group_id)
            if s.group_id and s.group_id in group_students_map:
                group_students_map[s.group_id].add(s.id)

        session_counts_by_group = {}
        if relevant_group_ids:
            session_counts_by_group = dict(
                AttendanceSession.objects.filter(group_id__in=relevant_group_ids)
                .values('group_id')
                .annotate(cnt=models.Count('id'))
                .values_list('group_id', 'cnt')
            )

        attended_by_student_group = {}
        if student_ids and relevant_group_ids:
            for row in (
                AttendanceRecord.objects.filter(
                    student_id__in=student_ids,
                    session__group_id__in=relevant_group_ids,
                    status='confirmed'
                )
                .values('student_id', 'session__group_id')
                .annotate(cnt=models.Count('id'))
            ):
                attended_by_student_group[(row['student_id'], row['session__group_id'])] = row['cnt']

        # Calculate real student attendance rates across students who actually had sessions
        student_rates = []
        active_student_count = 0
        low_attendance_count = 0
        perfect_attendance_count = 0

        for student in student_list:
            s_group_ids = student_groups_map.get(student.id) or set()
            if request.user.role == User.Role.LECTURER:
                s_group_ids = {gid for gid in s_group_ids if gid in group_students_map}
            total_sessions = sum(session_counts_by_group.get(gid, 0) for gid in s_group_ids) if s_group_ids else 0
            if total_sessions > 0:
                attended = sum(attended_by_student_group.get((student.id, gid), 0) for gid in s_group_ids)
                rate = min(100, int((attended / total_sessions) * 100))
                student_rates.append(rate)
                active_student_count += 1
                if rate < 75:
                    low_attendance_count += 1
                if rate == 100:
                    perfect_attendance_count += 1

        overall_avg = int(sum(student_rates) / len(student_rates)) if student_rates else 0

        # Real 7-day weekly attendance calculation
        week_cutoff = timezone.now() - timedelta(days=7)
        weekly_sessions = list(
            AttendanceSession.objects.filter(
                group_id__in=relevant_group_ids,
                opened_at__gte=week_cutoff
            ).annotate(
                confirmed_count=models.Count('records', filter=models.Q(records__status='confirmed'))
            )
        ) if relevant_group_ids else []
        if weekly_sessions:
            week_rates = []
            for ws in weekly_sessions:
                g_size = len(group_students_map.get(ws.group_id, set()))
                if g_size > 0:
                    week_rates.append(min(100, int((ws.confirmed_count / g_size) * 100)))
            this_week_avg = int(sum(week_rates) / len(week_rates)) if week_rates else 0
        else:
            this_week_avg = 0

        # Unresolved device alerts in this level (scoped to this cohort)
        flagged_count = (
            DeviceAlert.objects.filter(student_id__in=student_ids, status='open').count()
            if student_ids else 0
        )

        # Progress bars (0% when no sessions held yet — never fake 100%)
        progress = [
            { 'label': "Overall Attendance", 'value': overall_avg, 'color': "#3b82f6" },
            { 'label': "This Week", 'value': this_week_avg, 'color': "#10b981" },
            { 'label': "Below 75%", 'value': int((low_attendance_count / active_student_count * 100)) if active_student_count > 0 else 0, 'color': "#ef4444", 'raw': f"{low_attendance_count} students" },
            { 'label': "Perfect Attendance", 'value': int((perfect_attendance_count / active_student_count * 100)) if active_student_count > 0 else 0, 'color': "#f59e0b" },
        ]

        # Group pie chart data (computed in-memory, 0% when 0 sessions held)
        colors = ["#3b82f6", "#10b981", "#f59e0b", "#8b5cf6", "#ef4444"]
        group_pie_data = []
        for i, g in enumerate(ordered_groups):
            g_student_ids = group_students_map.get(g.id, set())
            g_rates = []
            g_total_sessions = session_counts_by_group.get(g.id, 0)
            if g_total_sessions > 0:
                for sid in g_student_ids:
                    attended = attended_by_student_group.get((sid, g.id), 0)
                    g_rates.append(min(100, int((attended / g_total_sessions) * 100)))

            avg_rate = int(sum(g_rates) / len(g_rates)) if g_rates else 0
            group_pie_data.append({
                'label': _group_label(g),
                'value': len(g_student_ids),
                'avg': avg_rate,
                'sessions': g_total_sessions,
                'color': colors[i % len(colors)]
            })

        # Compute real per-course attendance averages and student per-course stats
        course_ids_list = [c['id'] for c in courses_data]
        course_stats_map = {}
        if course_ids_list and relevant_group_ids:
            c_sessions = list(
                AttendanceSession.objects.filter(
                    course_id__in=course_ids_list,
                    group_id__in=relevant_group_ids
                ).annotate(
                    confirmed_count=models.Count('records', filter=models.Q(records__status='confirmed'))
                )
            )
            my_confirmed_by_course = {}
            if is_student or request.user.role == User.Role.REP:
                my_confirmed_by_course = dict(
                    AttendanceRecord.objects.filter(
                        student=request.user,
                        status='confirmed',
                        session__course_id__in=course_ids_list,
                        session__group_id__in=relevant_group_ids
                    ).values('session__course_id').annotate(cnt=models.Count('id')).values_list('session__course_id', 'cnt')
                )

            c_sess_rates = {cid: [] for cid in course_ids_list}
            c_sess_counts = {cid: 0 for cid in course_ids_list}
            c_student_total = {cid: 0 for cid in course_ids_list}
            my_group_set = set(student_groups_qs.values_list('id', flat=True)) if is_student else set(ordered_group_ids)
            for cs in c_sessions:
                c_sess_counts[cs.course_id] = c_sess_counts.get(cs.course_id, 0) + 1
                g_size = len(group_students_map.get(cs.group_id, set()))
                if g_size > 0:
                    c_sess_rates[cs.course_id].append(min(100, int((cs.confirmed_count / g_size) * 100)))
                if cs.group_id in my_group_set:
                    c_student_total[cs.course_id] = c_student_total.get(cs.course_id, 0) + 1

            for cid in course_ids_list:
                r_list = c_sess_rates.get(cid, [])
                s_tot = c_student_total.get(cid, 0)
                s_att = my_confirmed_by_course.get(cid, 0)
                course_stats_map[cid] = {
                    'sessions_count': c_sess_counts.get(cid, 0),
                    'avg_attendance': int(sum(r_list) / len(r_list)) if r_list else 0,
                    'student_attended': s_att,
                    'student_total': s_tot,
                    'student_pct': min(100, int((s_att / s_tot) * 100)) if s_tot > 0 else 0,
                }

        for c_item in courses_data:
            c_st = course_stats_map.get(c_item['id'], {})
            c_item['sessions_count'] = c_st.get('sessions_count', 0)
            c_item['avg_attendance'] = c_st.get('avg_attendance', 0)
            c_item['attended'] = c_st.get('student_attended', 0)
            c_item['total'] = c_st.get('student_total', 0)
            c_item['pct'] = c_st.get('student_pct', 0)

        # Active & historical sessions for this level
        all_sessions = AttendanceSession.objects.filter(
            group__level=level
        ).select_related('course', 'group', 'group__lecturer', 'created_by').annotate(
            checkin_count=models.Count('records')
        ).order_by('-opened_at')

        if request.user.role == User.Role.LECTURER:
            lec_group_ids = [g.id for g in ordered_groups]
            all_sessions = all_sessions.filter(models.Q(group_id__in=lec_group_ids) | models.Q(created_by=request.user)).distinct()
        elif request.user.role == User.Role.REP:
            all_sessions = all_sessions.filter(get_rep_scope_q(request.user)).distinct()
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
            host_name, host_role = get_session_host_info(s)
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
                'host_name': host_name,
                'host_role': host_role,
                'time_window': s.time_window_minutes,
                'checkin_count': getattr(s, 'checkin_count', 0),
                'checked_in': rec is not None,
                'checked_in_at': rec.checked_in_at.isoformat() if (rec and rec.checked_in_at) else None,
                'record_status': rec.status if rec else ('Pending' if s.status == 'active' else 'Absent'),
                'receipt_code': rec.receipt_code if (rec and rec.status == 'confirmed') else None,
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
        close_expired_sessions()
        level_code = request.query_params.get('level_code')
        course_code = request.query_params.get('course_code')
        group_name = request.query_params.get('group_name')

        if not level_code:
            if request.user.role == User.Role.REP:
                rep_ass = CourseRep.objects.filter(student=request.user).select_related('group__level', 'course__level').first()
                if rep_ass and rep_ass.group and rep_ass.group.level:
                    level = rep_ass.group.level
                elif rep_ass and rep_ass.course and rep_ass.course.level:
                    level = rep_ass.course.level
                elif request.user.group and request.user.group.level:
                    level = request.user.group.level
                else:
                    level = Level.objects.first()
            elif request.user.group and request.user.group.level:
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
            course = Course.objects.filter(code__iexact=course_code, level=level).first() or Course.objects.filter(code__iexact=course_code).first()
            if course and not group_name:
                course_groups = scoped_groups.filter(course=course)
                scoped_groups = course_groups
                students = students.filter(
                    models.Q(group__in=course_groups) | models.Q(enrolled_groups__in=course_groups)
                ).distinct()

        # Serialize students with their attendance for this specific course or level (bulk pre-fetched)
        data = []
        scoped_groups_list = sorted(
            list(scoped_groups.select_related('course', 'level')),
            key=_natural_group_sort_key
        )
        scoped_group_by_id = {g.id: g for g in scoped_groups_list}
        scoped_group_ids = list(scoped_group_by_id.keys())
        selected_group_ids = (
            list(selected_group_objs.values_list('id', flat=True))
            if selected_group_objs is not None else None
        )

        student_list = list(students.select_related('group', 'group__course', 'group__level'))
        student_ids = [s.id for s in student_list]

        through_model = StudentGroup.members.through
        student_group_ids_map = {sid: [] for sid in student_ids}
        if student_ids and scoped_group_ids:
            m2m_sets = {sid: set() for sid in student_ids}
            for sg_id, u_id in through_model.objects.filter(
                studentgroup_id__in=scoped_group_ids,
                user_id__in=student_ids
            ).values_list('studentgroup_id', 'user_id'):
                if u_id in m2m_sets:
                    m2m_sets[u_id].add(sg_id)
            for s in student_list:
                if s.group_id and s.group_id in scoped_group_by_id:
                    m2m_sets[s.id].add(s.group_id)
                student_group_ids_map[s.id] = [
                    g.id for g in scoped_groups_list if g.id in m2m_sets[s.id]
                ]

        all_candidate_group_ids = set(scoped_group_ids)
        if selected_group_ids:
            all_candidate_group_ids.update(selected_group_ids)
        for s in student_list:
            if s.group_id:
                all_candidate_group_ids.add(s.group_id)

        session_counts_by_group = {}
        if all_candidate_group_ids:
            sess_qs = AttendanceSession.objects.filter(group_id__in=all_candidate_group_ids)
            if request.user.role == User.Role.REP:
                sess_qs = sess_qs.filter(get_rep_scope_q(request.user, course_field='course_id', group_field='group_id'))
            if course:
                sess_qs = sess_qs.filter(course=course)
            session_counts_by_group = dict(
                sess_qs.values('group_id').annotate(cnt=models.Count('id')).values_list('group_id', 'cnt')
            )

        attended_by_student_group = {}
        if student_ids and all_candidate_group_ids:
            rec_qs = AttendanceRecord.objects.filter(
                student_id__in=student_ids,
                session__group_id__in=all_candidate_group_ids,
                status='confirmed'
            )
            if request.user.role == User.Role.REP:
                rec_qs = rec_qs.filter(get_rep_scope_q(request.user, course_field='session__course_id', group_field='session__group_id'))
            if course:
                rec_qs = rec_qs.filter(session__course=course)
            for row in rec_qs.values('student_id', 'session__group_id').annotate(cnt=models.Count('id')):
                attended_by_student_group[(row['student_id'], row['session__group_id'])] = row['cnt']

        alerts_by_student = {}
        if student_ids:
            for al in DeviceAlert.objects.filter(student_id__in=student_ids, status='open').order_by('-id'):
                if al.student_id not in alerts_by_student:
                    alerts_by_student[al.student_id] = al

        for s in student_list:
            s_group_ids = student_group_ids_map.get(s.id, [])
            s_groups = [scoped_group_by_id[gid] for gid in s_group_ids if gid in scoped_group_by_id]
            if selected_group_ids is not None:
                sess_group_ids = [gid for gid in selected_group_ids if gid in s_group_ids] or selected_group_ids
            else:
                sess_group_ids = s_group_ids if s_group_ids else ([s.group_id] if s.group_id else [])

            # Per-group and per-course stats so new courses/groups NEVER inherit other courses' session totals
            group_stats_map = {}
            course_stats_acc = {}
            for sg in s_groups:
                g_tot = session_counts_by_group.get(sg.id, 0)
                g_att = attended_by_student_group.get((s.id, sg.id), 0)
                g_pct = min(100, int((g_att / g_tot) * 100)) if g_tot > 0 else 0
                g_lbl = _group_label(sg)
                c_code_str = sg.course.code if sg.course else ''
                group_stats_map[g_lbl] = {
                    'attended': g_att,
                    'total': g_tot,
                    'pct': g_pct,
                    'has_sessions': g_tot > 0,
                    'course_code': c_code_str
                }
                if c_code_str:
                    acc = course_stats_acc.setdefault(c_code_str, {'attended': 0, 'total': 0})
                    acc['attended'] += g_att
                    acc['total'] += g_tot

            course_stats_map = {
                cc: {
                    'attended': v['attended'],
                    'total': v['total'],
                    'pct': min(100, int((v['attended'] / v['total']) * 100)) if v['total'] > 0 else 0,
                    'has_sessions': v['total'] > 0
                }
                for cc, v in course_stats_acc.items()
            }

            total_sessions = sum(session_counts_by_group.get(gid, 0) for gid in sess_group_ids)
            attended = sum(attended_by_student_group.get((s.id, gid), 0) for gid in sess_group_ids)
            rate = min(100, int((attended / total_sessions) * 100)) if total_sessions > 0 else 0

            alert = alerts_by_student.get(s.id)
            group_labels = [_group_label(g) for g in s_groups]

            data.append({
                'id': s.id,
                'name': f"{s.first_name} {s.last_name}".strip(),
                'index': s.index_number,
                'email': s.email,
                'attended': attended,
                'total': total_sessions,
                'pct': rate,
                'has_sessions': total_sessions > 0,
                'group_stats': group_stats_map,
                'course_stats': course_stats_map,
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
        close_expired_sessions()
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

                records_query = AttendanceRecord.objects.filter(student=s, status='confirmed')
                if course:
                    records_query = records_query.filter(session__course=course)

                attended = records_query.count()
                rate = min(100, int((attended / total) * 100)) if total > 0 else 0

                writer.writerow([
                    f"{s.first_name} {s.last_name}",
                    s.index_number,
                    s.group.name if s.group else "",
                    attended,
                    total,
                    f"{rate}%" if total > 0 else "No Sessions"
                ])
        except Exception as e:
            writer.writerow([f"Error generating report: {str(e)}"])

        return response
