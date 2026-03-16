from __future__ import annotations

from pathlib import Path

from PIL import Image, ImageDraw


def build_icon(size: int) -> Image.Image:
    image = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    draw = ImageDraw.Draw(image)

    padding = int(size * 0.08)
    card_radius = int(size * 0.18)
    draw.rounded_rectangle(
        (padding, padding, size - padding, size - padding),
        radius=card_radius,
        fill="#17324D",
    )

    accent_width = int(size * 0.1)
    draw.rounded_rectangle(
        (padding, padding, padding + accent_width, size - padding),
        radius=card_radius,
        fill="#F97316",
    )

    shelf_left = int(size * 0.24)
    shelf_top = int(size * 0.24)
    shelf_right = int(size * 0.78)
    shelf_bottom = int(size * 0.78)
    draw.rounded_rectangle(
        (shelf_left, shelf_top, shelf_right, shelf_bottom),
        radius=int(size * 0.08),
        fill="#F8FAFC",
    )

    gap = int(size * 0.04)
    book_width = int(size * 0.11)
    book_bottom = int(size * 0.72)
    book_top = int(size * 0.31)
    first_book_left = int(size * 0.31)

    book_colors = ["#1D4ED8", "#0F766E", "#C2410C"]
    for index, color in enumerate(book_colors):
        left = first_book_left + index * (book_width + gap)
        right = left + book_width
        draw.rounded_rectangle(
            (left, book_top, right, book_bottom),
            radius=int(size * 0.03),
            fill=color,
        )
        draw.line(
            (left + int(book_width * 0.25), book_top + gap, left + int(book_width * 0.25), book_bottom - gap),
            fill="#FFFFFF",
            width=max(1, size // 64),
        )

    draw.rounded_rectangle(
        (int(size * 0.28), int(size * 0.72), int(size * 0.76), int(size * 0.76)),
        radius=int(size * 0.02),
        fill="#CBD5E1",
    )

    return image


def main() -> None:
    project_root = Path(__file__).resolve().parents[1]
    assets_dir = project_root / "assets"
    assets_dir.mkdir(parents=True, exist_ok=True)

    icon_path = assets_dir / "app_icon.ico"
    base_icon = build_icon(256)
    base_icon.save(
        icon_path,
        format="ICO",
        sizes=[(256, 256), (128, 128), (64, 64), (48, 48), (32, 32), (16, 16)],
    )
    print(icon_path)


if __name__ == "__main__":
    main()
