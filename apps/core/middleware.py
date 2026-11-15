"""Adds a strict Content-Security-Policy and related headers."""

CSP = (
    "default-src 'self'; script-src 'self'; style-src 'self'; img-src 'self' data:; "
    "font-src 'self'; connect-src 'self'; frame-ancestors 'none'; base-uri 'self'; form-action 'self'"
)
# Swagger UI assets are served from a CDN by drf-spectacular.
DOCS_CSP = (
    "default-src 'self'; script-src 'self' 'unsafe-inline' cdn.jsdelivr.net; "
    "style-src 'self' 'unsafe-inline' cdn.jsdelivr.net; img-src 'self' data: cdn.jsdelivr.net; "
    "connect-src 'self'; frame-ancestors 'none'"
)


class SecurityHeadersMiddleware:
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        response = self.get_response(request)
        policy = DOCS_CSP if request.path.startswith("/api/docs") else CSP
        response.headers.setdefault("Content-Security-Policy", policy)
        response.headers.setdefault("Permissions-Policy", "camera=(), microphone=(), geolocation=()")
        response.headers.setdefault("Cross-Origin-Opener-Policy", "same-origin")
        return response
