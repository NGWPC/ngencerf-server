from django.contrib.auth import get_user_model
from djoser.serializers import UserCreateSerializer
from rest_framework_simplejwt.serializers import TokenObtainPairSerializer

User = get_user_model()


class CustomUserSerializer(UserCreateSerializer):
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


class CustomTokenObtainPairSerializer(TokenObtainPairSerializer):

    def validate(self, attrs):
        data = super().validate(attrs)

        # Include first_name and last_name in the response
        data['first_name'] = self.user.first_name
        data['last_name'] = self.user.last_name

        return data
