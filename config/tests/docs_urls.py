"""A URLconf that always carries the API docs, so their tests do not depend on the
environment the test run happens to use."""

from django.contrib import admin
from django.urls import include, path

from config.api_docs import build_docs_urlpatterns

urlpatterns = [
    path("admin/", admin.site.urls),
    path("api/v1/", include("config.api_urls")),
    *build_docs_urlpatterns(),
]
