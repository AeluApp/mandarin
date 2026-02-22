#!/usr/bin/env python3
"""Generate AppIcon.icns for MandarinApp.

Draws the character 漫 in accent color (#946070) on linen (#F2EBE0) background.

Uses CoreGraphics + CoreText via ctypes (no PyObjC needed, no Cocoa import).
This avoids the SwiftBridging modulemap bug entirely since we stay in C-level APIs.
"""

import ctypes
import ctypes.util
import os
import subprocess
import shutil
import struct
import zlib

# ── Load C frameworks ──────────────────────────────────────────────

def _load(name):
    path = ctypes.util.find_library(name)
    if path:
        return ctypes.cdll.LoadLibrary(path)
    raise RuntimeError(f"Cannot find library: {name}")

CG = _load("CoreGraphics")
CT = _load("CoreText")
CF = _load("CoreFoundation")

CGFloat = ctypes.c_double

# ── CoreFoundation ─────────────────────────────────────────────────

CF.CFStringCreateWithCString.restype = ctypes.c_void_p
CF.CFStringCreateWithCString.argtypes = [ctypes.c_void_p, ctypes.c_char_p, ctypes.c_uint32]

CF.CFAttributedStringCreate.restype = ctypes.c_void_p
CF.CFAttributedStringCreate.argtypes = [ctypes.c_void_p, ctypes.c_void_p, ctypes.c_void_p]

CF.CFDictionaryCreate.restype = ctypes.c_void_p
CF.CFDictionaryCreate.argtypes = [
    ctypes.c_void_p,
    ctypes.POINTER(ctypes.c_void_p),
    ctypes.POINTER(ctypes.c_void_p),
    ctypes.c_long,
    ctypes.c_void_p, ctypes.c_void_p,
]

CF.CFRelease.argtypes = [ctypes.c_void_p]
CF.CFRelease.restype = None

CF.CFURLCreateWithFileSystemPath.restype = ctypes.c_void_p
CF.CFURLCreateWithFileSystemPath.argtypes = [ctypes.c_void_p, ctypes.c_void_p, ctypes.c_int, ctypes.c_bool]

kCFStringEncodingUTF8 = 0x08000100

def cfstr(s):
    return CF.CFStringCreateWithCString(None, s.encode("utf-8"), kCFStringEncodingUTF8)

# ── CoreGraphics ───────────────────────────────────────────────────

CG.CGColorSpaceCreateDeviceRGB.restype = ctypes.c_void_p
CG.CGColorSpaceCreateDeviceRGB.argtypes = []

CG.CGBitmapContextCreate.restype = ctypes.c_void_p
CG.CGBitmapContextCreate.argtypes = [
    ctypes.c_void_p, ctypes.c_size_t, ctypes.c_size_t,
    ctypes.c_size_t, ctypes.c_size_t, ctypes.c_void_p, ctypes.c_uint32
]

CG.CGBitmapContextCreateImage.restype = ctypes.c_void_p
CG.CGBitmapContextCreateImage.argtypes = [ctypes.c_void_p]

CG.CGBitmapContextGetData.restype = ctypes.POINTER(ctypes.c_ubyte)
CG.CGBitmapContextGetData.argtypes = [ctypes.c_void_p]

CG.CGContextSetRGBFillColor.argtypes = [ctypes.c_void_p, CGFloat, CGFloat, CGFloat, CGFloat]
CG.CGContextSetRGBFillColor.restype = None

CG.CGContextFillRect.argtypes = [ctypes.c_void_p, CGFloat * 4]
CG.CGContextFillRect.restype = None

CG.CGContextAddPath.argtypes = [ctypes.c_void_p, ctypes.c_void_p]
CG.CGContextAddPath.restype = None

CG.CGContextFillPath.argtypes = [ctypes.c_void_p]
CG.CGContextFillPath.restype = None

CG.CGPathCreateWithRoundedRect.restype = ctypes.c_void_p
CG.CGPathCreateWithRoundedRect.argtypes = [CGFloat * 4, CGFloat, CGFloat, ctypes.c_void_p]

CG.CGPathRelease.argtypes = [ctypes.c_void_p]
CG.CGPathRelease.restype = None

CG.CGContextRelease.argtypes = [ctypes.c_void_p]
CG.CGContextRelease.restype = None

