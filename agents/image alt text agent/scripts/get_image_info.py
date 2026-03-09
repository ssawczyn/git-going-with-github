#!/usr/bin/env python3
"""Extract image metadata for accessibility markup.

Usage:
    python get_image_info.py <image_path> [--json]
    python get_image_info.py <folder_path> --batch [--json]

Outputs width, height, aspect ratio, format, file size, color mode, EXIF data,
dominant colors, and SVG viewBox for each image.
Requires: Pillow (pip install Pillow)
"""

import argparse
import json
import re
import sys
from pathlib import Path

try:
    from PIL import Image
    from PIL.ExifTags import TAGS
except ImportError:
    print(
        "Error: Pillow is required. Install it with: pip install Pillow",
        file=sys.stderr,
    )
    sys.exit(1)

SUPPORTED_EXTENSIONS = {
    ".jpg", ".jpeg", ".png", ".gif", ".webp", ".avif",
    ".svg", ".bmp", ".tiff", ".tif", ".ico",
}


def extract_exif(img: Image.Image) -> dict:
    """Extract common EXIF tags from an image."""
    exif_data = {}
    try:
        raw_exif = img.getexif()
        if not raw_exif:
            return exif_data
        # Only extract useful accessibility-relevant tags
        wanted = {
            "ImageDescription", "Make", "Model", "Orientation",
            "DateTime", "DateTimeOriginal", "GPSInfo",
            "XResolution", "YResolution",
        }
        for tag_id, value in raw_exif.items():
            tag_name = TAGS.get(tag_id, str(tag_id))
            if tag_name in wanted:
                # Convert to string for JSON serialization
                exif_data[tag_name] = str(value)
    except Exception:
        pass
    return exif_data


def extract_dominant_colors(img: Image.Image, count: int = 3) -> list[str]:
    """Extract the top dominant colors as hex strings."""
    try:
        # Resize to small thumbnail for fast color analysis
        thumb = img.copy()
        thumb.thumbnail((50, 50))
        # Convert to RGB if needed
        if thumb.mode not in ("RGB", "RGBA"):
            thumb = thumb.convert("RGB")
        elif thumb.mode == "RGBA":
            # Composite on white background
            bg = Image.new("RGB", thumb.size, (255, 255, 255))
            bg.paste(thumb, mask=thumb.split()[3])
            thumb = bg

        colors = thumb.getcolors(maxcolors=2500)
        if not colors:
            return []
        # Sort by frequency (count descending)
        colors.sort(key=lambda x: x[0], reverse=True)
        result = []
        for freq, rgb in colors[:count]:
            hex_color = "#{:02x}{:02x}{:02x}".format(*rgb)
            result.append(hex_color)
        return result
    except Exception:
        return []


def parse_svg_viewbox(svg_path: Path) -> dict:
    """Extract viewBox and explicit width/height from an SVG file."""
    result = {}
    try:
        content = svg_path.read_text(encoding="utf-8", errors="ignore")
        # Extract viewBox
        viewbox_match = re.search(r'viewBox\s*=\s*["\']([^"\']+)["\']', content)
        if viewbox_match:
            result["viewBox"] = viewbox_match.group(1)
            parts = viewbox_match.group(1).split()
            if len(parts) == 4:
                try:
                    result["viewBox_width"] = float(parts[2])
                    result["viewBox_height"] = float(parts[3])
                except ValueError:
                    pass
        # Extract explicit width/height attributes
        width_match = re.search(r'<svg[^>]*\bwidth\s*=\s*["\']([^"\']+)["\']', content)
        height_match = re.search(r'<svg[^>]*\bheight\s*=\s*["\']([^"\']+)["\']', content)
        if width_match:
            result["svg_width"] = width_match.group(1)
        if height_match:
            result["svg_height"] = height_match.group(1)
    except Exception:
        pass
    return result


