from django.conf import settings
from django.conf.urls.static import static
from django.contrib import admin
from django.urls import include, path

from predictions import consts

urlpatterns = [
    path("admin/", admin.site.urls),
    path("api/", include("predictions.api_urls")),
]

# In production avatars live in Supabase Storage (absolute URLs); in local dev
# they sit under MEDIA_ROOT and Django serves them here.
if settings.DEBUG:
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)

# The Unfold theme owns the site header/title via settings.UNFOLD (its
# AdminSite.each_context overrides admin.site.site_header/site_title). The
# index-page heading has no UNFOLD equivalent, so it's set here.
admin.site.index_title = consts.ADMIN_INDEX_TITLE
