import random
from datetime import datetime, timedelta
from django.core.management.base import BaseCommand
from django.utils import timezone
from django.contrib.auth.hashers import make_password

from accounts.models import User
from core.models import AcademicPeriod, Level
from courses.models import Course, StudentGroup, CourseRep, LecturerCourse
from attendance.models import AttendanceSession, AttendanceRecord, DeviceAlert


class Command(BaseCommand):
    help = 'Seeds database with realistic prototype data'

    def handle(self, *args, **options):
        self.stdout.write('Deleting existing data...')
        AttendanceRecord.objects.all().delete()
        AttendanceSession.objects.all().delete()
        DeviceAlert.objects.all().delete()
        CourseRep.objects.all().delete()
        LecturerCourse.objects.all().delete()
        Course.objects.all().delete()
        StudentGroup.objects.all().delete()
        User.objects.filter(is_superuser=False).delete()
        Level.objects.all().delete()
        AcademicPeriod.objects.all().delete()

        self.stdout.write('Creating Academic Period...')
        period = AcademicPeriod.objects.create(
            name="2025/2026 Academic Year — Semester 2",
            is_active=True
        )

        self.stdout.write('Creating Levels...')
        levels = {
            'L100': Level.objects.create(code='L100', label='Level 100', year='1st Year', color='#3b82f6', bg='#eff6ff', border='#bfdbfe'),
            'L200': Level.objects.create(code='L200', label='Level 200', year='2nd Year', color='#10b981', bg='#ecfdf5', border='#a7f3d0'),
            'L300': Level.objects.create(code='L300', label='Level 300', year='3rd Year', color='#8b5cf6', bg='#f5f3ff', border='#ddd6fe'),
            'L400': Level.objects.create(code='L400', label='Level 400', year='4th Year', color='#f59e0b', bg='#fffbeb', border='#fde68a'),
        }

        self.stdout.write('Creating Student Groups...')
        groups = {
            'L100_G1': StudentGroup.objects.create(name='Group 1', level=levels['L100'], academic_period=period),
            'L100_G2': StudentGroup.objects.create(name='Group 2', level=levels['L100'], academic_period=period),
            'L200_G1': StudentGroup.objects.create(name='Group 1', level=levels['L200'], academic_period=period),
            'L200_G2': StudentGroup.objects.create(name='Group 2', level=levels['L200'], academic_period=period),
            'L200_G3': StudentGroup.objects.create(name='Group 3', level=levels['L200'], academic_period=period),
            'L300_G1': StudentGroup.objects.create(name='Group 1', level=levels['L300'], academic_period=period),
            'L300_G2': StudentGroup.objects.create(name='Group 2', level=levels['L300'], academic_period=period),
            'L400_G1': StudentGroup.objects.create(name='Group 1', level=levels['L400'], academic_period=period),
        }

        self.stdout.write('Creating Courses...')
        courses = [
            Course.objects.create(code='ICTE125', name='Multimedia Authoring in Education', level=levels['L100'], academic_period=period),
            Course.objects.create(code='ICTW123', name='Fundamentals of Computer Programming', level=levels['L100'], academic_period=period),
            Course.objects.create(code='ICTS201', name='Systems Analysis and Design', level=levels['L200'], academic_period=period),
            Course.objects.create(code='ICTD310', name='Database Management Systems', level=levels['L300'], academic_period=period),
        ]

        self.stdout.write('Creating Users (Lecturers, Reps, Students)...')
        
        # 1. Main Lecturers
        lecturer = User.objects.create_user(
            username='lecturer@infoctess.edu',
            email='lecturer@infoctess.edu',
            password='password123',
            first_name='Isaac',
            last_name='Koomson',
            role=User.Role.LECTURER
        )
        for c in courses:
            LecturerCourse.objects.create(lecturer=lecturer, course=c, academic_period=period)

        # 1b. Dr. Danso Lecturer
        lecturer_danso = User.objects.create_user(
            username='danso@uew.edu.gh',
            email='danso@uew.edu.gh',
            password='password123',
            first_name='Dr.',
            last_name='Danso',
            role=User.Role.LECTURER
        )

        # Ensure Admin superuser password is set to Admin@12345
        admin_user = User.objects.filter(is_superuser=True).first()
        if not admin_user:
            admin_user = User.objects.create_superuser('admin@infoctess.edu', 'admin@infoctess.edu', 'Admin@12345', first_name='System', last_name='Admin')
        else:
            admin_user.set_password('Admin@12345')
            admin_user.save()

        # 2. Students & Reps Data Mapping
        students_data = [
            # Level 100
            { "name": "Alberta Klokpa",   "index": "5261000018", "group": "L100_G1", "level": "L100", "device_name": "iPhone 13", "device_id": "dev-001", "role": User.Role.REP },
            { "name": "Daniel Amoh",      "index": "5261000667", "group": "L100_G1", "level": "L100", "device_name": "Samsung S21", "device_id": "dev-002" },
            { "name": "Emmanuel Oduro",   "index": "5261000215", "group": "L100_G2", "level": "L100", "device_name": "Pixel 7", "device_id": "dev-003" },
            { "name": "Emmanuel Twumasi", "index": "5261000267", "group": "L100_G2", "level": "L100", "device_name": "Multiple (2)", "device_id": None, "alert": { "type": "multi_device", "reason": "Logged in from 2 devices: iPhone 12 & Samsung A52" } },
            { "name": "Heis Boateng",     "index": "5261000323", "group": "L100_G1", "level": "L100", "device_name": "iPhone 12", "device_id": "dev-005", "role": User.Role.REP },
            { "name": "Nimako Joe",       "index": "5261000334", "group": "L100_G2", "level": "L100", "device_name": "Changed device", "device_id": None, "alert": { "type": "device_change", "reason": "Device changed: Tecno Spark → Infinix Hot 20" } },
            { "name": "Osie Eugen Bonu",  "index": "5261000660", "group": "L100_G1", "level": "L100", "device_name": "Tecno Spark", "device_id": "dev-007" },
            { "name": "Sandra Mensah",    "index": "5261000712", "group": "L100_G2", "level": "L100", "device_name": "iPhone SE", "device_id": "dev-008" },
            
            # Level 200
            { "name": "Ama Boateng",      "index": "5251000011", "group": "L200_G1", "level": "L200", "device_name": "Samsung A53", "device_id": "dev-009" },
            { "name": "Kofi Mensah",      "index": "5251000022", "group": "L200_G1", "level": "L200", "device_name": "iPhone 14", "device_id": "dev-010" },
            { "name": "Abena Osei",       "index": "5251000033", "group": "L200_G2", "level": "L200", "device_name": "Multiple (3)", "device_id": None, "alert": { "type": "multi_device", "reason": "Signed in from 3 different devices this semester" } },
            { "name": "Kweku Asante",     "index": "5251000044", "group": "L200_G2", "level": "L200", "device_name": "Pixel 6", "device_id": "dev-012" },
            { "name": "Adwoa Darko",      "index": "5251000055", "group": "L200_G3", "level": "L200", "device_name": "Tecno Spark", "device_id": "dev-013" },

            # Level 300
            { "name": "Yaw Frempong",     "index": "5241000001", "group": "L300_G1", "level": "L300", "device_name": "iPhone 13 Pro", "device_id": "dev-014" },
            { "name": "Akosua Ampah",     "index": "5241000002", "group": "L300_G1", "level": "L300", "device_name": "Changed device", "device_id": None, "alert": { "type": "device_change", "reason": "Phone changed mid-semester: Huawei P30 → Samsung S22" } },
            { "name": "Kwame Ofori",      "index": "5241000003", "group": "L300_G2", "level": "L300", "device_name": "Pixel 7 Pro", "device_id": "dev-016" },
            { "name": "Efua Asiedu",      "index": "5241000004", "group": "L300_G2", "level": "L300", "device_name": "Multiple (2)", "device_id": None, "alert": { "type": "multi_device", "reason": "Two devices detected in same session: iPhone 11 & Oppo A57" } },

            # Level 400
            { "name": "Nana Ama Sarpong", "index": "5231000010", "group": "L400_G1", "level": "L400", "device_name": "Samsung S23", "device_id": "dev-018" },
            { "name": "Fiifi Entsie",     "index": "5231000011", "group": "L400_G1", "level": "L400", "device_name": "iPhone 15 Pro", "device_id": "dev-019" },
            { "name": "Maame Serwaa",     "index": "5231000012", "group": "L400_G1", "level": "L400", "device_name": "Multiple (2)", "device_id": None, "alert": { "type": "multi_device", "reason": "Checked in using 2 phones: own device + borrowed device detected" } },
        ]

        seeded_users = {}
        for s in students_data:
            first, last = s["name"].split(" ", 1)
            role = s.get("role", User.Role.STUDENT)
            
            u = User.objects.create_user(
                username=s["index"],
                email=f"{s['index']}@st.uew.edu.gh",
                password='password123',
                first_name=first,
                last_name=last,
                index_number=s["index"],
                role=role,
                device_name=s["device_name"],
                device_id=s["device_id"],
                group=groups[s["group"]]
            )
            u.save()
            seeded_users[s["index"]] = u

            if role == User.Role.REP:
                CourseRep.objects.create(student=u, group=groups[s["group"]], academic_period=period)

            if "alert" in s:
                DeviceAlert.objects.create(
                    student=u,
                    alert_type=s["alert"]["type"],
                    reason=s["alert"]["reason"],
                    status='open'
                )

        self.stdout.write('Seeding Sessions and Records for Level 100...')
        
        # 1. Closed session ATT-4869
        s1 = AttendanceSession.objects.create(
            session_code="ATT-4869",
            course=courses[0],
            group=groups['L100_G1'],
            opened_at=timezone.now() - timedelta(days=2),
            closed_at=timezone.now() - timedelta(days=2, hours=-1),
            time_window_minutes=10,
            status='closed',
            created_by=lecturer
        )
        AttendanceRecord.objects.create(session=s1, student=seeded_users["5261000018"], method='qr_code')
        AttendanceRecord.objects.create(session=s1, student=seeded_users["5261000215"], method='code')

        # 2. Closed session ATT-6162
        s2 = AttendanceSession.objects.create(
            session_code="ATT-6162",
            course=courses[1],
            group=groups['L100_G1'],
            opened_at=timezone.now() - timedelta(days=1),
            closed_at=timezone.now() - timedelta(days=1, hours=-1),
            time_window_minutes=10,
            status='closed',
            created_by=lecturer
        )
        AttendanceRecord.objects.create(session=s2, student=seeded_users["5261000712"], method='qr_code')

        # 3. Closed session ATT-6656
        s3 = AttendanceSession.objects.create(
            session_code="ATT-6656",
            course=courses[1],
            group=groups['L100_G2'],
            opened_at=timezone.now() - timedelta(hours=5),
            closed_at=timezone.now() - timedelta(hours=4),
            time_window_minutes=15,
            status='closed',
            created_by=lecturer
        )
        AttendanceRecord.objects.create(session=s3, student=seeded_users["5261000334"], method='code')
        AttendanceRecord.objects.create(session=s3, student=seeded_users["5261000323"], method='qr_code')

        self.stdout.write(self.style.SUCCESS('Successfully seeded database with prototype dataset!'))
