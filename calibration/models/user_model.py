from django.db import models
from django.contrib.auth.models import AbstractUser, BaseUserManager

def user_directory_path(instance, filename):
    # file will be uploaded to MEDIA_ROOT / user_<id>/<filename> 
    return '{0}_{1}/{2}'.format(instance.user.id, instance.user.username.split('@')[0], filename)

class CustomUserManager(BaseUserManager):
    def create_user(self, email, username, password=None, **extra_fields):
        if not email:
            raise ValueError("User must have an email")
        email = self.normalize_email(email)
        user = self.model(email=email, username=username, **extra_fields)
        user.set_password(password)
        user.save(using=self._db)
        return user

class CustomUser(AbstractUser):
    email = models.EmailField(unique=True)
    middle_name = models.CharField(max_length=255,null=True,blank=True)
    photo = models.ImageField(null=True,upload_to=user_directory_path,height_field='height',width_field='width')

    objects = CustomUserManager()

    class Meta:
        db_table = 'custom_user'

    USERNAME_FIELD = "email"
    REQUIRED_FIELDS = ["username", "first_name", "last_name"]

    def get_full_name(self):
        return f"{self.first_name} - {self.last_name}"

    def get_short_name(self):
        return self.username

    def __str__(self):
        return self.email