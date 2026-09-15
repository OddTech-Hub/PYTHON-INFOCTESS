from rest_framework import serializers
from .models import User


class UserSerializer(serializers.ModelSerializer):
    level_code = serializers.SerializerMethodField()
    level_label = serializers.SerializerMethodField()
    group_name = serializers.SerializerMethodField()

    class Meta:
        model = User
        fields = [
            'id', 'username', 'first_name', 'last_name',
            'email', 'role', 'index_number', 'device_id', 'device_name',
            'group', 'group_name', 'level_code', 'level_label', 'must_change_password'
        ]
        read_only_fields = ['id', 'username', 'role']

    def get_level_code(self, obj):
        if obj.group and obj.group.level:
            return obj.group.level.code
        return None

    def get_level_label(self, obj):
        if obj.group and obj.group.level:
            return obj.group.level.label
        return None

    def get_group_name(self, obj):
        if obj.group:
            return obj.group.name
        return None
