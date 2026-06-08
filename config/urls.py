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

# Branded admin headers (Persian).
admin.site.site_header = consts.BRAND_NAME
admin.site.site_title = consts.BRAND_NAME
admin.site.index_title = "پنل مدیریت"
