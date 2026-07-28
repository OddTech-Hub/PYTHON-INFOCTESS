from accounts.models import User
from .models import CourseRep, StudentGroup


def get_user_rep_group_ids(user):
    """
    Returns a list of group_ids that a Course Rep or Student is assigned to.
    Returns None if the user is a Lecturer or Admin (unrestricted access).
    """
    if not user or not user.is_authenticated:
        return []

    # Lecturers and Admins have unrestricted access
    if user.is_superuser or user.role == User.Role.LECTURER:
        return None

    # For Course Reps and Students:
    group_ids = set()

    # 1. Check CourseRep model assignments
    assignments = CourseRep.objects.filter(student=user)
    for rep in assignments:
        if rep.group_id:
            group_ids.add(rep.group_id)

    # 2. Check direct user.group foreign key
    if user.group_id:
        group_ids.add(user.group_id)

    return list(group_ids)
