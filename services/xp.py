def xp_required_for_level(level: int) -> int:
    """
    فرمول v1: تصاعدی ملایم
    lvl1: 100
    lvl2: 150
    lvl3: 225
    ...
    """
    if level <= 1:
        return 100
    base = 100
    mult = 1.5
    return int(base * (mult ** (level - 1)))


def apply_xp(level: int, xp: int, gained: int) -> tuple[int, int, bool]:
    """
    خروجی: (new_level, new_xp, leveled_up)
    xp در هر لول به صورت progress نگه داشته می‌شود.
    """
    new_level = int(level)
    new_xp = int(xp) + int(gained)
    leveled = False

    while new_xp >= xp_required_for_level(new_level):
        new_xp -= xp_required_for_level(new_level)
        new_level += 1
        leveled = True

    return new_level, new_xp, leveled
