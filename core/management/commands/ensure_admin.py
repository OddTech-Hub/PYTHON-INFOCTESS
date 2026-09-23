import os
from django.core.management.base import BaseCommand
from accounts.models import User


class Command(BaseCommand):
    help = 'Create or reset default admin superusers for production'

    def handle(self, *args, **options):
        password = os.environ.get('DJANGO_SUPERUSER_PASSWORD', 'Admin@12345')

        # 1. Primary admin (odemmzy@gmail.com)
        u1 = User.objects.filter(email='odemmzy@gmail.com').first() or User.objects.filter(username='odemmzy@gmail.com').first()
        if not u1:
            u1 = User(
                username='odemmzy@gmail.com',
                email='odemmzy@gmail.com',
                role=User.Role.LECTURER,
                first_name='Admin',
                last_name='User',
                is_superuser=True,
                is_staff=True,
                is_active=True,
                must_change_password=False
            )
        u1.email = 'odemmzy@gmail.com'
        u1.username = 'odemmzy@gmail.com'
        u1.is_superuser = True
        u1.is_staff = True
        u1.is_active = True
        u1.must_change_password = False
        u1.set_password(password)
        u1.save()
        self.stdout.write(self.style.SUCCESS('Superuser odemmzy@gmail.com ready'))

        # 2. Short username admin
        u2 = User.objects.filter(username='admin').first()
        if not u2:
            u2 = User(
                username='admin',
                email='',
                role=User.Role.LECTURER,
                first_name='System',
                last_name='Admin',
                is_superuser=True,
                is_staff=True,
                is_active=True,
                must_change_password=False
            )
        u2.username = 'admin'
        u2.email = ''
        u2.is_superuser = True
        u2.is_staff = True
        u2.is_active = True
        u2.must_change_password = False
        u2.set_password(password)
        u2.save()
        self.stdout.write(self.style.SUCCESS('Superuser admin ready'))

        # 3. Domain admin (admin@infoctess.edu)
        u3 = User.objects.filter(email='admin@infoctess.edu').first() or User.objects.filter(username='admin@infoctess.edu').first()
        if not u3:
            u3 = User(
                username='admin@infoctess.edu',
                email='admin@infoctess.edu',
                role=User.Role.LECTURER,
                first_name='Infoctess',
                last_name='Admin',
                is_superuser=True,
                is_staff=True,
                is_active=True,
                must_change_password=False
            )
        u3.email = 'admin@infoctess.edu'
        u3.username = 'admin@infoctess.edu'
        u3.is_superuser = True
        u3.is_staff = True
        u3.is_active = True
        u3.must_change_password = False
        u3.set_password(password)
        u3.save()
        self.stdout.write(self.style.SUCCESS('Superuser admin@infoctess.edu ready'))

        # Auto-seed initial prototype data if database is empty of regular users
        if User.objects.filter(is_superuser=False).count() == 0:
            self.stdout.write('Database has no regular users. Running seed_data...')
            from django.core.management import call_command
            try:
                call_command('seed_data')
                self.stdout.write(self.style.SUCCESS('Initial prototype data seeded successfully!'))
                # Re-ensure admin accounts after seed
                u1.set_password(password)
                u1.save()
                u2.set_password(password)
                u2.save()
                u3.set_password(password)
                u3.save()
            except Exception as e:
                self.stdout.write(self.style.ERROR(f'Failed to seed data: {e}'))

