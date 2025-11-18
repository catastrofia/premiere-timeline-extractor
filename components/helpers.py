def tc_to_seconds(tc):
    """Converts HH:MM:SS timecode string to seconds."""
    if not tc: return 0
    parts = tc.split(':')
    if len(parts) != 3: return 0
    try:
        h, m, s = map(int, parts)
        return h * 3600 + m * 60 + s
    except (ValueError, TypeError):
        return 0

def tc_from_seconds(s):
    """Converts seconds to HH:MM:SS timecode string."""
    s_round = int(round(s))
    if s_round < 0:
        sign='-'; s_abs = -s_round
    else:
        sign=''; s_abs = s_round
    hh = s_abs // 3600
    mm = (s_abs % 3600) // 60
    ss = s_abs % 60
    return f"{sign}{hh:02d}:{mm:02d}:{ss:02d}"