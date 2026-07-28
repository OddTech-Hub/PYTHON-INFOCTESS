import re
from django.contrib import admin
from django.urls import path, include
from django.shortcuts import redirect
from django.contrib.auth import logout
from django.conf import settings


def get_frontend_url(request):
    """
    Dynamically determine the frontend landing page URL.
    Checks HTTP_REFERER and HTTP_ORIGIN for any active frontend port on localhost (e.g. 8085, 5173, 3000, 5174),
    otherwise defaults to settings.FRONTEND_URL (http://localhost:8085).
    """
    referer = request.META.get('HTTP_REFERER', '') or request.META.get('HTTP_ORIGIN', '')
    target = getattr(settings, 'FRONTEND_URL', 'http://localhost:5173')
    
    if referer and ('localhost:' in referer or '127.0.0.1:' in referer):
        match = re.search(r'(https?://(?:localhost|127\.0\.0\.1):\d+)', referer)
        if match:
            origin = match.group(1)
            # Avoid redirecting back to django server itself on port 8000
            if not origin.endswith(':8000'):
                target = origin
                
    return target


def redirect_to_frontend(request):
    """View to redirect root / or View Site clicks to the frontend landing page."""
    target = get_frontend_url(request)
    return redirect(target)


def custom_admin_logout(request):
    """View to log out admin user and redirect to the frontend landing page."""
    logout(request)
    target = get_frontend_url(request)
    return redirect(target)


# Override Django Admin's default logout view directly
admin.site.logout = custom_admin_logout

# Set "View site" link in Django Admin header to '/' (triggers redirect_to_frontend)
admin.site.site_url = '/'

urlpatterns = [
    path('', redirect_to_frontend, name='landing'),
    path('admin/logout/', custom_admin_logout, name='admin_logout'),
    path('admin/', admin.site.urls),
    path('api/auth/', include('accounts.urls')),
    path('api/', include('courses.urls')),
    path('api/', include('attendance.urls')),
    path('api/reports/', include('reports.urls')),
]


