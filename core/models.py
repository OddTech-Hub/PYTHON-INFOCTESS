from django.db import models


class AcademicPeriod(models.Model):
    name = models.CharField(max_length=100)  # e.g., "Semester 1 2025/26"
    start_date = models.DateField(null=True, blank=True)
    end_date = models.DateField(null=True, blank=True)
    is_active = models.BooleanField(default=True)

    def __str__(self):
        return self.name


class Level(models.Model):
    code = models.CharField(max_length=20, unique=True)  # e.g., "L100", "L200"
    label = models.CharField(max_length=50)  # e.g., "Level 100"
    year = models.CharField(max_length=50)  # e.g., "1st Year"
    color = models.CharField(max_length=20, default="#3b82f6")
    bg = models.CharField(max_length=20, default="#eff6ff")
    border = models.CharField(max_length=20, default="#bfdbfe")

    def __str__(self):
        return self.label
