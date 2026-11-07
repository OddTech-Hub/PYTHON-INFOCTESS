import traceback
from django.http import HttpResponse

class ExceptionDiagnosticMiddleware:
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        return self.get_response(request)

    def process_exception(self, request, exception):
        tb = traceback.format_exc()
        print("EXCEPTION DIAGNOSTIC:", tb)
        if request.user.is_authenticated and request.user.is_superuser:
            return HttpResponse(f"<h1>Debug Error Traceback</h1><pre>{tb}</pre>", status=500)
        return None

