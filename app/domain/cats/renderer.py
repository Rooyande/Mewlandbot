from pathlib import Path
from typing import Optional

from PIL import Image, ImageDraw, ImageFont


ASSETS_ROOT = Path("assets")


def get_cat_image_path(base_image_path: str) -> Path:
    """
    base_image_path در DB مثل: assets/cats/siamese.png
    ما آن را به Path تبدیل می‌کنیم.
    """
    return Path(base_image_path)


def ensure_placeholder(path: Path, title: str = "CAT") -> Path:
    """
    اگر تصویر واقعی وجود نداشت، یک تصویر placeholder می‌سازیم.
    این باعث می‌شود ربات هیچ وقت به خاطر نبود asset کرش نکند.
    """
    path.parent.mkdir(parents=True, exist_ok=True)

    img = Image.new("RGBA", (512, 512), (30, 30, 30, 255))
    draw = ImageDraw.Draw(img)

    # متن وسط
    text = f"{title}\n(missing asset)"
    draw.multiline_text((40, 220), text, fill=(255, 255, 255, 255), spacing=8)

    img.save(path)
    return path


def render_cat_image(base_image_path: str, title: str) -> Path:
    """
    فعلاً فقط عکس پایه را آماده می‌کنیم.
    در آینده اینجا آیتم‌ها (تاج/کلاه) هم overlay می‌شوند.
    """
    p = get_cat_image_path(base_image_path)
    if not p.exists():
        return ensure_placeholder(p, title=title)
    return p

