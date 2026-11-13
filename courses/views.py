from django.db import models
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import status, permissions
from core.models import Level
from core.serializers import LevelSerializer
from .models import Course, StudentGroup, CourseRep, LecturerCourse
from .serializers import CourseSerializer, StudentGroupSerializer
from .helpers import get_user_rep_group_ids
from accounts.models import User
from accounts.serializers import UserSerializer


class LevelListView(APIView):
    permission_classes = [permissions.IsAuthenticated]

    def get(self, request):
        levels = Level.objects.all()
        serializer = LevelSerializer(levels, many=True)
        return Response({
            'success': True,
            'data': serializer.data
        })


class CourseListView(APIView):
    permission_classes = [permissions.IsAuthenticated]

    def get(self, request):
        level_id = request.query_params.get('level_id')
        rep_me = request.query_params.get('rep')

        queryset = Course.objects.all()

        if request.user.role == User.Role.LECTURER:
            lecturer_course_ids = LecturerCourse.objects.filter(lecturer=request.user).values_list('course_id', flat=True)
            if lecturer_course_ids.exists():
                lec_qs = queryset.filter(id__in=lecturer_course_ids)
                if level_id:
                    if str(level_id).isdigit():
                        lec_qs_level = lec_qs.filter(models.Q(level_id=int(level_id)) | models.Q(level__code__iexact=str(level_id)))
                    else:
                        lec_qs_level = lec_qs.filter(level__code__iexact=str(level_id))
                    if lec_qs_level.exists():
                        queryset = lec_qs_level
                    else:
                        if str(level_id).isdigit():
                            queryset = queryset.filter(models.Q(level_id=int(level_id)) | models.Q(level__code__iexact=str(level_id)))
                        else:
                            queryset = queryset.filter(level__code__iexact=str(level_id))
                else:
                    queryset = lec_qs
            elif level_id:
                if str(level_id).isdigit():
                    queryset = queryset.filter(models.Q(level_id=int(level_id)) | models.Q(level__code__iexact=str(level_id)))
                else:
                    queryset = queryset.filter(level__code__iexact=str(level_id))
        elif level_id:
            if str(level_id).isdigit():
                queryset = queryset.filter(models.Q(level_id=int(level_id)) | models.Q(level__code__iexact=str(level_id)))
            else:
                queryset = queryset.filter(level__code__iexact=str(level_id))
        elif request.user.role == User.Role.REP:
            # Course Reps can ONLY see and access courses they have been specifically assigned to
            rep_assignments = CourseRep.objects.filter(student=request.user, course__isnull=False)
            if rep_assignments.exists():
                assigned_course_ids = rep_assignments.values_list('course_id', flat=True)
                queryset = queryset.filter(id__in=assigned_course_ids)
            else:
                queryset = Course.objects.none()

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

                if target_lvl and period:
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

        serializer = StudentGroupSerializer(queryset.order_by('name'), many=True)
        return Response({
            'success': True,
            'data': serializer.data
        })

    def post(self, request):
        name = request.data.get('name', '').strip()
        level_id = request.data.get('level_id') or request.query_params.get('level_id')
        course_code = request.data.get('course_code')
        course_id = request.data.get('course_id')
        lecturer_id = request.data.get('lecturer_id')

        if name and " - " in name:
            parts = [p.strip() for p in name.split('-', 1)]
            if not course_code:
                course_code = parts[0]
            name = parts[1]

        target_lecturer = request.user
        if request.user.is_staff and lecturer_id:
            target_lecturer = User.objects.filter(id=lecturer_id, role=User.Role.LECTURER).first() or request.user

        level = None
        if level_id:
            level = Level.objects.filter(code__iexact=str(level_id)).first()
            if not level and (isinstance(level_id, int) or (isinstance(level_id, str) and str(level_id).isdigit())):
                level = Level.objects.filter(id=int(level_id)).first()
        if not level:
            level = Level.objects.first()

        target_course = None
        if course_code:
            target_course = Course.objects.filter(code__iexact=str(course_code).strip()).first()
        elif course_id:
            target_course = Course.objects.filter(id=course_id).first()
        if not target_course and target_lecturer.role == User.Role.LECTURER:
            lc = LecturerCourse.objects.filter(lecturer=target_lecturer, course__level=level).first()
            if lc:
                target_course = lc.course
        
        from core.models import AcademicPeriod
        period = AcademicPeriod.objects.filter(is_active=True).first() or AcademicPeriod.objects.first()

        # If name not given, auto-calculate next group number for this course & lecturer e.g. "Group 2"
        if not name:
            existing_count = StudentGroup.objects.filter(course=target_course, level=level, lecturer=target_lecturer).count()
            name = f"Group {existing_count + 1}"

        group, created = StudentGroup.objects.get_or_create(
            name=name,
            course=target_course,
            level=level,
            lecturer=target_lecturer if target_lecturer.role == User.Role.LECTURER else None,
            defaults={'academic_period': period}
        )

        return Response({
            'success': True,
            'message': f'{str(group)} created successfully.',
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
            queryset = queryset.filter(group_id__in=rep_group_ids)
        elif request.user.role == User.Role.LECTURER:
            lec_groups = StudentGroup.objects.filter(lecturer=request.user)
            if group_id:
                queryset = queryset.filter(group_id=group_id)
            elif lec_groups.exists():
                queryset = queryset.filter(group__in=lec_groups)
        elif group_id:
            queryset = queryset.filter(group_id=group_id)
        elif level_id:
            queryset = queryset.filter(group__level_id=level_id)

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
        email = request.data.get('email', '').strip()
        group_id = request.data.get('group_id')
        group_name = request.data.get('group_name', '').strip()

        if name and not (first_name and last_name):
            parts = name.split(' ', 1)
            first_name = parts[0]
            last_name = parts[1] if len(parts) > 1 else ''

        if not index_number and email and '@' in email:
            prefix = email.split('@')[0]
            if prefix.isdigit():
                index_number = prefix

        if not index_number:
            return Response({'success': False, 'message': 'Index number is required.'}, status=status.HTTP_400_BAD_REQUEST)

        if not email:
            email = f"{index_number}@st.uew.edu.gh"

        if not first_name:
            first_name = "Student"
        if not last_name:
            last_name = index_number

        group = None
        if group_id:
            group = StudentGroup.objects.filter(id=group_id).first()
        elif group_name:
            if " - " in group_name:
                c_code, g_name = [p.strip() for p in group_name.split('-', 1)]
                if request.user.role == User.Role.LECTURER:
                    group = StudentGroup.objects.filter(course__code__iexact=c_code, name__iexact=g_name, lecturer=request.user).first()
                if not group:
                    group = StudentGroup.objects.filter(course__code__iexact=c_code, name__iexact=g_name).first()
            if not group and request.user.role == User.Role.LECTURER:
                group = StudentGroup.objects.filter(name__iexact=group_name, lecturer=request.user).first()
            if not group:
                group = StudentGroup.objects.filter(name__iexact=group_name).first()

        user = User.objects.filter(index_number=index_number).first() or User.objects.filter(email__iexact=email).first()
        if user:
            user.first_name = first_name
            user.last_name = last_name
            user.email = email
            if group:
                user.group = group
            user.save()
            if group:
                group.members.add(user)
            msg = f"Updated student {first_name} {last_name}."
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
        queryset = CourseRep.objects.all()
        if request.user.role == User.Role.LECTURER:
            queryset = queryset.filter(models.Q(created_by=request.user) | models.Q(course__lecturers__lecturer=request.user)).distinct()
        
        data = []
        for rep in queryset:
            data.append({
                'id': rep.id,
                'student_id': rep.student.id,
                'name': f"{rep.student.first_name} {rep.student.last_name}",
                'index_number': rep.student.index_number or rep.student.username,
                'email': rep.student.email,
                'group_name': str(rep.group) if rep.group else "Group 1",
                'level_code': rep.group.level.code if rep.group else "L100",
                'course_code': rep.course.code if rep.course else "All",
                'created_by': f"{rep.created_by.first_name} {rep.created_by.last_name}" if rep.created_by else "Admin"
            })

        return Response({
            'success': True,
            'data': data
        })

    def post(self, request):
        student_id = request.data.get('student_id')
        index_number = request.data.get('index_number', '').strip()
        email = request.data.get('email', '').strip()
        first_name = request.data.get('first_name', '').strip()
        last_name = request.data.get('last_name', '').strip()
        group_id = request.data.get('group_id')
        course_code = request.data.get('course_code')
        new_password = request.data.get('password', '').strip()

        student = None
        if student_id:
            student = User.objects.filter(id=student_id).first()
        elif index_number:
            student = User.objects.filter(index_number=index_number).first() or User.objects.filter(username=index_number).first()
        elif email:
            student = User.objects.filter(email__iexact=email).first()

        if not student:
            if not email or not first_name:
                return Response({'success': False, 'message': 'Student email and first name are required to create a Course Rep.'}, status=status.HTTP_400_BAD_REQUEST)
            student = User.objects.create_user(
                username=email,
                email=email,
                password=new_password or 'password123',
                first_name=first_name,
                last_name=last_name,
                index_number=index_number or email.split('@')[0],
                role=User.Role.REP
            )
        else:
            student.role = User.Role.REP
            if new_password:
                student.set_password(new_password)
            student.save()

        course = Course.objects.filter(code__iexact=course_code).first() if course_code else None

        group = None
        if group_id:
            if isinstance(group_id, int) or (isinstance(group_id, str) and group_id.isdigit()):
                group = StudentGroup.objects.filter(id=group_id).first()
            if not group and " - " in str(group_id):
                c_code, g_name = [p.strip() for p in str(group_id).split('-', 1)]
                group = StudentGroup.objects.filter(course__code__iexact=c_code, name__iexact=g_name).first()
            if not group and course:
                group = StudentGroup.objects.filter(course=course, name__iexact=str(group_id).strip()).first()
            if not group:
                group = StudentGroup.objects.filter(name__iexact=group_id).first()
        if not group and course:
            group = StudentGroup.objects.filter(course=course).first()
        if not group:
            group = StudentGroup.objects.first()

        from core.models import AcademicPeriod
        period = AcademicPeriod.objects.filter(is_active=True).first() or AcademicPeriod.objects.first()

        rep_obj, created = CourseRep.objects.get_or_create(
            student=student,
            group=group,
            defaults={'course': course, 'academic_period': period, 'created_by': request.user}
        )
        if not created:
            rep_obj.course = course
            rep_obj.created_by = request.user
            rep_obj.save()

        if group:
            group.members.add(student)

        return Response({
            'success': True,
            'message': f'Successfully appointed {student.first_name} {student.last_name} as Course Rep!',
            'data': {
                'id': rep_obj.id,
                'email': student.email,
                'password': new_password or 'password123'
            }
        })

