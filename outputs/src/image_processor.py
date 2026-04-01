#!/usr/bin/env python3
"""Image Processor - Background Removal and Upscaling for print-on-demand."""

from pathlib import Path
from typing import Optional
from PIL import Image
import shutil

PRINT_OPTIMAL_SIZE = 4500


def remove_background(image_path: str, output_path: Optional[str] = None) -> str:
    """Remove background using withoutbg (Focus v1.0.0). Returns output path (transparent PNG)."""
    try:
        from withoutbg import WithoutBG
    except ImportError:
        print("Warning: withoutbg not installed. pip install withoutbg")
        return image_path

    inp = Path(image_path)
    if output_path is None:
        output_path = str(inp.parent / (inp.stem + "_nobg.png"))

    print("Removing background from: " + inp.name + " (using withoutbg Focus model)")
    # Create remover instance with local open-source model
    remover = WithoutBG.opensource()
    # Remove background - returns PIL Image
    result_image = remover.remove_background(image_path)
    # Save as transparent PNG
    result_image.save(output_path, format="PNG")
    print("Background removed: " + output_path)
    return output_path


def upscale_for_print(image_path: str, output_path: Optional[str] = None,
                     target_size: int = PRINT_OPTIMAL_SIZE) -> str:
    """Upscale image to print-ready dimensions using Lanczos."""
    inp = Path(image_path)
    if output_path is None:
        output_path = str(inp.parent / (inp.stem + "_print.png"))

    img = Image.open(image_path)
    w, h = img.size
    longest = max(w, h)

    if longest >= target_size:
        print("Image already large enough: " + str(w) + "x" + str(h))
        if image_path != output_path:
            img.save(output_path, format="PNG")
        return output_path

    scale = target_size / longest
    new_w, new_h = int(w * scale), int(h * scale)
    print("Upscaling " + str(w) + "x" + str(h) + " -> " + str(new_w) + "x" + str(new_h))
    img.resize((new_w, new_h), Image.Resampling.LANCZOS).save(output_path, format="PNG", dpi=(150, 150))
    print("Upscaled: " + output_path)
    return output_path


def process_for_pod(image_path: str, output_path: Optional[str] = None,
                   remove_bg: bool = True, upscale: bool = True,
                   target_size: int = PRINT_OPTIMAL_SIZE) -> str:
    """Full pipeline: optional bg removal + upscale for print."""
    inp = Path(image_path)
    if output_path is None:
        suffix = "_pod"
        if remove_bg:
            suffix += "_nobg"
        if upscale:
            suffix += "_print"
        output_path = str(inp.parent / (inp.stem + suffix + ".png"))

    current = image_path
    tmp_nobg = str(inp.parent / (inp.stem + "_nobg_tmp.png"))

    if remove_bg:
        current = remove_background(current, tmp_nobg)

    if upscale:
        current = upscale_for_print(current, output_path, target_size)
    elif current != output_path:
        shutil.copy2(current, output_path)
        current = output_path

    # Cleanup temp
    tmp = Path(tmp_nobg)
    if tmp.exists() and str(tmp) != output_path:
        tmp.unlink()

    return current


if __name__ == "__main__":
    import sys
    if len(sys.argv) < 2:
        print("Usage: python image_processor.py <image_path> [--no-bg] [--no-upscale]")
        sys.exit(1)
    path = sys.argv[1]
    result = process_for_pod(path, remove_bg="--no-bg" not in sys.argv, upscale="--no-upscale" not in sys.argv)
    print("Done: " + result)
