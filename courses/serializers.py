from rest_framework import serializers
from .models import StudentGroup, Course, LecturerCourse, CourseRep
from accounts.serializers import UserSerializer
from core.serializers import LevelSerializer


class StudentGroupSerializer(serializers.ModelSerializer):
    level = LevelSerializer(read_only=True)
    
    class Meta:
        model = StudentGroup
        fields = '__all__'


class CourseSerializer(serializers.ModelSerializer):
    class Meta:
        model = Course
        fields = '__all__'


class LecturerCourseSerializer(serializers.ModelSerializer):
    course = CourseSerializer(read_only=True)
    lecturer = UserSerializer(read_only=True)

    class Meta:
        model = LecturerCourse
        fields = '__all__'


class CourseRepSerializer(serializers.ModelSerializer):
    student = UserSerializer(read_only=True)
    group = StudentGroupSerializer(read_only=True)

    class Meta:
        model = CourseRep
        fields = '__all__'
