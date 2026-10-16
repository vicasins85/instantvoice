"""Writes companion/build_icon/icon.png, icon.ico and (on macOS) icon.icns. Run from companion/."""
import os
import subprocess
import sys

sys.path.insert(0, os.getcwd())
from tray import app_icon  # noqa: E402

out = os.path.join(os.getcwd(), "build_icon")
os.makedirs(out, exist_ok=True)
img = app_icon(1024)
img.save(os.path.join(out, "icon.png"))
img.save(os.path.join(out, "icon.ico"), sizes=[(16, 16), (24, 24), (32, 32), (48, 48), (64, 64), (128, 128), (256, 256)])

if sys.platform == "darwin":
    iconset = os.path.join(out, "icon.iconset")
    os.makedirs(iconset, exist_ok=True)
    for size in (16, 32, 128, 256, 512):
        img.resize((size, size)).save(os.path.join(iconset, f"icon_{size}x{size}.png"))
        img.resize((size * 2, size * 2)).save(os.path.join(iconset, f"icon_{size}x{size}@2x.png"))
    subprocess.run(["iconutil", "-c", "icns", iconset, "-o", os.path.join(out, "icon.icns")], check=True)
print("icons written to", out)
