from django.core.management.base import BaseCommand
from accounts.models import User

class Command(BaseCommand):
    help = 'Create or reset default admin superuser'

    def handle(self, *args, **options):
        email = 'admin@infoctess.edu'
        password = 'password123'
        
        user = User.objects.filter(email=email).first() or User.objects.filter(username=email).first()
        if not user:
            user = User(
                username=email,
                email=email,
                role=User.Role.LECTURER,
                first_name='Admin',
                last_name='User',
                is_superuser=True,
                is_staff=True,
                is_active=True,
                must_change_password=False
            )
            user.set_password(password)
            user.save()
            self.stdout.write(self.style.SUCCESS(f'Successfully created superuser {email}'))
        else:
            user.set_password(password)
            user.is_superuser = True
            user.is_staff = True
            user.is_active = True
            user.must_change_password = False
            user.save()
            self.stdout.write(self.style.SUCCESS(f'Successfully updated superuser {email} password'))