CG.CGImageRelease.argtypes = [ctypes.c_void_p]
CG.CGImageRelease.restype = None

CG.CGColorSpaceRelease.argtypes = [ctypes.c_void_p]
CG.CGColorSpaceRelease.restype = None

CG.CGColorCreate.restype = ctypes.c_void_p
CG.CGColorCreate.argtypes = [ctypes.c_void_p, ctypes.POINTER(CGFloat)]

CG.CGColorRelease.argtypes = [ctypes.c_void_p]
CG.CGColorRelease.restype = None

CG.CGContextSetTextPosition.argtypes = [ctypes.c_void_p, CGFloat, CGFloat]
CG.CGContextSetTextPosition.restype = None

# ── CoreText ───────────────────────────────────────────────────────

CT.CTFontCreateWithName.restype = ctypes.c_void_p
CT.CTFontCreateWithName.argtypes = [ctypes.c_void_p, CGFloat, ctypes.c_void_p]

CT.CTLineCreateWithAttributedString.restype = ctypes.c_void_p
CT.CTLineCreateWithAttributedString.argtypes = [ctypes.c_void_p]

CT.CTLineDraw.argtypes = [ctypes.c_void_p, ctypes.c_void_p]
CT.CTLineDraw.restype = None

CT.CTLineGetTypographicBounds.restype = ctypes.c_double
CT.CTLineGetTypographicBounds.argtypes = [
    ctypes.c_void_p,
    ctypes.POINTER(CGFloat),
    ctypes.POINTER(CGFloat),
    ctypes.POINTER(CGFloat),
]

# Get the CoreText attribute key constants
_kCTFontAttributeName = ctypes.c_void_p.in_dll(CT, "kCTFontAttributeName")
_kCTForegroundColorAttributeName = ctypes.c_void_p.in_dll(CT, "kCTForegroundColorAttributeName")


# ── ImageIO ────────────────────────────────────────────────────────

ImageIO = _load("ImageIO")

ImageIO.CGImageDestinationCreateWithURL.restype = ctypes.c_void_p
ImageIO.CGImageDestinationCreateWithURL.argtypes = [ctypes.c_void_p, ctypes.c_void_p, ctypes.c_size_t, ctypes.c_void_p]

ImageIO.CGImageDestinationAddImage.argtypes = [ctypes.c_void_p, ctypes.c_void_p, ctypes.c_void_p]
ImageIO.CGImageDestinationAddImage.restype = None

ImageIO.CGImageDestinationFinalize.restype = ctypes.c_bool
ImageIO.CGImageDestinationFinalize.argtypes = [ctypes.c_void_p]


# ── Helpers ────────────────────────────────────────────────────────

def make_rect(x, y, w, h):
    r = (CGFloat * 4)()
    r[0] = x; r[1] = y; r[2] = w; r[3] = h
    return r


