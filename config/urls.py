from django.contrib import admin
from django.urls import include, path

from predictions import consts

urlpatterns = [
    path("admin/", admin.site.urls),
    path("api/", include("predictions.api_urls")),
]

# Branded admin headers (Persian).
admin.site.site_header = consts.BRAND_NAME
admin.site.site_title = consts.BRAND_NAME
admin.site.index_title = "پنل مدیریت"
