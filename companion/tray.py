"""Tray / menu bar icon image. Grey idle, red listening, amber thinking, violet voice on."""
from __future__ import annotations

from PIL import Image, ImageDraw

COLORS = {
    "idle": (150, 155, 170),
    "listening": (235, 70, 70),
    "thinking": (240, 175, 50),
    "on": (139, 124, 255),
}


def tray_image(on: bool, status: str = "") -> Image.Image:
    s = status.lower()
    if s.startswith("listening"):
        color = COLORS["listening"]
    elif s.startswith("thinking"):
        color = COLORS["thinking"]
    elif on:
        color = COLORS["on"]
    else:
        color = COLORS["idle"]
    img = Image.new("RGBA", (64, 64), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    d.rounded_rectangle((22, 6, 42, 40), radius=10, fill=color)
    d.arc((14, 20, 50, 50), start=0, end=180, fill=color, width=4)
    d.line((32, 50, 32, 58), fill=color, width=4)
    d.line((22, 58, 42, 58), fill=color, width=4)
    return img


def app_icon(size: int = 1024) -> Image.Image:
    """App icon: rounded square with a waveform."""
    img = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    pad = size // 10
    d.rounded_rectangle((pad, pad, size - pad, size - pad), radius=size // 5, fill=(139, 124, 255))
    cx, cy = size // 2, size // 2
    bars = [0.18, 0.38, 0.62, 0.38, 0.18]
    w = size // 16
    gap = size // 9
    for i, h in enumerate(bars):
        x = cx + (i - 2) * gap
        half = int(h * size / 2)
        d.rounded_rectangle((x - w // 2, cy - half, x + w // 2, cy + half), radius=w // 2, fill=(12, 14, 22))
    return img
