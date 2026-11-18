from django.db import models
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import status, permissions
from core.models import Level
from core.serializers import LevelSerializer
from .models import Course, StudentGroup, CourseRep, LecturerCourse
from .serializers import CourseSerializer, StudentGroupSerializer
from .helpers import get_user_rep_group_ids, get_user_rep_course_ids, get_user_rep_assignments
from accounts.models import User
from accounts.serializers import UserSerializer


class LevelListView(APIView):
    permission_classes = [permissions.IsAuthenticated]

    def get(self, request):
        levels = Level.objects.all()
        serializer = LevelSerializer(levels, many=True)
        data = serializer.data

        if request.user.role == User.Role.LECTURER:
            from attendance.models import DeviceAlert
            course_counts = dict(
                LecturerCourse.objects.filter(lecturer=request.user)
                .values('course__level_id')
                .annotate(cnt=models.Count('id'))
                .values_list('course__level_id', 'cnt')
            )
            lec_group_rows = list(
                StudentGroup.objects.filter(lecturer=request.user).values_list('id', 'level_id')
            )
            groups_by_level = {}
            all_lec_group_ids = []
            for gid, lid in lec_group_rows:
                groups_by_level.setdefault(lid, []).append(gid)
                all_lec_group_ids.append(gid)

            students_by_level = {item.get('id'): set() for item in data}
            flagged_student_ids = set()
            if all_lec_group_ids:
                group_to_level = {gid: lid for gid, lid in lec_group_rows}
                through_model = StudentGroup.members.through
                for sg_id, u_id in through_model.objects.filter(
                    studentgroup_id__in=all_lec_group_ids
                ).values_list('studentgroup_id', 'user_id'):
                    lid = group_to_level.get(sg_id)
                    if lid in students_by_level:
                        students_by_level[lid].add(u_id)

                for u_id, g_id in User.objects.filter(
                    role__in=[User.Role.STUDENT, User.Role.REP],
                    group_id__in=all_lec_group_ids
                ).values_list('id', 'group_id'):
                    lid = group_to_level.get(g_id)
                    if lid in students_by_level:
                        students_by_level[lid].add(u_id)

                all_student_ids = set().union(*students_by_level.values()) if students_by_level else set()
                if all_student_ids:
                    flagged_student_ids = set(
                        DeviceAlert.objects.filter(student_id__in=all_student_ids, status='open')
                        .values_list('student_id', flat=True)
                    )

            enriched = []
            for item in data:
                lvl_id = item.get('id')
                lvl_students = students_by_level.get(lvl_id, set())
                row = dict(item)
                row['courses_count'] = course_counts.get(lvl_id, 0)
                row['groups_count'] = len(groups_by_level.get(lvl_id, []))
                row['studentsCount'] = len(lvl_students)
                row['flaggedCount'] = len(lvl_students & flagged_student_ids)
                enriched.append(row)
            data = enriched

        return Response({
            'success': True,
            'data': data
        })


