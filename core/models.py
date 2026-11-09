import uuid

from django.db import models


class BaseModel(models.Model):
    """Fields every Wasli table carries: a UUID primary key and UTC timestamps.

    ``users.User`` defines the same three fields itself so that ``users`` does not depend on
    ``core``; every other app's models inherit from this class.
    """

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        abstract = True
