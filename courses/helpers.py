from django.db import models
from accounts.models import User
from .models import CourseRep, StudentGroup


def get_user_rep_assignments(user):
    """Returns CourseRep queryset for an authenticated Course Rep."""
    if not user or not user.is_authenticated or user.role != User.Role.REP:
        return CourseRep.objects.none()
    return CourseRep.objects.filter(student=user).select_related('course', 'group', 'group__level', 'group__course')


def get_user_rep_course_ids(user):
    """Returns list of course IDs a Course Rep is explicitly assigned to."""
    assignments = get_user_rep_assignments(user)
    course_ids = set()
    for rep in assignments:
        if rep.course_id:
            course_ids.add(rep.course_id)
        elif rep.group and rep.group.course_id:
            course_ids.add(rep.group.course_id)
    return list(course_ids)


def get_rep_scope_q(user, course_field='course_id', group_field='group_id'):
    """
    Returns a strict Q object pairing (course_id, group_id) for each CourseRep
    assignment so a Course Rep ONLY accesses their exact assigned course + group.
    """
    assignments = get_user_rep_assignments(user)
    combined_q = models.Q()
    has_scope = False
    for rep in assignments:
        eff_course_id = rep.course_id or (rep.group.course_id if rep.group else None)
        if eff_course_id and rep.group_id:
            combined_q |= models.Q(**{course_field: eff_course_id, group_field: rep.group_id})
            has_scope = True
        elif rep.group_id:
            combined_q |= models.Q(**{group_field: rep.group_id})
            has_scope = True
        elif eff_course_id:
            combined_q |= models.Q(**{course_field: eff_course_id})
            has_scope = True

    return combined_q if has_scope else models.Q(pk__in=[])


def get_user_rep_group_ids(user):
    """
    Returns a list of group_ids that a Course Rep or Student is assigned to.
    Returns None if the user is a Lecturer or Admin (unrestricted access).
    For Course Reps, strictly uses CourseRep assignments so unrelated enrollment
    groups from other courses are never leaked.
    """
    if not user or not user.is_authenticated:
        return []

    # Lecturers and Admins have unrestricted access
    if user.is_superuser or user.role == User.Role.LECTURER:
        return None

    # Course Reps are strictly scoped to their CourseRep assignments only
    if user.role == User.Role.REP:
        return list(
            CourseRep.objects.filter(student=user, group__isnull=False)
            .values_list('group_id', flat=True)
            .distinct()
        )

    # For regular Students:
    group_ids = set()
    if user.group_id:
        group_ids.add(user.group_id)
    group_ids.update(user.enrolled_groups.values_list('id', flat=True))
    return list(group_ids)
