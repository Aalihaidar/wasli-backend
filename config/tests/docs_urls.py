"""A URLconf that always carries the API docs, so their tests do not depend on the
environment the test run happens to use."""

from django.contrib import admin
from django.urls import path

from config.api_docs import build_docs_urlpatterns

urlpatterns = [
    path("admin/", admin.site.urls),
    *build_docs_urlpatterns(),
]