def create_icon_context(size):
    """Create a bitmap context and draw the icon. Returns (context, cgImage)."""
    cs = CG.CGColorSpaceCreateDeviceRGB()

    # kCGImageAlphaPremultipliedLast (RGBA) = 1
    ctx = CG.CGBitmapContextCreate(None, size, size, 8, size * 4, cs, 1)

    # Colors
    linen_r, linen_g, linen_b = 0xF2 / 255.0, 0xEB / 255.0, 0xE0 / 255.0
    accent_r, accent_g, accent_b = 0x94 / 255.0, 0x60 / 255.0, 0x70 / 255.0

    # Fill background with linen
    CG.CGContextSetRGBFillColor(ctx, linen_r, linen_g, linen_b, 1.0)
    CG.CGContextFillRect(ctx, make_rect(0, 0, size, size))

    # Rounded rect (macOS icon corner radius ~22.37%)
    corner = size * 0.2237
    rect = make_rect(0, 0, size, size)
    path = CG.CGPathCreateWithRoundedRect(rect, corner, corner, None)
    CG.CGContextAddPath(ctx, path)
    CG.CGContextSetRGBFillColor(ctx, linen_r, linen_g, linen_b, 1.0)
    CG.CGContextFillPath(ctx)
    CG.CGPathRelease(path)

    # Create font and color for text
    font_size = size * 0.62
    font_name = cfstr("PingFangSC-Medium")
    font = CT.CTFontCreateWithName(font_name, font_size, None)
    if not font:
        font_name2 = cfstr("PingFang SC")
        font = CT.CTFontCreateWithName(font_name2, font_size, None)
        CF.CFRelease(font_name2)
    CF.CFRelease(font_name)

    components = (CGFloat * 4)(accent_r, accent_g, accent_b, 1.0)
    color = CG.CGColorCreate(cs, components)

    # Build attributed string: { kCTFontAttributeName: font, kCTForegroundColorAttributeName: color }
    keys = (ctypes.c_void_p * 2)(_kCTFontAttributeName.value, _kCTForegroundColorAttributeName.value)
    values = (ctypes.c_void_p * 2)(font, color)
    attrs = CF.CFDictionaryCreate(None, keys, values, 2, None, None)

    # Create CFString for the character 漫
    text = cfstr("\u6F2B")
    attr_str = CF.CFAttributedStringCreate(None, text, attrs)

    # Create CTLine
    line = CT.CTLineCreateWithAttributedString(attr_str)

    # Measure for centering
    ascent = CGFloat(0)
    descent = CGFloat(0)
    leading = CGFloat(0)
    width = CT.CTLineGetTypographicBounds(line, ctypes.byref(ascent), ctypes.byref(descent), ctypes.byref(leading))

    text_height = ascent.value + descent.value
    x = (size - width) / 2.0
    y = (size - text_height) / 2.0 + descent.value - size * 0.02

    CG.CGContextSetTextPosition(ctx, x, y)
    CT.CTLineDraw(line, ctx)

    # Create CGImage
    image = CG.CGBitmapContextCreateImage(ctx)

    # Cleanup
    CF.CFRelease(line)
    CF.CFRelease(attr_str)
    CF.CFRelease(text)
    CF.CFRelease(attrs)
    CG.CGColorRelease(color)
    CF.CFRelease(font)
    CG.CGContextRelease(ctx)
    CG.CGColorSpaceRelease(cs)

    return image


def save_png(cgImage, path):
    """Save CGImage to PNG using ImageIO."""
    url_str = cfstr(path)
    url = CF.CFURLCreateWithFileSystemPath(None, url_str, 0, False)  # kCFURLPOSIXPathStyle = 0
    CF.CFRelease(url_str)

    png_uti = cfstr("public.png")
    dest = ImageIO.CGImageDestinationCreateWithURL(url, png_uti, 1, None)
    CF.CFRelease(png_uti)

    ImageIO.CGImageDestinationAddImage(dest, cgImage, None)
    ok = ImageIO.CGImageDestinationFinalize(dest)

    CF.CFRelease(dest)
    CF.CFRelease(url)

    if not ok:
        raise RuntimeError(f"Failed to write PNG: {path}")


def main():
    script_dir = os.path.dirname(os.path.abspath(__file__))
    iconset_dir = os.path.join(script_dir, "AppIcon.iconset")
    icns_path = os.path.join(script_dir, "AppIcon.icns")

    # Clean
    if os.path.exists(iconset_dir):
        shutil.rmtree(iconset_dir)
    os.makedirs(iconset_dir)

    # Required icon sizes
    sizes = {
        "icon_16x16.png": 16,
        "icon_16x16@2x.png": 32,
        "icon_32x32.png": 32,
        "icon_32x32@2x.png": 64,
        "icon_128x128.png": 128,
        "icon_128x128@2x.png": 256,
        "icon_256x256.png": 256,
        "icon_256x256@2x.png": 512,
        "icon_512x512.png": 512,
        "icon_512x512@2x.png": 1024,
    }

    for name, px in sizes.items():
        print(f"  Generating {name} ({px}x{px})...")
        image = create_icon_context(px)
        save_png(image, os.path.join(iconset_dir, name))
        CG.CGImageRelease(image)

    # Convert iconset to icns
    print(f"  Creating AppIcon.icns...")
    subprocess.run(
        ["iconutil", "-c", "icns", iconset_dir, "-o", icns_path],
        check=True,
    )

    # Clean up iconset
    shutil.rmtree(iconset_dir)
    print(f"  Done: {icns_path}")


if __name__ == "__main__":
    main()
