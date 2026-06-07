from rest_framework import authentication, exceptions

from . import clerk


class ClerkAuthentication(authentication.BaseAuthentication):
    """
    DRF authentication using a Clerk session JWT in the Authorization header.

    The Next.js frontend obtains the token from Clerk and sends it as
    `Authorization: Bearer <token>`. We verify it against Clerk's JWKS and map
    it to (creating if needed) a local Django user.
    """

    keyword = "Bearer"

    def authenticate(self, request):
        header = request.headers.get("Authorization", "")
        if not header.startswith(self.keyword + " "):
            return None  # let other authenticators / AnonymousUser handle it

        token = header[len(self.keyword) + 1:].strip()
        try:
            claims = clerk.verify_session_token(token)
            user = clerk.get_or_create_user(claims)
        except clerk.ClerkError:
            raise exceptions.AuthenticationFailed("توکن نامعتبر است.")
        return (user, token)

    def authenticate_header(self, request):
        return self.keyword
