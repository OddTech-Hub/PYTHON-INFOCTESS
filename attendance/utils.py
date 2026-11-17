import math
import re
import time
from django.db import transaction
from accounts.models import User

WINDOW_SECONDS = 90


def _imul32(a, b):
    """Emulate 32-bit signed integer multiplication matching JavaScript Math.imul."""
    res = ((a & 0xFFFFFFFF) * (b & 0xFFFFFFFF)) & 0xFFFFFFFF
    return res - 0x100000000 if (res & 0x80000000) else res


def _u32(val):
    return val & 0xFFFFFFFF


def hash_slot(seed: str, slot: int) -> str:
    """
    Deterministic 90-second Murmur3 + FNV-1a 4-digit passcode generator.
    Matches frontend src/utils/sessionCode.js bit-for-bit.
    """
    clean_seed = (seed or 'INFOCTESS_SECURE_SALT').upper()
    reversed_seed = clean_seed[::-1]
    mul_part = _u32(_imul32(slot, 2654435761))
    xor_part = slot ^ 0x5BF03635
    payload = f"{clean_seed}:#{mul_part}!{reversed_seed}:@{xor_part}"

    h = 0x811C9DC5
    for ch in payload:
        h ^= ord(ch)
        h = _imul32(h, 0x01000193)

    u = _u32(h)
    u ^= (u >> 16)
    u = _u32(_imul32(u, 0x85EBCA6B))
    u ^= (u >> 13)
    u = _u32(_imul32(u, 0xC2B2AE35))
    u ^= (u >> 16)

    code = (u % 9000) + 1000
    return str(code)


def extract_submitted_code(raw_input: str) -> str:
    """Extracts uppercase ATT-XXXX code or 4 digits from raw input or QR payload."""
    if not raw_input:
        return ''
    s = str(raw_input).strip()
    if 'infoctess://session/' in s.lower():
        after = s.split('session/', 1)[-1]
        s = after.split('?', 1)[0].strip()
    elif '/' in s:
        s = s.split('/')[-1].split('?', 1)[0].strip()
    s = s.upper()
    m = re.search(r'(ATT-[0-9A-Z]{4,8})', s)
    if m:
        return m.group(1)
    if re.fullmatch(r'\d{4}', s):
        return f"ATT-{s}"
    return s


def validate_rotating_code(submitted_code: str, base_session_code: str, now_ts: int | None = None) -> bool:
    """
    Validates a submitted code strictly against the active session's live
    90-second rotating ATT-XXXX code (current window + 1 previous window grace period).
    """
    clean_sub = extract_submitted_code(submitted_code)
    if not clean_sub or not base_session_code:
        return False

    now = int(now_ts if now_ts is not None else time.time())
    current_slot = now // WINDOW_SECONDS
    prev_slot = current_slot - 1

    cur_digits = hash_slot(base_session_code, current_slot)
    prev_digits = hash_slot(base_session_code, prev_slot)

    valid_options = {
        f"ATT-{cur_digits}",
        f"ATT-{prev_digits}",
        cur_digits,
        prev_digits,
        f"ATT {cur_digits}",
        f"ATT {prev_digits}",
    }
    return clean_sub in valid_options


def haversine_meters(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """Returns great-circle distance in meters between two WGS84 coordinates."""
    r = 6371000.0
    phi1 = math.radians(lat1)
    phi2 = math.radians(lat2)
    dphi = math.radians(lat2 - lat1)
    dlambda = math.radians(lon2 - lon1)
    a = math.sin(dphi / 2.0) ** 2 + math.cos(phi1) * math.cos(phi2) * math.sin(dlambda / 2.0) ** 2
    return 2.0 * r * math.atan2(math.sqrt(a), math.sqrt(1.0 - a))


def get_session_host_info(session) -> tuple[str, str]:
    """Returns (display_label, role_label) for the user who created an AttendanceSession."""
    creator = getattr(session, 'created_by', None)
    if not creator:
        return ("Assigned Lecturer", "Lecturer")
    full_name = f"{creator.first_name} {creator.last_name}".strip() or creator.email or creator.username
    role_label = "Course Rep" if creator.role == User.Role.REP else "Lecturer"
    return (f"{full_name} ({role_label})", role_label)


def _format_group_tag(group_obj) -> str:
    if not group_obj or not getattr(group_obj, 'name', None):
        return ""
    raw_name = str(group_obj.name).strip()
    if ' - ' in raw_name:
        raw_name = raw_name.split('-', 1)[-1].strip()
    m = re.search(r'(\d+)\s*$', raw_name)
    if m and 'group' in raw_name.lower():
        return f"-GP{m.group(1)}"
    compact = re.sub(r'\s+', '', raw_name).upper()
    compact = compact.replace('GROUP', 'GP')
    return f"-{compact}" if compact else ""


def assign_next_receipt_code(session, student) -> str:
    """
    Atomically computes the next 4-digit sequential receipt code for a session
    (e.g. ATT-0001-GP1) using a row lock on AttendanceSession so concurrent check-ins
    never produce duplicate sequence numbers.
    """
    from .models import AttendanceSession, AttendanceRecord

    with transaction.atomic():
        locked_session = AttendanceSession.objects.select_for_update().select_related('group').get(pk=session.pk)
        existing_codes = list(
            AttendanceRecord.objects.filter(
                session=locked_session,
                status='confirmed',
                receipt_code__isnull=False
            ).values_list('receipt_code', flat=True)
        )
        max_seq = len(existing_codes)
        for code in existing_codes:
            m = re.match(r'^ATT-(\d+)', str(code).upper())
            if m:
                max_seq = max(max_seq, int(m.group(1)))

        next_seq = max_seq + 1
        target_group = locked_session.group or getattr(student, 'group', None)
        group_tag = _format_group_tag(target_group)
        return f"ATT-{next_seq:04d}{group_tag}"