class CourseListView(APIView):
    permission_classes = [permissions.IsAuthenticated]

    def get(self, request):
        level_id = request.query_params.get('level_id')
        rep_me = request.query_params.get('rep')

        queryset = Course.objects.all()

        if request.user.role == User.Role.LECTURER:
            # Strictly scope courses to those explicitly assigned to this lecturer
            lecturer_course_ids = LecturerCourse.objects.filter(lecturer=request.user).values_list('course_id', flat=True)
            queryset = queryset.filter(id__in=lecturer_course_ids)
        elif request.user.role == User.Role.REP:
            # Course Reps can ONLY see courses they have been specifically assigned to
            assigned_course_ids = get_user_rep_course_ids(request.user)
            queryset = queryset.filter(id__in=assigned_course_ids) if assigned_course_ids else Course.objects.none()

        if level_id:
            if str(level_id).isdigit():
                queryset = queryset.filter(models.Q(level_id=int(level_id)) | models.Q(level__code__iexact=str(level_id)))
            else:
                queryset = queryset.filter(level__code__iexact=str(level_id))

        serializer = CourseSerializer(queryset, many=True)
        return Response({
            'success': True,
            'data': serializer.data
        })

    def post(self, request):
        code = request.data.get('code', '').strip().upper()
        name = request.data.get('name', '').strip()
        level_id = request.data.get('level_id')

        if not code or not name:
            return Response({
                'success': False,
                'message': 'Course code and name are required.'
            }, status=status.HTTP_400_BAD_REQUEST)

        level = None
        if level_id:
            if str(level_id).isdigit():
                level = Level.objects.filter(id=int(level_id)).first() or Level.objects.filter(code__iexact=str(level_id)).first()
            else:
                level = Level.objects.filter(code__iexact=str(level_id)).first()
        if not level:
            level = Level.objects.first()
        
        from core.models import AcademicPeriod
        period = AcademicPeriod.objects.filter(is_active=True).first() or AcademicPeriod.objects.first()
        if not period:
            period = AcademicPeriod.objects.create(name='2025/2026 Academic Year — Semester 2', is_active=True)

        course, created = Course.objects.get_or_create(
            code=code,
            defaults={'name': name, 'level': level, 'academic_period': period}
        )
        if not created:
            course.name = name
            if level:
                course.level = level
            if not course.academic_period:
                course.academic_period = period
            course.save()

        if request.user.role == User.Role.LECTURER:
            LecturerCourse.objects.get_or_create(
                lecturer=request.user,
                course=course,
                defaults={'academic_period': period}
            )

        return Response({
            'success': True,
            'message': 'Course created and assigned successfully.',
            'data': CourseSerializer(course).data
        })


