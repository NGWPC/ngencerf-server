from djoser.serializers import UserCreateSerializer, ValidationError
from django.contrib.auth import get_user_model

User = get_user_model()

class UserCreateSerializer(UserCreateSerializer):
    class Meta(UserCreateSerializer.Meta):
        model = User
        fields = ("id", "email", "first_name", "last_name", "password")
        extra_kwargs = {'password': {'write_only': True}}

    def create(self, validated_data):
        # Automatically set username to email
        validated_data['username'] = validated_data['email']

        # Call the base implementation of create to ensure password hashing and other logic is applied
        user = super().create(validated_data)

        return user