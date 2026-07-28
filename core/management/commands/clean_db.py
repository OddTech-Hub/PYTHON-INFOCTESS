from django.core.management.base import BaseCommand
from accounts.models import User
from core.models import AcademicPeriod, Level
from courses.models import Course, StudentGroup, CourseRep, LecturerCourse
from attendance.models import AttendanceSession, AttendanceRecord, DeviceAlert


class Command(BaseCommand):
    help = 'Clears all transactional seed data, students, reps, and sessions, keeping structural levels and lecturer accounts.'

    def handle(self, *args, **options):
        self.stdout.write('Clearing transactional data...')
        
        # Delete attendance records and sessions
        AttendanceRecord.objects.all().delete()
        AttendanceSession.objects.all().delete()
        DeviceAlert.objects.all().delete()
        
        # Delete rep assignments and lecturer course linkages
        CourseRep.objects.all().delete()
        LecturerCourse.objects.all().delete()
        
        # Delete courses and student groups
        Course.objects.all().delete()
        StudentGroup.objects.all().delete()
        
        # Delete student/rep users, keeping lecturers and superusers
        deleted_count, _ = User.objects.filter(role__in=[User.Role.STUDENT, User.Role.REP]).delete()
        self.stdout.write(f'Deleted {deleted_count} student/rep users.')

        # Ensure active academic period exists
        period = AcademicPeriod.objects.filter(is_active=True).first()
        if not period:
            period = AcademicPeriod.objects.create(
                name="2025/2026 Academic Year — Semester 2",
                is_active=True
            )
            self.stdout.write('Created active Academic Period.')

        # Ensure academic levels exist
        levels_data = [
            {'code': 'L100', 'year': '1st Year', 'label': 'Level 100', 'color': '#3b82f6', 'bg': '#eff6ff', 'border': '#bfdbfe'},
            {'code': 'L200', 'year': '2nd Year', 'label': 'Level 200', 'color': '#10b981', 'bg': '#ecfdf5', 'border': '#a7f3d0'},
            {'code': 'L300', 'year': '3rd Year', 'label': 'Level 300', 'color': '#8b5cf6', 'bg': '#f5f3ff', 'border': '#ddd6fe'},
            {'code': 'L400', 'year': '4th Year', 'label': 'Level 400', 'color': '#f59e0b', 'bg': '#fffbeb', 'border': '#fde68a'},
        ]
        for lvl in levels_data:
            Level.objects.get_or_create(
                code=lvl['code'],
                defaults={
                    'label': lvl['label'],
                    'year': lvl['year'],
                    'color': lvl['color'],
                    'bg': lvl['bg'],
                    'border': lvl['border']
                }
            )

        # Ensure lecturer accounts exist
        lecturers = [
            {'email': 'danso@uew.edu.gh', 'first_name': 'Dr.', 'last_name': 'Danso'},
            {'email': 'lecturer@infoctess.edu', 'first_name': 'Isaac', 'last_name': 'Koomson'},
        ]
        for lec in lecturers:
            u, created = User.objects.get_or_create(
                username=lec['email'],
                email=lec['email'],
                defaults={
                    'first_name': lec['first_name'],
                    'last_name': lec['last_name'],
                    'role': User.Role.LECTURER
                }
            )
            u.set_password('password123')
            u.save()

        # Ensure admin superuser exists
        admin_user = User.objects.filter(is_superuser=True).first()
        if not admin_user:
            User.objects.create_superuser('admin@infoctess.edu', 'admin@infoctess.edu', 'admin123', first_name='System', last_name='Admin')
            self.stdout.write('Created superuser admin@infoctess.edu.')
        else:
            admin_user.set_password('admin123')
            admin_user.save()

        self.stdout.write(self.style.SUCCESS('Database successfully reset to a clean slate!'))