class GroupListView(APIView):
    permission_classes = [permissions.IsAuthenticated]

    def get(self, request):
        level_id = request.query_params.get('level_id')
        course_code = request.query_params.get('course_code')
        course_id = request.query_params.get('course_id')
        
        if request.user.role == User.Role.LECTURER:
            queryset = StudentGroup.objects.filter(lecturer=request.user)
            if level_id:
                queryset = queryset.filter(models.Q(level__code__iexact=str(level_id)) | models.Q(level_id=level_id if str(level_id).isdigit() else None))
            if course_code:
                queryset = queryset.filter(course__code__iexact=str(course_code).strip())
            elif course_id:
                queryset = queryset.filter(course_id=course_id)
            
            # If lecturer has no groups yet for this level/course, auto-create Group 1 for them!
            if not queryset.exists():
                from core.models import AcademicPeriod
                period = AcademicPeriod.objects.filter(is_active=True).first() or AcademicPeriod.objects.first()
                target_lvl = None
                if level_id:
                    target_lvl = Level.objects.filter(code__iexact=str(level_id)).first() or Level.objects.filter(id=level_id if str(level_id).isdigit() else None).first()
                if not target_lvl:
                    target_lvl = Level.objects.first()

                target_course = None
                if course_code:
                    target_course = Course.objects.filter(code__iexact=str(course_code).strip()).first()
                elif course_id:
                    target_course = Course.objects.filter(id=course_id).first()
                if not target_course and target_lvl:
                    lc = LecturerCourse.objects.filter(lecturer=request.user, course__level=target_lvl).first()
                    if lc:
                        target_course = lc.course

                if target_lvl and target_course and period:
                    grp, _ = StudentGroup.objects.get_or_create(
                        name="Group 1",
                        course=target_course,
                        level=target_lvl,
                        academic_period=period,
                        lecturer=request.user
                    )
                    queryset = StudentGroup.objects.filter(id=grp.id)
        else:
            queryset = StudentGroup.objects.all()
            rep_group_ids = get_user_rep_group_ids(request.user)
            if rep_group_ids is not None:
                queryset = queryset.filter(id__in=rep_group_ids)
            if level_id:
                queryset = queryset.filter(models.Q(level__code__iexact=str(level_id)) | models.Q(level_id=level_id if str(level_id).isdigit() else None))
            if course_code:
                queryset = queryset.filter(course__code__iexact=str(course_code).strip())
            elif course_id:
                queryset = queryset.filter(course_id=course_id)

        import re
        def group_sort_key(g):
            m = re.search(r'(\d+)\s*$', g.name or '')
            num = int(m.group(1)) if m else 999999
            c_code = g.course.code if g.course else ''
            return (c_code, num, g.name or '')

        ordered_groups = sorted(list(queryset.select_related('course', 'level')), key=group_sort_key)
        serializer = StudentGroupSerializer(ordered_groups, many=True)
        return Response({
            'success': True,
            'data': serializer.data
        })

    def post(self, request):
        import re
        name = (request.data.get('name') or '').strip()
        auto_increment = bool(request.data.get('auto_increment'))
        level_id = request.data.get('level_id') or request.query_params.get('level_id')
        course_code = request.data.get('course_code')
        course_id = request.data.get('course_id')
        lecturer_id = request.data.get('lecturer_id')

        prefix_hint = ''
        if name and " - " in name:
            parts = [p.strip() for p in name.split('-', 1)]
            prefix_hint = parts[0]
            name = parts[1]

        target_lecturer = request.user
        if request.user.is_staff and lecturer_id:
            target_lecturer = User.objects.filter(id=lecturer_id, role=User.Role.LECTURER).first() or request.user

        level = None
        if level_id:
            level = Level.objects.filter(code__iexact=str(level_id)).first()
            if not level and (isinstance(level_id, int) or (isinstance(level_id, str) and str(level_id).isdigit())):
                level = Level.objects.filter(id=int(level_id)).first()
        if not level and prefix_hint:
            level = Level.objects.filter(code__iexact=prefix_hint).first()
        if not level:
            level = Level.objects.first()

        target_course = None
        if course_code:
            target_course = Course.objects.filter(code__iexact=str(course_code).strip()).first()
        elif course_id:
            target_course = Course.objects.filter(id=course_id).first()
        elif prefix_hint:
            target_course = Course.objects.filter(code__iexact=prefix_hint).first()

        if not target_course and target_lecturer.role == User.Role.LECTURER:
            lc = LecturerCourse.objects.filter(lecturer=target_lecturer, course__level=level).first()
            if lc:
                target_course = lc.course

        if not target_course and target_lecturer.role == User.Role.LECTURER:
            return Response({
                'success': False,
                'message': f'You have no course assigned in {level.code if level else "this level"}.'
            }, status=status.HTTP_400_BAD_REQUEST)

        # Ensure course level matches the course itself if available
        if target_course and target_course.level:
            level = target_course.level

        from core.models import AcademicPeriod
        period = AcademicPeriod.objects.filter(is_active=True).first() or AcademicPeriod.objects.first()

        scoped_lecturer = target_lecturer if target_lecturer.role == User.Role.LECTURER else None
        existing_qs = StudentGroup.objects.filter(
            course=target_course,
            level=level,
            lecturer=scoped_lecturer
        )

        # Sequential auto-numbering: Group 1, Group 2, Group 3, ...
        if not name or auto_increment:
            max_num = 0
            for existing_grp in existing_qs:
                match = re.search(r'(\d+)\s*$', existing_grp.name or '')
                if match:
                    max_num = max(max_num, int(match.group(1)))
            next_num = max(max_num + 1, existing_qs.count() + 1)
            while existing_qs.filter(name__iexact=f"Group {next_num}").exists():
                next_num += 1
            name = f"Group {next_num}"

        group, created = StudentGroup.objects.get_or_create(
            name=name,
            course=target_course,
            level=level,
            lecturer=scoped_lecturer,
            defaults={'academic_period': period}
        )

        return Response({
            'success': True,
            'message': f'{StudentGroupSerializer(group).data.get("display_name", str(group))} created successfully.',
            'data': StudentGroupSerializer(group).data
        })

    def delete(self, request):
        group_id = request.data.get('group_id') or request.query_params.get('group_id')
        if not group_id:
            return Response({'success': False, 'message': 'group_id is required.'}, status=status.HTTP_400_BAD_REQUEST)
        
        group = StudentGroup.objects.filter(id=group_id).first()
        if not group:
            return Response({'success': False, 'message': 'Group not found.'}, status=status.HTTP_404_NOT_FOUND)

        if not request.user.is_staff and group.lecturer != request.user:
            return Response({'success': False, 'message': 'Permission denied.'}, status=status.HTTP_403_FORBIDDEN)

        # Unlink students from this group
        User.objects.filter(group=group).update(group=None)
        group.delete()

        return Response({'success': True, 'message': 'Group deleted successfully.'})


