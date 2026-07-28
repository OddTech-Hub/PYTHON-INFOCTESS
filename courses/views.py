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
            queryset = queryset.filter(id__in=lecturer_course_ids)
        elif level_id:
            queryset = queryset.filter(level_id=level_id)
        elif rep_me == 'me' and request.user.role == User.Role.REP:
            rep_assignments = CourseRep.objects.filter(student=request.user)
            if rep_assignments.exists():
                level_ids = rep_assignments.values_list('group__level_id', flat=True)
                queryset = queryset.filter(level_id__in=level_ids)
            elif request.user.group:
                queryset = queryset.filter(level=request.user.group.level)
            else:
                queryset = Course.objects.all()

        if level_id and request.user.role == User.Role.LECTURER:
            queryset = queryset.filter(level_id=level_id)

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
            level = Level.objects.filter(code__iexact=level_id).first()
            if not level and (isinstance(level_id, int) or (isinstance(level_id, str) and level_id.isdigit())):
                level = Level.objects.filter(id=level_id).first()
        if not level:
            level = Level.objects.first()
        
        from core.models import AcademicPeriod
        period = AcademicPeriod.objects.filter(is_active=True).first() or AcademicPeriod.objects.first()
        if not period:
            period = AcademicPeriod.objects.create(name='2025/2026 Semester 2', is_active=True)

        course, created = Course.objects.get_or_create(
            code=code,
            defaults={'name': name, 'level': level, 'academic_period': period}
        )
        if not created:
            course.name = name
            course.level = level
            if not course.academic_period:
                course.academic_period = period
            course.save()

        if request.user.role == User.Role.LECTURER:
            LecturerCourse.objects.get_or_create(
                lecturer=request.user,
                course=course,
                academic_period=period
            )

        return Response({
            'success': True,
            'message': 'Course created successfully.',
            'data': CourseSerializer(course).data
        })


class GroupListView(APIView):
    permission_classes = [permissions.IsAuthenticated]

    def get(self, request):
        level_id = request.query_params.get('level_id')
        queryset = StudentGroup.objects.all()
        
        if request.user.role == User.Role.LECTURER:
            queryset = queryset.filter(models.Q(lecturer=request.user) | models.Q(lecturer__isnull=True))
        else:
            rep_group_ids = get_user_rep_group_ids(request.user)
            if rep_group_ids is not None:
                queryset = queryset.filter(id__in=rep_group_ids)

        if level_id:
            queryset = queryset.filter(level_id=level_id)
            
        serializer = StudentGroupSerializer(queryset, many=True)
        return Response({
            'success': True,
            'data': serializer.data
        })

    def post(self, request):
        name = request.data.get('name', '').strip()
        level_id = request.data.get('level_id')

        if not name:
            return Response({
                'success': False,
                'message': 'Group name is required.'
            }, status=status.HTTP_400_BAD_REQUEST)

        level = None
        if level_id:
            level = Level.objects.filter(code__iexact=level_id).first()
            if not level and (isinstance(level_id, int) or (isinstance(level_id, str) and level_id.isdigit())):
                level = Level.objects.filter(id=level_id).first()
        if not level:
            level = Level.objects.first()
        
        from core.models import AcademicPeriod
        period = AcademicPeriod.objects.filter(is_active=True).first()

        group, created = StudentGroup.objects.get_or_create(
            name=name,
            level=level,
            lecturer=request.user if request.user.role == User.Role.LECTURER else None,
            defaults={'academic_period': period}
        )

        return Response({
            'success': True,
            'message': 'Group created successfully.',
            'data': StudentGroupSerializer(group).data
        })


class StudentListView(APIView):
    permission_classes = [permissions.IsAuthenticated]

    def get(self, request):
        level_id = request.query_params.get('level_id')
        group_id = request.query_params.get('group_id')
        search_query = request.query_params.get('search', '').strip()

        # Users with student role (or rep since reps are technically student users too)
        queryset = User.objects.filter(role__in=[User.Role.STUDENT, User.Role.REP])

        rep_group_ids = get_user_rep_group_ids(request.user)
        if rep_group_ids is not None:
            queryset = queryset.filter(group_id__in=rep_group_ids)
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

        serializer = UserSerializer(queryset, many=True)
        return Response({
            'success': True,
            'data': serializer.data
        })


class CourseDetailView(APIView):
    permission_classes = [permissions.IsAuthenticated]

    def delete(self, request, code):
        course = Course.objects.filter(code__iexact=code).first() or Course.objects.filter(id=code).first()
        if not course:
            return Response({
                'success': False,
                'message': 'Course not found.'
            }, status=status.HTTP_404_NOT_FOUND)

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
                'group_name': rep.group.name if rep.group else "Group 1",
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

        group = None
        if group_id:
            if isinstance(group_id, int) or (isinstance(group_id, str) and group_id.isdigit()):
                group = StudentGroup.objects.filter(id=group_id).first()
            if not group:
                group = StudentGroup.objects.filter(name__iexact=group_id).first()
        if not group:
            group = StudentGroup.objects.first()

        course = Course.objects.filter(code__iexact=course_code).first() if course_code else None

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

        return Response({
            'success': True,
            'message': f'Successfully appointed {student.first_name} {student.last_name} as Course Rep!',
            'data': {
                'id': rep_obj.id,
                'email': student.email,
                'password': new_password or 'password123'
            }
        })

