"""The interactive API docs (Swagger UI) and the live schema, for staff outside production.

The committed ``openapi/schema.yaml`` is the contract. These two routes show the same schema
from the running app so it can be read and tried in a browser:

* ``/api/docs/``: Swagger UI, bundled with the app (``drf-spectacular-sidecar``), nothing is
  loaded from a CDN, so it also works under a strict Content Security Policy.
* ``/api/schema/``: the schema itself (YAML, or JSON with
  ``Accept: application/vnd.oai.openapi+json``).

They exist only when ``ENVIRONMENT`` is ``local`` or ``staging``, and only for staff accounts
signed in through the Django admin. Anyone else, signed in or not, gets a plain 404: a redirect
to the admin sign-in would tell every visitor where the admin is. Production never serves them;
its schema is the ``openapi.yaml`` attached to each release.
"""

from collections.abc import Callable
from functools import wraps

from django.conf import settings
from django.http import Http404, HttpRequest, HttpResponse
from django.urls import URLPattern, path
from django.views.decorators.cache import never_cache
from drf_spectacular.views import SpectacularAPIView, SpectacularSwaggerView
from rest_framework.permissions import AllowAny

SCHEMA_URL_NAME = "api-schema"
DOCS_ENVIRONMENTS = frozenset({"local", "staging"})


class StaffSchemaView(SpectacularAPIView):
    """The schema. Access is decided by the staff check around the view, not by DRF."""

    authentication_classes = ()
    permission_classes = (AllowAny,)


class StaffSwaggerView(SpectacularSwaggerView):
    """Swagger UI. Access is decided by the staff check around the view, not by DRF."""

    authentication_classes = ()
    permission_classes = (AllowAny,)


def staff_or_404(
    view: Callable[..., HttpResponse],
) -> Callable[..., HttpResponse]:
    """Let an active staff account through; for everyone else the page does not exist."""

    @wraps(view)
    def wrapper(request: HttpRequest, *args: object, **kwargs: object) -> HttpResponse:
        user = request.user
        if not (user.is_active and user.is_staff):
            raise Http404
        return view(request, *args, **kwargs)

    return wrapper


def docs_enabled() -> bool:
    """True on local and staging only. Any other value, production included, serves nothing."""
    return bool(settings.ENVIRONMENT in DOCS_ENVIRONMENTS)


def build_docs_urlpatterns() -> list[URLPattern]:
    """The two routes, whatever the environment. Never cached by a browser or a proxy."""
    return [
        path(
            "api/schema/",
            never_cache(staff_or_404(StaffSchemaView.as_view())),
            name=SCHEMA_URL_NAME,
        ),
        path(
            "api/docs/",
            never_cache(
                staff_or_404(StaffSwaggerView.as_view(url_name=SCHEMA_URL_NAME))
            ),
            name="api-docs",
        ),
    ]


def docs_urlpatterns() -> list[URLPattern]:
    """The two routes on local and staging, none anywhere else."""
    return build_docs_urlpatterns() if docs_enabled() else []