class StudentListView(APIView):
    permission_classes = [permissions.IsAuthenticated]

    def get(self, request):
        level_id = request.query_params.get('level_id')
        group_id = request.query_params.get('group_id')
        search_query = request.query_params.get('search', '').strip()

        queryset = User.objects.filter(role__in=[User.Role.STUDENT, User.Role.REP])

        rep_group_ids = get_user_rep_group_ids(request.user)
        if rep_group_ids is not None:
            queryset = queryset.filter(models.Q(group_id__in=rep_group_ids) | models.Q(enrolled_groups__id__in=rep_group_ids)).distinct()
        elif request.user.role == User.Role.LECTURER:
            lec_groups = StudentGroup.objects.filter(lecturer=request.user)
            if level_id:
                lec_groups = lec_groups.filter(
                    models.Q(level__code__iexact=str(level_id)) |
                    models.Q(level_id=int(level_id) if str(level_id).isdigit() else None)
                )
            if group_id:
                lec_groups = lec_groups.filter(id=group_id)
            if lec_groups.exists():
                queryset = queryset.filter(models.Q(group__in=lec_groups) | models.Q(enrolled_groups__in=lec_groups)).distinct()
            else:
                queryset = User.objects.none()
        elif group_id:
            queryset = queryset.filter(models.Q(group_id=group_id) | models.Q(enrolled_groups__id=group_id)).distinct()
        elif level_id:
            queryset = queryset.filter(models.Q(group__level_id=level_id) | models.Q(enrolled_groups__level_id=level_id)).distinct()

        if search_query:
            queryset = queryset.filter(
                models.Q(first_name__icontains=search_query) |
                models.Q(last_name__icontains=search_query) |
                models.Q(index_number__icontains=search_query)
            )

        queryset = queryset.order_by('first_name', 'last_name', 'username')
        serializer = UserSerializer(queryset, many=True)
        return Response({
            'success': True,
            'data': serializer.data
        })

    def post(self, request):
        first_name = request.data.get('first_name', '').strip()
        last_name = request.data.get('last_name', '').strip()
        name = request.data.get('name', '').strip()
        index_number = request.data.get('index_number', '').strip()
        provided_email = request.data.get('email', '').strip()
        group_id = request.data.get('group_id')
        group_name = request.data.get('group_name', '').strip()
        level_code = request.data.get('level_code') or request.data.get('level_id') or ''

        if name and not (first_name and last_name):
            parts = name.split(' ', 1)
            first_name = parts[0]
            last_name = parts[1] if len(parts) > 1 else ''

        if not index_number and provided_email and '@' in provided_email:
            prefix = provided_email.split('@')[0]
            if prefix.isdigit():
                index_number = prefix

        if not index_number:
            return Response({'success': False, 'message': 'Index number is required.'}, status=status.HTTP_400_BAD_REQUEST)

        email = provided_email or f"{index_number}@st.uew.edu.gh"

        if not first_name:
            first_name = "Student"
        if not last_name:
            last_name = index_number

        group = None
        base_group_qs = StudentGroup.objects.all()
        if request.user.role == User.Role.LECTURER:
            lec_qs = base_group_qs.filter(lecturer=request.user)
            if lec_qs.exists():
                base_group_qs = lec_qs
        if level_code:
            lvl_qs = base_group_qs.filter(
                models.Q(level__code__iexact=str(level_code)) |
                models.Q(level_id=int(level_code) if str(level_code).isdigit() else None)
            )
            if lvl_qs.exists():
                base_group_qs = lvl_qs

        if group_id:
            group = StudentGroup.objects.filter(id=group_id).first()
        elif group_name:
            if " - " in group_name:
                c_code, g_name = [p.strip() for p in group_name.split('-', 1)]
                group = base_group_qs.filter(course__code__iexact=c_code, name__iexact=g_name).first()
                if not group:
                    group = base_group_qs.filter(level__code__iexact=c_code, name__iexact=g_name).first()
                if not group:
                    group = StudentGroup.objects.filter(course__code__iexact=c_code, name__iexact=g_name).first()
                if not group:
                    group = StudentGroup.objects.filter(level__code__iexact=c_code, name__iexact=g_name).first()
            if not group:
                group = base_group_qs.filter(name__iexact=group_name).first()
            if not group:
                group = StudentGroup.objects.filter(name__iexact=group_name).first()

        user = User.objects.filter(index_number=index_number).first() or (User.objects.filter(email__iexact=provided_email).first() if provided_email else User.objects.filter(email__iexact=email).first())
        if user:
            if (not user.first_name or user.first_name == "Student") and first_name != "Student":
                user.first_name = first_name
            elif first_name and first_name != "Student":
                user.first_name = first_name
            if last_name and last_name != index_number:
                user.last_name = last_name
            if provided_email and provided_email.lower() != (user.email or '').lower():
                if not User.objects.filter(email__iexact=provided_email).exclude(id=user.id).exists():
                    user.email = provided_email
            if group:
                user.group = group
            user.save()
            if group:
                group.members.add(user)
            msg = f"Updated student {user.first_name} {user.last_name}."
        else:
            user = User.objects.create_user(
                username=email,
                email=email,
                password='password123',
                first_name=first_name,
                last_name=last_name,
                index_number=index_number,
                role=User.Role.STUDENT,
                must_change_password=True,
                group=group
            )
            if group:
                group.members.add(user)
            msg = f"Added student {first_name} {last_name} to {str(group) if group else 'cohort'}."

        return Response({
            'success': True,
            'message': msg,
            'data': {
                'id': user.id,
                'name': f"{user.first_name} {user.last_name}",
                'index': user.index_number,
                'email': user.email,
                'group': user.group.name if user.group else "Unassigned",
                'group_id': user.group_id
            }
        })


