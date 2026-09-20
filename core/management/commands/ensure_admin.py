from django.core.management.base import BaseCommand
from accounts.models import User

class Command(BaseCommand):
    help = 'Create or reset default admin superuser'

    def handle(self, *args, **options):
        email = 'admin@infoctess.edu'
        password = 'password123'
        
        user = User.objects.filter(email=email).first() or User.objects.filter(username=email).first()
        if not user:
            user = User.objects.create_superuser(
                username=email,
                email=email,
                password=password,
                role=User.Role.LECTURER,
                first_name='Admin',
                last_name='User'
            )
            self.stdout.write(self.style.SUCCESS(f'Successfully created superuser {email}'))
        else:
            user.set_password(password)
            user.is_superuser = True
            user.is_staff = True
            user.save()
            self.stdout.write(self.style.SUCCESS(f'Successfully updated superuser {email} password'))
