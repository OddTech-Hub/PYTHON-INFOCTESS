from rest_framework import serializers
from .models import User


class UserSerializer(serializers.ModelSerializer):
    level_code = serializers.SerializerMethodField()
    level_label = serializers.SerializerMethodField()
    group_name = serializers.SerializerMethodField()
    group_display_name = serializers.SerializerMethodField()
    lecturer_name = serializers.SerializerMethodField()
    academic_period = serializers.SerializerMethodField()
    enrolled_groups = serializers.SerializerMethodField()

    class Meta:
        model = User
        fields = [
            'id', 'username', 'first_name', 'last_name',
            'email', 'role', 'index_number', 'device_id', 'device_name',
            'group', 'group_name', 'group_display_name',
            'level_code', 'level_label', 'lecturer_name', 'academic_period',
            'enrolled_groups', 'must_change_password'
        ]
        read_only_fields = ['id', 'username', 'role']

    def _primary_group(self, obj):
        if obj.group:
            return obj.group
        return obj.enrolled_groups.select_related('course', 'level', 'lecturer', 'academic_period').first()

    def get_level_code(self, obj):
        grp = self._primary_group(obj)
        if grp and grp.level:
            return grp.level.code
        return None

    def get_level_label(self, obj):
        grp = self._primary_group(obj)
        if grp and grp.level:
            return grp.level.label
        return None

    def get_group_name(self, obj):
        grp = self._primary_group(obj)
        if grp:
            return grp.name
        return None

    def get_group_display_name(self, obj):
        grp = self._primary_group(obj)
        if grp:
            return str(grp)
        return None

    def get_lecturer_name(self, obj):
        grp = self._primary_group(obj)
        if grp and grp.lecturer:
            full = f"{grp.lecturer.first_name} {grp.lecturer.last_name}".strip()
            return full or grp.lecturer.email or grp.lecturer.username
        return None

    def get_academic_period(self, obj):
        grp = self._primary_group(obj)
        if grp and grp.academic_period:
            return grp.academic_period.name
        return None

    def get_enrolled_groups(self, obj):
        seen = {}
        groups_to_include = []
        if obj.group:
            groups_to_include.append(obj.group)
        for g in obj.enrolled_groups.select_related('course', 'level', 'lecturer', 'academic_period').all():
            groups_to_include.append(g)

        for g in groups_to_include:
            if g.id in seen:
                continue
            lec_name = None
            if g.lecturer:
                lec_name = f"{g.lecturer.first_name} {g.lecturer.last_name}".strip() or g.lecturer.email or g.lecturer.username
            seen[g.id] = {
                'id': g.id,
                'name': g.name,
                'display_name': str(g),
                'course_code': g.course.code if g.course else None,
                'course_name': g.course.name if g.course else None,
                'level_code': g.level.code if g.level else None,
                'level_label': g.level.label if g.level else None,
                'lecturer_name': lec_name,
            }
        return list(seen.values())