def get_image_info(image_path: Path) -> dict:
    """Extract metadata from a single image file."""
    if not image_path.is_file():
        return {"path": str(image_path), "error": "File not found"}

    suffix = image_path.suffix.lower()
    if suffix not in SUPPORTED_EXTENSIONS:
        return {"path": str(image_path), "error": f"Unsupported format: {image_path.suffix}"}

    # SVG special handling
    if suffix == ".svg":
        svg_info = parse_svg_viewbox(image_path)
        result = {
            "path": str(image_path),
            "filename": image_path.name,
            "format": "SVG",
            "width": int(svg_info.get("viewBox_width", 0)),
            "height": int(svg_info.get("viewBox_height", 0)),
            "aspect_ratio": "N/A",
            "file_size_bytes": image_path.stat().st_size,
            "file_size_kb": round(image_path.stat().st_size / 1024, 1),
            "mode": "vector",
        }
        if svg_info.get("viewBox"):
            result["viewBox"] = svg_info["viewBox"]
        if svg_info.get("svg_width"):
            result["svg_width"] = svg_info["svg_width"]
        if svg_info.get("svg_height"):
            result["svg_height"] = svg_info["svg_height"]
        # Calculate aspect ratio from viewBox if available
        w = svg_info.get("viewBox_width", 0)
        h = svg_info.get("viewBox_height", 0)
        if w > 0 and h > 0:
            from math import gcd
            divisor = gcd(int(w), int(h))
            result["aspect_ratio"] = f"{int(w) // divisor}:{int(h) // divisor}"
        return result

    try:
        with Image.open(image_path) as img:
            width, height = img.size
            from math import gcd

            divisor = gcd(width, height)
            aspect_w = width // divisor
            aspect_h = height // divisor

            result = {
                "path": str(image_path),
                "filename": image_path.name,
                "format": img.format or suffix.lstrip(".").upper(),
                "width": width,
                "height": height,
                "aspect_ratio": f"{aspect_w}:{aspect_h}",
                "file_size_bytes": image_path.stat().st_size,
                "file_size_kb": round(image_path.stat().st_size / 1024, 1),
                "mode": img.mode,
            }

            # EXIF data
            exif = extract_exif(img)
            if exif:
                result["exif"] = exif

            # Dominant colors
            colors = extract_dominant_colors(img)
            if colors:
                result["dominant_colors"] = colors

            # Flag potential image-of-text (heuristic: high contrast, few colors)
            try:
                thumb = img.copy()
                thumb.thumbnail((100, 100))
                if thumb.mode not in ("RGB", "RGBA"):
                    thumb = thumb.convert("RGB")
                unique_colors = len(set(thumb.getdata()))
                total_pixels = thumb.size[0] * thumb.size[1]
                color_ratio = unique_colors / total_pixels if total_pixels > 0 else 1
                # Very few unique colors relative to pixels suggests text/graphics
                if color_ratio < 0.05 and unique_colors < 50:
                    result["text_heuristic"] = "likely-text-or-graphic"
                elif color_ratio < 0.15:
                    result["text_heuristic"] = "possible-text-or-graphic"
                else:
                    result["text_heuristic"] = "likely-photograph"
            except Exception:
                pass

            return result
    except Exception as exc:
        return {"path": str(image_path), "error": str(exc)}


def scan_folder(folder_path: Path) -> list[dict]:
    """Scan a folder for all image files and extract metadata."""
    results = []
    for file in sorted(folder_path.rglob("*")):
        if file.suffix.lower() in SUPPORTED_EXTENSIONS:
            results.append(get_image_info(file))
    return results


def format_table(info_list: list[dict]) -> str:
    """Format results as a readable text table."""
    lines = []
    lines.append(f"{'File':<40} {'Dimensions':<14} {'Ratio':<10} {'Format':<8} {'Size':<12} {'Hint':<20}")
    lines.append("-" * 104)
    for info in info_list:
        if "error" in info:
            lines.append(f"{info['path']:<40} ERROR: {info['error']}")
        else:
            dims = f"{info['width']}x{info['height']}"
            size = f"{info['file_size_kb']} KB"
            hint = info.get("text_heuristic", info.get("viewBox", ""))
            lines.append(
                f"{info['filename']:<40} {dims:<14} {info['aspect_ratio']:<10} {info['format']:<8} {size:<12} {hint:<20}"
            )
    return "\n".join(lines)


def main():
    parser = argparse.ArgumentParser(description="Extract image metadata for accessibility markup.")
    parser.add_argument("path", type=Path, help="Path to an image file or folder")
    parser.add_argument("--batch", action="store_true", help="Scan all images in folder recursively")
    parser.add_argument("--json", action="store_true", dest="as_json", help="Output as JSON")
    args = parser.parse_args()

    target = args.path.resolve()

    if args.batch or target.is_dir():
        if not target.is_dir():
            print(f"Error: {target} is not a directory", file=sys.stderr)
            sys.exit(1)
        results = scan_folder(target)
        if not results:
            print("No supported images found.", file=sys.stderr)
            sys.exit(1)
    else:
        results = [get_image_info(target)]

    if args.as_json:
        print(json.dumps(results if len(results) > 1 else results[0], indent=2))
    else:
        print(format_table(results))


if __name__ == "__main__":
    main()
