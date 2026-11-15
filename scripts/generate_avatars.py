#!/usr/bin/env python3
"""
Generate crisp, high-DPI theme avatars for SIQVA chat interface.
Generates:
- app/assets/assistant_avatar.png (Teal ocean wave in Deep Ocean palette)
- app/assets/user_avatar.png (Neutral person silhouette in Deep Ocean palette)
"""

from pathlib import Path
from PIL import Image, ImageDraw

def generate_avatars(assets_dir: Path | None = None) -> None:
    if assets_dir is None:
        assets_dir = Path(__file__).resolve().parent.parent / "app" / "assets"
    assets_dir.mkdir(parents=True, exist_ok=True)

    size = 128

    # 1. Assistant Avatar: Ocean waves in Teal (#2EC4B6) on Dark Surface (#12303F)
    asst_img = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    d_asst = ImageDraw.Draw(asst_img)

    # Background circle
    d_asst.ellipse([4, 4, size - 4, size - 4], fill=(18, 48, 63, 255), outline=(46, 196, 182, 180), width=4)

    # Stylized wave arcs
    teal_color = (46, 196, 182, 255)
    # Upper wave
    d_asst.arc([24, 34, 72, 82], start=180, end=360, fill=teal_color, width=7)
    d_asst.arc([56, 34, 104, 82], start=180, end=360, fill=teal_color, width=7)

    # Lower wave
    d_asst.arc([20, 56, 68, 104], start=180, end=360, fill=teal_color, width=6)
    d_asst.arc([60, 56, 108, 104], start=180, end=360, fill=teal_color, width=6)

    asst_path = assets_dir / "assistant_avatar.png"
    asst_img.save(asst_path, "PNG")
    print(f"Generated assistant avatar: {asst_path}")

    # 2. User Avatar: Neutral Person Silhouette (#E6F1F5) on Slate Canvas (#1A3B4D)
    user_img = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    d_user = ImageDraw.Draw(user_img)

    # Background circle
    d_user.ellipse([4, 4, size - 4, size - 4], fill=(26, 59, 77, 255), outline=(142, 171, 192, 140), width=4)

    user_color = (230, 241, 245, 255)
    # Head
    d_user.ellipse([44, 26, 84, 66], fill=user_color)
    # Torso
    d_user.pieslice([24, 70, 104, 150], start=180, end=360, fill=user_color)

    user_path = assets_dir / "user_avatar.png"
    user_img.save(user_path, "PNG")
    print(f"Generated user avatar: {user_path}")

if __name__ == "__main__":
    generate_avatars()
