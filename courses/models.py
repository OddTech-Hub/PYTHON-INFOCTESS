from django.db import models
from core.models import Level, AcademicPeriod
from django.conf import settings


class StudentGroup(models.Model):
    name = models.CharField(max_length=50)  # e.g., "Group 1", "Group 2"
    level = models.ForeignKey(Level, on_delete=models.CASCADE, related_name='groups')
    academic_period = models.ForeignKey(AcademicPeriod, on_delete=models.CASCADE, related_name='groups')
    lecturer = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, null=True, blank=True, related_name='lecturer_groups')

    class Meta:
        unique_together = ('name', 'level', 'academic_period', 'lecturer')

    def __str__(self):
        return f"{self.level.code} - {self.name}"


class Course(models.Model):
    code = models.CharField(max_length=20, unique=True)  # e.g., "ICTE125"
    name = models.CharField(max_length=200)  # e.g., "Multimedia Authoring in Education"
    level = models.ForeignKey(Level, on_delete=models.CASCADE, related_name='courses')
    academic_period = models.ForeignKey(AcademicPeriod, on_delete=models.CASCADE, related_name='courses')

    def __str__(self):
        return f"{self.code} - {self.name}"


class LecturerCourse(models.Model):
    lecturer = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='lecturer_courses')
    course = models.ForeignKey(Course, on_delete=models.CASCADE, related_name='lecturers')
    academic_period = models.ForeignKey(AcademicPeriod, on_delete=models.CASCADE)

    class Meta:
        unique_together = ('lecturer', 'course', 'academic_period')

    def __str__(self):
        return f"{self.lecturer.first_name} {self.lecturer.last_name} teaches {self.course.code}"


class CourseRep(models.Model):
    student = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='course_rep_assignments')
    course = models.ForeignKey(Course, on_delete=models.CASCADE, null=True, blank=True, related_name='reps')
    group = models.ForeignKey(StudentGroup, on_delete=models.CASCADE, related_name='reps')
    academic_period = models.ForeignKey(AcademicPeriod, on_delete=models.CASCADE, null=True, blank=True)
    created_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, null=True, blank=True, related_name='created_course_reps')

    class Meta:
        unique_together = ('student', 'group', 'course', 'academic_period')

    def __str__(self):
        return f"{self.student.first_name} rep for {self.group}"
