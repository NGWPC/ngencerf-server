from django.db import models

from django_currentuser.db.models import CurrentUserField


class BaseModel(models.Model):
    updated_by = CurrentUserField(on_update=True, related_name='+', on_delete=models.RESTRICT, db_column='updated_by')
    updated_at = models.DateTimeField(auto_now=True)
    created_by = CurrentUserField(related_name='+', on_delete=models.RESTRICT, db_column='created_by')
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        abstract = True
