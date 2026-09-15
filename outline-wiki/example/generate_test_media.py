"""Generate placeholder media (PNG, GIF, MP4, SVG) for the GDC Outline sync test."""

import colorsys
import pathlib

import imageio.v2 as imageio
from PIL import Image, ImageDraw, ImageFont

OUT = pathlib.Path(__file__).parent / "assets"
W, H = 480, 270
N_FRAMES = 20


def frame(i: int, n: int) -> Image.Image:
    hue = i / n
    r, g, b = (int(c * 255) for c in colorsys.hsv_to_rgb(hue, 0.65, 0.9))
    img = Image.new("RGB", (W, H), (r, g, b))
    draw = ImageDraw.Draw(img)
    try:
        font = ImageFont.truetype("arial.ttf", 28)
    except OSError:
        font = ImageFont.load_default()
    text = f"GDC calibration\nframe {i + 1}/{n}"
    draw.multiline_text((W / 2, H / 2), text, fill="white", font=font, anchor="mm", align="center")
    return img


def main() -> None:
    frames = [frame(i, N_FRAMES) for i in range(N_FRAMES)]

    frames[0].save(
        OUT / "gdc_calibration.gif",
        save_all=True,
        append_images=frames[1:],
        duration=120,
        loop=0,
    )
    print("wrote", OUT / "gdc_calibration.gif")

    imageio.mimsave(OUT / "gdc_calibration.mp4", [f.convert("RGB") for f in frames], fps=8)
    print("wrote", OUT / "gdc_calibration.mp4")

    frames[0].save(OUT / "gdc_target.png")
    print("wrote", OUT / "gdc_target.png")

    svg = """<svg xmlns="http://www.w3.org/2000/svg" width="120" height="120"
     viewBox="0 0 120 120">
  <circle cx="60" cy="60" r="50" fill="none" stroke="#1e3a5f" stroke-width="4"/>
  <line x1="60" y1="10" x2="60" y2="110" stroke="#5a2d4a" stroke-width="2"/>
  <line x1="10" y1="60" x2="110" y2="60" stroke="#5a2d4a" stroke-width="2"/>
  <circle cx="60" cy="60" r="6" fill="#4a3c1e"/>
</svg>"""
    (OUT / "gdc_icon.svg").write_text(svg)
    print("wrote", OUT / "gdc_icon.svg")


if __name__ == "__main__":
    main()