class CourseDetailView(APIView):
    permission_classes = [permissions.IsAuthenticated]

    def delete(self, request, code):
        course = Course.objects.filter(code__iexact=code).first()
        if not course and str(code).isdigit():
            course = Course.objects.filter(id=int(code)).first()
        if not course:
            return Response({
                'success': False,
                'message': 'Course not found.'
            }, status=status.HTTP_404_NOT_FOUND)

        if request.user.role == User.Role.LECTURER:
            LecturerCourse.objects.filter(lecturer=request.user, course=course).delete()
            return Response({
                'success': True,
                'message': f'Course {course.code} unlinked from your dashboard.'
            })

        course.delete()
        return Response({
            'success': True,
            'message': 'Course deleted successfully.'
        })


class CourseRepView(APIView):
    permission_classes = [permissions.IsAuthenticated]

    def get(self, request):
        queryset = CourseRep.objects.all().select_related('student', 'group', 'group__level', 'course', 'created_by')
        if request.user.role == User.Role.LECTURER:
            lec_course_ids = LecturerCourse.objects.filter(lecturer=request.user).values_list('course_id', flat=True)
            lec_group_ids = StudentGroup.objects.filter(lecturer=request.user).values_list('id', flat=True)
            queryset = queryset.filter(
                models.Q(created_by=request.user) |
                models.Q(course_id__in=lec_course_ids) |
                models.Q(group_id__in=lec_group_ids) |
                models.Q(course__lecturers__lecturer=request.user)
            ).distinct()

        elif request.user.role == User.Role.REP:
            queryset = queryset.filter(student=request.user)

        data = []
        for rep in queryset:
            data.append({
                'id': rep.id,
                'student_id': rep.student.id,
                'name': f"{rep.student.first_name} {rep.student.last_name}".strip() or rep.student.username,
                'index_number': rep.student.index_number or rep.student.username,
                'email': rep.student.email,
                'group_name': str(rep.group) if rep.group else "Group 1",
                'level_code': rep.group.level.code if (rep.group and rep.group.level) else "L100",
                'course_code': rep.course.code if rep.course else "All",
                'course_name': rep.course.name if rep.course else "",
                'created_by': f"{rep.created_by.first_name} {rep.created_by.last_name}".strip() if rep.created_by else "Admin"
            })

        return Response({
            'success': True,
            'data': data
        })

    def post(self, request):
        try:
            student_id = request.data.get('student_id')
            index_number = str(request.data.get('index_number') or '').strip()
            email = str(request.data.get('email') or '').strip().lower()
            first_name = str(request.data.get('first_name') or '').strip()
            last_name = str(request.data.get('last_name') or '').strip()
            group_id = request.data.get('group_id')
            course_code = str(request.data.get('course_code') or '').strip()
            new_password = str(request.data.get('password') or '').strip()

            # Flexible student resolution across ID, Index Number, Email, and Username
            student = None
            if student_id:
                student = User.objects.filter(id=student_id).first()
            if not student and index_number:
                student = (
                    User.objects.filter(index_number__iexact=index_number).first() or
                    User.objects.filter(username__iexact=index_number).first()
                )
            if not student and email:
                student = (
                    User.objects.filter(email__iexact=email).first() or
                    User.objects.filter(username__iexact=email).first()
                )
            if not student and email and '@' in email:
                prefix = email.split('@')[0]
                if prefix.isdigit():
                    student = User.objects.filter(index_number__iexact=prefix).first()

            was_existing_student = student is not None

            if not student:
                if not email and index_number:
                    email = f"{index_number}@st.uew.edu.gh"
                if not email or not first_name:
                    return Response({
                        'success': False,
                        'message': 'Student email and first name are required to onboard a Course Rep.'
                    }, status=status.HTTP_400_BAD_REQUEST)

                # Guard against duplicate username or index constraint collisions
                collision = User.objects.filter(
                    models.Q(username__iexact=email) |
                    models.Q(email__iexact=email) |
                    (models.Q(index_number__iexact=index_number) if index_number else models.Q(id=-1))
                ).first()

                if collision:
                    student = collision
                    was_existing_student = True
                else:
                    target_index = index_number or (email.split('@')[0] if email.split('@')[0].isdigit() else None)
                    student = User.objects.create_user(
                        username=email,
                        email=email,
                        password=new_password or 'password123',
                        first_name=first_name,
                        last_name=last_name,
                        index_number=target_index,
                        role=User.Role.REP,
                        must_change_password=True
                    )

            if was_existing_student:
                student.role = User.Role.REP
                if first_name and (not student.first_name or student.first_name == "Student"):
                    student.first_name = first_name
                if last_name and (not student.last_name or student.last_name == student.index_number):
                    student.last_name = last_name
                if new_password:
                    student.set_password(new_password)
                    student.must_change_password = False
                student.save()

            # Resolve Course
            course = None
            if course_code:
                course = Course.objects.filter(code__iexact=course_code).first()
                if not course and course_code.isdigit():
                    course = Course.objects.filter(id=int(course_code)).first()

            # Resolve Group strictly matching the appointed course when course is provided
            group = None
            raw_group_str = str(group_id).strip() if group_id else ""
            parsed_group_name = raw_group_str
            if " - " in raw_group_str:
                _, parsed_group_name = [p.strip() for p in raw_group_str.split('-', 1)]

            if group_id:
                if isinstance(group_id, int) or raw_group_str.isdigit():
                    candidate = StudentGroup.objects.filter(id=int(raw_group_str)).first()
                    if candidate and (not course or candidate.course_id == course.id or candidate.course_id is None):
                        group = candidate
                if not group and course:
                    group = StudentGroup.objects.filter(course=course, name__iexact=parsed_group_name).first()
                if not group and not course and " - " in raw_group_str:
                    prefix, g_name = [p.strip() for p in raw_group_str.split('-', 1)]
                    group = StudentGroup.objects.filter(
                        models.Q(course__code__iexact=prefix, name__iexact=g_name) |
                        models.Q(level__code__iexact=prefix, name__iexact=g_name)
                    ).first()
                if not group and not course:
                    group = StudentGroup.objects.filter(name__iexact=raw_group_str).first()

            from core.models import AcademicPeriod
            period = AcademicPeriod.objects.filter(is_active=True).first() or AcademicPeriod.objects.first()

            if not group and course:
                target_g_name = parsed_group_name if (parsed_group_name and not parsed_group_name.isdigit()) else "Group 1"
                group = StudentGroup.objects.filter(course=course, name__iexact=target_g_name).first()
                if not group:
                    group, _ = StudentGroup.objects.get_or_create(
                        name=target_g_name,
                        course=course,
                        level=course.level,
                        lecturer=request.user if request.user.role == User.Role.LECTURER else None,
                        defaults={'academic_period': period}
                    )

            # If still no group exists, auto-provision default group for this lecturer
            if not group:
                target_level = course.level if course else Level.objects.first()
                target_course = course or Course.objects.filter(level=target_level).first()
                group, _ = StudentGroup.objects.get_or_create(
                    name="Group 1",
                    course=target_course,
                    level=target_level,
                    academic_period=period,
                    lecturer=request.user if request.user.role == User.Role.LECTURER else None
                )

            if not course and group and group.course:
                course = group.course

            # Look up or create CourseRep cleanly (avoiding MultipleObjectsReturned or unique collisions)
            rep_obj = CourseRep.objects.filter(student=student, group=group, course=course).first()
            if not rep_obj and course:
                rep_obj = CourseRep.objects.filter(student=student, course=course).first()
            if not rep_obj:
                rep_obj = CourseRep.objects.filter(student=student, group=group).first()

            if not rep_obj:
                rep_obj = CourseRep.objects.create(
                    student=student,
                    group=group,
                    course=course,
                    academic_period=period,
                    created_by=request.user
                )
            else:
                rep_obj.group = group
                if course:
                    rep_obj.course = course
                rep_obj.created_by = request.user
                rep_obj.save()

            if group:
                group.members.add(student)
                if not student.group:
                    student.group = group
                    student.save(update_fields=['group'])

            return Response({
                'success': True,
                'message': f'Successfully appointed {student.first_name} {student.last_name} as Course Rep!',
                'data': {
                    'id': rep_obj.id,
                    'email': student.email or student.username,
                    'index_number': student.index_number,
                    'existing_student': was_existing_student,
                    'password_kept': was_existing_student and not bool(new_password),
                    'password': new_password if new_password else (None if was_existing_student else 'password123')
                }
            })
        except Exception as e:
            return Response({
                'success': False,
                'message': f'Failed to appoint Course Rep: {str(e)}'
            }, status=status.HTTP_400_BAD_REQUEST)

