from django.db import models


class AcademicPeriod(models.Model):
    name = models.CharField(max_length=100)  # e.g., "Semester 1 2025/26"
    start_date = models.DateField(null=True, blank=True)
    end_date = models.DateField(null=True, blank=True)
    is_active = models.BooleanField(default=True)

    def __str__(self):
        return self.name


class Level(models.Model):
    code = models.CharField(max_length=20, unique=True, help_text="e.g. 100 or L100")
    label = models.CharField(max_length=50, blank=True)  # Auto-computed: Level 100
    year = models.CharField(max_length=50, blank=True)   # Auto-computed: 1st Year
    color = models.CharField(max_length=20, default="#3b82f6", blank=True)
    bg = models.CharField(max_length=20, default="#eff6ff", blank=True)
    border = models.CharField(max_length=20, default="#bfdbfe", blank=True)

    def save(self, *args, **kwargs):
        # Auto-normalize code from number (e.g. '100' or '1' -> 'L100')
        raw = str(self.code).upper().strip().replace('LEVEL', '').replace('L', '').strip()
        if raw.isdigit():
            num = int(raw)
            if num < 10:
                num = num * 100
            self.code = f"L{num}"
            if not self.label:
                self.label = f"Level {num}"
            if not self.year:
                year_map = {100: "1st Year", 200: "2nd Year", 300: "3rd Year", 400: "4th Year"}
                self.year = year_map.get(num, f"Year {num // 100}")
            color_map = {
                100: ("#3b82f6", "#eff6ff", "#bfdbfe"),
                200: ("#8b5cf6", "#f5f3ff", "#ddd6fe"),
                300: ("#10b981", "#ecfdf5", "#a7f3d0"),
                400: ("#f59e0b", "#fffbeb", "#fde68a"),
            }
            if num in color_map and (self.color == "#3b82f6" or not self.color):
                self.color, self.bg, self.border = color_map[num]
        elif not self.label:
            self.label = f"Level {self.code}"

        super().save(*args, **kwargs)

    def __str__(self):
        return self.label or self.code
