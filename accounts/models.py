from django.db import models
from django.contrib.auth.models import AbstractUser


class User(AbstractUser):
    class Role(models.TextChoices):
        LECTURER = 'lecturer', 'Lecturer'
        REP = 'rep', 'Course Representative'
        STUDENT = 'student', 'Student'

    role = models.CharField(
        max_length=20,
        choices=Role.choices,
        default=Role.STUDENT
    )
    index_number = models.CharField(
        max_length=50,
        unique=True,
        blank=True,
        null=True
    )
    pin = models.CharField(
        max_length=128,
        blank=True,
        null=True
    )
    device_id = models.CharField(
        max_length=100,
        blank=True,
        null=True
    )
    device_name = models.CharField(
        max_length=100,
        blank=True,
        null=True
    )
    group = models.ForeignKey(
        'courses.StudentGroup',
        on_delete=models.SET_NULL,
        blank=True,
        null=True,
        related_name='students'
    )
    must_change_password = models.BooleanField(
        default=True,
        help_text="Designates whether the user must change their password upon next login."
    )

    def save(self, *args, **kwargs):
        # Normalize email to lowercase
        if self.email:
            self.email = self.email.strip().lower()

        # 1. Lecturers do NOT use index numbers
        if self.role == self.Role.LECTURER or self.is_superuser:
            self.index_number = None
            # Preserve lecturer's custom name in username field (e.g. "Dr. Michael Asare")
            if not self.username:
                self.username = self.email or f"{self.first_name} {self.last_name}".strip()
            # If first_name is empty, use username as display name
            if not self.first_name and self.username:
                self.first_name = self.username
        else:
            # 2. Students and Course Reps HAVE index numbers
            if self.index_number:
                self.index_number = str(self.index_number).strip()
                if not self.email or '@' not in self.email:
                    self.email = f"{self.index_number}@st.uew.edu.gh"
            elif self.email and '@st.uew.edu.gh' in self.email:
                prefix = self.email.split('@')[0]
                if prefix.isdigit() and len(prefix) == 10:
                    self.index_number = prefix

            if not self.username:
                self.username = self.email or (f"{self.index_number}@st.uew.edu.gh" if self.index_number else '')

        super().save(*args, **kwargs)

    def __str__(self):
        display_name = f"{self.first_name} {self.last_name}".strip() or self.username
        if self.role == self.Role.LECTURER:
            return f"Lecturer: {display_name} ({self.email})"
        elif self.role == self.Role.REP:
            return f"Course Rep: {display_name} ({self.email})"
        return f"Student: {display_name} ({self.email})"
