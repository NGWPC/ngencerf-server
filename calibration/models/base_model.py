from django.db import models


class BaseModel(models.Model):
    updated_by = models.TextField()
    updated_at = models.DateTimeField(auto_now=True)
    created_by = models.TextField()
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        abstract = True
