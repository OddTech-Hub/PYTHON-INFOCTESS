from django.db import models
from rest_framework import serializers
from .models import StudentGroup, Course, LecturerCourse, CourseRep
from accounts.models import User
from accounts.serializers import UserSerializer
from core.serializers import LevelSerializer


class CourseSerializer(serializers.ModelSerializer):
    class Meta:
        model = Course
        fields = '__all__'


class StudentGroupSerializer(serializers.ModelSerializer):
    level = LevelSerializer(read_only=True)
    course = CourseSerializer(read_only=True)
    academic_period_name = serializers.SerializerMethodField()
    display_name = serializers.SerializerMethodField()
    enrolled_count = serializers.SerializerMethodField()
    
    class Meta:
        model = StudentGroup
        fields = '__all__'

    def get_academic_period_name(self, obj):
        return obj.academic_period.name if obj.academic_period else None

    def get_display_name(self, obj):
        if obj.course:
            return f"{obj.course.code} - {obj.name}"
        return f"{obj.level.code} - {obj.name}"

    def get_enrolled_count(self, obj):
        return User.objects.filter(models.Q(group=obj) | models.Q(enrolled_groups=obj)).distinct().count()


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
