import base64
import ctypes
import json
import os
import re
import struct
import sys
import time
import urllib.request
import zlib
from ctypes import wintypes
from typing import Any, Dict, List, Tuple, Optional

# ============================================================================
# CONFIGURATION
# ============================================================================

LMSTUDIO_ENDPOINT = "http://localhost:1234/v1/chat/completions"
LMSTUDIO_MODEL = "qwen3-vl-2b-instruct"
LMSTUDIO_TIMEOUT = 240
LMSTUDIO_TEMPERATURE = 0.5

LMSTUDIO_MAX_TOKENS = 1024

AGENT_IMAGE_W = 512
AGENT_IMAGE_H = 256

DUMP_DIR = "dumps"
DUMP_PREFIX = "screen_"

MAX_STEPS = 600

# TIMING CONSTANTS
TIMING_CURSOR_SETTLE = 0.12
TIMING_UI_RENDER = 2.5
TIMING_INPUT_CHAR = 0.005
TIMING_CLICK_DOUBLE = 0.05
TIMING_DRAG_STEP = 0.01
TIMING_DRAG_PREPARE = 0.1
TIMING_SCREENSHOT_SETTLE = 3.4
TIMING_TURN_DELAY = 3.5
TIMING_INTER_ACTION = 0.3

# FEATURE FLAGS
ENABLE_ACTIVE_LOOP_PREVENTION = True
ENABLE_FULL_ARCHIVE = True

# NEW: Three-body hierarchy config
TACTICIAN_INTERVAL = 5  # Oversight every N turns
JUSTIFICATION_MIN_CHARS = 30
LOOP_DETECTION_THRESHOLD = 3
MAX_HISTORY_ITEMS = 10

# ============================================================================
# WINDOWS API (unchanged)
# ============================================================================

for attr in ["HCURSOR", "HICON", "HBITMAP", "HGDIOBJ", "HBRUSH", "HDC"]:
    if not hasattr(wintypes, attr):
        setattr(wintypes, attr, wintypes.HANDLE)
if not hasattr(wintypes, "ULONG_PTR"):
    wintypes.ULONG_PTR = ctypes.c_size_t

user32 = ctypes.WinDLL("user32", use_last_error=True)
gdi32 = ctypes.WinDLL("gdi32", use_last_error=True)

DPI_AWARENESS_CONTEXT_PER_MONITOR_AWARE_V2 = ctypes.c_void_p(-4)
SM_CXSCREEN, SM_CYSCREEN = 0, 1
CURSOR_SHOWING, DI_NORMAL = 0x00000001, 0x0003
BI_RGB, DIB_RGB_COLORS = 0, 0
HALFTONE, SRCCOPY = 4, 0x00CC0020
INPUT_MOUSE, INPUT_KEYBOARD = 0, 1
KEYEVENTF_KEYUP, KEYEVENTF_UNICODE = 0x0002, 0x0004
MOUSEEVENTF_LEFTDOWN, MOUSEEVENTF_LEFTUP = 0x0002, 0x0004
MOUSEEVENTF_RIGHTDOWN, MOUSEEVENTF_RIGHTUP = 0x0008, 0x0010
MOUSEEVENTF_WHEEL = 0x0800

VK_MAP = {
    "enter": 0x0D, "tab": 0x09, "escape": 0x1B, "esc": 0x1B, "windows": 0x5B, "win": 0x5B,
    "ctrl": 0x11, "alt": 0x12, "shift": 0x10, "f4": 0x73, "c": 0x43, "v": 0x56,
    "t": 0x54, "w": 0x57, "f": 0x46, "l": 0x4C, "r": 0x52,
    "backspace": 0x08, "delete": 0x2E, "space": 0x20,
    "home": 0x24, "end": 0x23, "pageup": 0x21, "pagedown": 0x22,
    "left": 0x25, "up": 0x26, "right": 0x27, "down": 0x28,
}

class POINT(ctypes.Structure):
    _fields_ = [("x", wintypes.LONG), ("y", wintypes.LONG)]

class CURSORINFO(ctypes.Structure):
    _fields_ = [("cbSize", wintypes.DWORD), ("flags", wintypes.DWORD),
                ("hCursor", wintypes.HCURSOR), ("ptScreenPos", POINT)]

class ICONINFO(ctypes.Structure):
    _fields_ = [("fIcon", wintypes.BOOL), ("xHotspot", wintypes.DWORD),
                ("yHotspot", wintypes.DWORD), ("hbmMask", wintypes.HBITMAP),
                ("hbmColor", wintypes.HBITMAP)]

class BITMAPINFOHEADER(ctypes.Structure):
    _fields_ = [("biSize", wintypes.DWORD), ("biWidth", wintypes.LONG),
                ("biHeight", wintypes.LONG), ("biPlanes", wintypes.WORD),
                ("biBitCount", wintypes.WORD), ("biCompression", wintypes.DWORD),
                ("biSizeImage", wintypes.DWORD), ("biXPelsPerMeter", wintypes.LONG),
                ("biYPelsPerMeter", wintypes.LONG), ("biClrUsed", wintypes.DWORD),
                ("biClrImportant", wintypes.DWORD)]

class BITMAPINFO(ctypes.Structure):
    _fields_ = [("bmiHeader", BITMAPINFOHEADER), ("bmiColors", wintypes.DWORD * 3)]

class MOUSEINPUT(ctypes.Structure):
    _fields_ = [("dx", wintypes.LONG), ("dy", wintypes.LONG), ("mouseData", wintypes.DWORD),
                ("dwFlags", wintypes.DWORD), ("time", wintypes.DWORD),
                ("dwExtraInfo", wintypes.ULONG_PTR)]

class KEYBDINPUT(ctypes.Structure):
    _fields_ = [("wVk", wintypes.WORD), ("wScan", wintypes.WORD),
                ("dwFlags", wintypes.DWORD), ("time", wintypes.DWORD),
                ("dwExtraInfo", wintypes.ULONG_PTR)]

class HARDWAREINPUT(ctypes.Structure):
    _fields_ = [("uMsg", wintypes.DWORD), ("wParamL", wintypes.WORD), ("wParamH", wintypes.WORD)]

class INPUT_I(ctypes.Union):
    _fields_ = [("mi", MOUSEINPUT), ("ki", KEYBDINPUT), ("hi", HARDWAREINPUT)]

class INPUT(ctypes.Structure):
    _fields_ = [("type", wintypes.DWORD), ("ii", INPUT_I)]

user32.GetSystemMetrics.argtypes = [wintypes.INT]
user32.GetSystemMetrics.restype = wintypes.INT
user32.GetCursorInfo.argtypes = [ctypes.POINTER(CURSORINFO)]
user32.GetCursorInfo.restype = wintypes.BOOL
user32.GetIconInfo.argtypes = [wintypes.HICON, ctypes.POINTER(ICONINFO)]
user32.GetIconInfo.restype = wintypes.BOOL
user32.DrawIconEx.argtypes = [wintypes.HDC, wintypes.INT, wintypes.INT, wintypes.HICON,
                              wintypes.INT, wintypes.INT, wintypes.UINT, wintypes.HBRUSH, wintypes.UINT]
user32.DrawIconEx.restype = wintypes.BOOL
user32.GetDC.argtypes = [wintypes.HWND]
user32.GetDC.restype = wintypes.HDC
user32.ReleaseDC.argtypes = [wintypes.HWND, wintypes.HDC]
user32.ReleaseDC.restype = wintypes.INT
user32.SetCursorPos.argtypes = [wintypes.INT, wintypes.INT]
user32.SetCursorPos.restype = wintypes.BOOL
user32.SendInput.argtypes = [wintypes.UINT, ctypes.POINTER(INPUT), ctypes.c_int]
user32.SendInput.restype = wintypes.UINT
user32.SetProcessDpiAwarenessContext.argtypes = [wintypes.HANDLE]
user32.SetProcessDpiAwarenessContext.restype = wintypes.BOOL
gdi32.CreateCompatibleDC.argtypes = [wintypes.HDC]
gdi32.CreateCompatibleDC.restype = wintypes.HDC
gdi32.DeleteDC.argtypes = [wintypes.HDC]
gdi32.DeleteDC.restype = wintypes.BOOL
gdi32.SelectObject.argtypes = [wintypes.HDC, wintypes.HGDIOBJ]
gdi32.SelectObject.restype = wintypes.HGDIOBJ
gdi32.DeleteObject.argtypes = [wintypes.HGDIOBJ]
gdi32.DeleteObject.restype = wintypes.BOOL
gdi32.CreateDIBSection.argtypes = [wintypes.HDC, ctypes.POINTER(BITMAPINFO), wintypes.UINT,
                                    ctypes.POINTER(ctypes.c_void_p), wintypes.HANDLE, wintypes.DWORD]
gdi32.CreateDIBSection.restype = wintypes.HBITMAP
gdi32.StretchBlt.argtypes = [wintypes.HDC, wintypes.INT, wintypes.INT, wintypes.INT, wintypes.INT,
                             wintypes.HDC, wintypes.INT, wintypes.INT, wintypes.INT, wintypes.INT, wintypes.DWORD]
gdi32.StretchBlt.restype = wintypes.BOOL
gdi32.SetStretchBltMode.argtypes = [wintypes.HDC, wintypes.INT]
gdi32.SetStretchBltMode.restype = wintypes.INT
gdi32.SetBrushOrgEx.argtypes = [wintypes.HDC, wintypes.INT, wintypes.INT, ctypes.POINTER(POINT)]
gdi32.SetBrushOrgEx.restype = wintypes.BOOL

# ============================================================================
# WINDOWS PRIMITIVES (unchanged)
# ============================================================================

def init_dpi() -> None:
    user32.SetProcessDpiAwarenessContext(DPI_AWARENESS_CONTEXT_PER_MONITOR_AWARE_V2)

def get_screen_size() -> Tuple[int, int]:
    w = user32.GetSystemMetrics(SM_CXSCREEN)
    h = user32.GetSystemMetrics(SM_CYSCREEN)
    return (w if w > 0 else 1920, h if h > 0 else 1080)

def png_pack(tag: bytes, data: bytes) -> bytes:
    chunk = tag + data
    return struct.pack("!I", len(data)) + chunk + struct.pack("!I", zlib.crc32(chunk) & 0xFFFFFFFF)

def rgb_to_png(rgb: bytes, w: int, h: int) -> bytes:
    raw = bytearray(b"".join(b"\x00" + rgb[y * w * 3:(y + 1) * w * 3] for y in range(h)))
    compressed = zlib.compress(bytes(raw), level=6)
    png = bytearray(b"\x89PNG\r\n\x1a\n")
    png.extend(png_pack(b"IHDR", struct.pack("!IIBBBBB", w, h, 8, 2, 0, 0, 0)))
    png.extend(png_pack(b"IDAT", compressed))
    png.extend(png_pack(b"IEND", b""))
    return bytes(png)

def draw_cursor(hdc_mem: int, sw: int, sh: int, dw: int, dh: int) -> None:
    ci = CURSORINFO(cbSize=ctypes.sizeof(CURSORINFO))
    if not user32.GetCursorInfo(ctypes.byref(ci)) or not (ci.flags & CURSOR_SHOWING):
        return
    ii = ICONINFO()
    if not user32.GetIconInfo(ci.hCursor, ctypes.byref(ii)):
        return
    try:
        cx = int(ci.ptScreenPos.x) - int(ii.xHotspot)
        cy = int(ci.ptScreenPos.y) - int(ii.yHotspot)
        dx = int(round(cx * (dw / float(sw))))
        dy = int(round(cy * (dh / float(sh))))
        user32.DrawIconEx(hdc_mem, dx, dy, ci.hCursor, 0, 0, 0, None, DI_NORMAL)
    finally:
        if ii.hbmMask:
            gdi32.DeleteObject(ii.hbmMask)
        if ii.hbmColor:
            gdi32.DeleteObject(ii.hbmColor)

def capture_png(tw: int, th: int) -> Tuple[bytes, int, int]:
    sw, sh = get_screen_size()
    hdc_scr = user32.GetDC(None)
    if not hdc_scr:
        raise RuntimeError("GetDC failed")
    hdc_mem = gdi32.CreateCompatibleDC(hdc_scr)
    if not hdc_mem:
        user32.ReleaseDC(None, hdc_scr)
        raise RuntimeError("CreateCompatibleDC failed")
    
    bmi = BITMAPINFO()
    bmi.bmiHeader.biSize = ctypes.sizeof(BITMAPINFOHEADER)
    bmi.bmiHeader.biWidth, bmi.bmiHeader.biHeight = tw, -th
    bmi.bmiHeader.biPlanes, bmi.bmiHeader.biBitCount = 1, 32
    bmi.bmiHeader.biCompression = BI_RGB
    bits = ctypes.c_void_p()
    hbm = gdi32.CreateDIBSection(hdc_scr, ctypes.byref(bmi), DIB_RGB_COLORS, ctypes.byref(bits), None, 0)
    if not hbm or not bits:
        gdi32.DeleteDC(hdc_mem)
        user32.ReleaseDC(None, hdc_scr)
        raise RuntimeError("CreateDIBSection failed")
    
    old = gdi32.SelectObject(hdc_mem, hbm)
    gdi32.SetStretchBltMode(hdc_mem, HALFTONE)
    gdi32.SetBrushOrgEx(hdc_mem, 0, 0, None)
    if not gdi32.StretchBlt(hdc_mem, 0, 0, tw, th, hdc_scr, 0, 0, sw, sh, SRCCOPY):
        gdi32.SelectObject(hdc_mem, old)
        gdi32.DeleteObject(hbm)
        gdi32.DeleteDC(hdc_mem)
        user32.ReleaseDC(None, hdc_scr)
        raise RuntimeError("StretchBlt failed")
    
    draw_cursor(hdc_mem, sw, sh, tw, th)
    raw = bytes((ctypes.c_ubyte * (tw * th * 4)).from_address(bits.value))
    gdi32.SelectObject(hdc_mem, old)
    gdi32.DeleteObject(hbm)
    gdi32.DeleteDC(hdc_mem)
    user32.ReleaseDC(None, hdc_scr)
    
    rgb = bytearray(tw * th * 3)
    for i in range(tw * th):
        rgb[i * 3:i * 3 + 3] = [raw[i * 4 + 2], raw[i * 4 + 1], raw[i * 4 + 0]]
    return rgb_to_png(bytes(rgb), tw, th), sw, sh

def save_screenshot(png: bytes, turn: int) -> str:
    os.makedirs(DUMP_DIR, exist_ok=True)
    path = os.path.join(DUMP_DIR, f"{DUMP_PREFIX}{turn:04d}.png")
    with open(path, "wb") as f:
        f.write(png)
    return path

def send_input(inputs) -> None:
    arr = (INPUT * len(inputs))(*inputs)
    if user32.SendInput(len(inputs), arr, ctypes.sizeof(INPUT)) != len(inputs):
        raise RuntimeError("SendInput failed")

def move_mouse(x: int, y: int) -> None:
    user32.SetCursorPos(int(x), int(y))

def click() -> None:
    send_input([
        INPUT(type=INPUT_MOUSE, ii=INPUT_I(mi=MOUSEINPUT(dx=0, dy=0, mouseData=0, dwFlags=MOUSEEVENTF_LEFTDOWN, time=0, dwExtraInfo=0))),
        INPUT(type=INPUT_MOUSE, ii=INPUT_I(mi=MOUSEINPUT(dx=0, dy=0, mouseData=0, dwFlags=MOUSEEVENTF_LEFTUP, time=0, dwExtraInfo=0)))
    ])

def double_click() -> None:
    click()
    time.sleep(TIMING_CLICK_DOUBLE)
    click()

def right_click() -> None:
    send_input([
        INPUT(type=INPUT_MOUSE, ii=INPUT_I(mi=MOUSEINPUT(dx=0, dy=0, mouseData=0, dwFlags=MOUSEEVENTF_RIGHTDOWN, time=0, dwExtraInfo=0))),
        INPUT(type=INPUT_MOUSE, ii=INPUT_I(mi=MOUSEINPUT(dx=0, dy=0, mouseData=0, dwFlags=MOUSEEVENTF_RIGHTUP, time=0, dwExtraInfo=0)))
    ])

def drag(x1: int, y1: int, x2: int, y2: int) -> None:
    move_mouse(x1, y1)
    time.sleep(TIMING_DRAG_PREPARE)
    send_input([INPUT(type=INPUT_MOUSE, ii=INPUT_I(mi=MOUSEINPUT(dx=0, dy=0, mouseData=0, dwFlags=MOUSEEVENTF_LEFTDOWN, time=0, dwExtraInfo=0)))])
    time.sleep(TIMING_CURSOR_SETTLE)
    steps = 20
    for i in range(steps + 1):
        t = i / float(steps)
        x = int(x1 + (x2 - x1) * t)
        y = int(y1 + (y2 - y1) * t)
        move_mouse(x, y)
        time.sleep(TIMING_DRAG_STEP)
    time.sleep(TIMING_CURSOR_SETTLE)
    send_input([INPUT(type=INPUT_MOUSE, ii=INPUT_I(mi=MOUSEINPUT(dx=0, dy=0, mouseData=0, dwFlags=MOUSEEVENTF_LEFTUP, time=0, dwExtraInfo=0)))])

def scroll_action(direction: int) -> None:
    delta = 120 if direction > 0 else -120
    send_input([INPUT(type=INPUT_MOUSE, ii=INPUT_I(mi=MOUSEINPUT(dx=0, dy=0, mouseData=delta, dwFlags=MOUSEEVENTF_WHEEL, time=0, dwExtraInfo=0)))])

def type_text(text: str) -> None:
    for ch in text:
        code = ord(ch)
        send_input([
            INPUT(type=INPUT_KEYBOARD, ii=INPUT_I(ki=KEYBDINPUT(wVk=0, wScan=code, dwFlags=KEYEVENTF_UNICODE, time=0, dwExtraInfo=0))),
            INPUT(type=INPUT_KEYBOARD, ii=INPUT_I(ki=KEYBDINPUT(wVk=0, wScan=code, dwFlags=KEYEVENTF_UNICODE | KEYEVENTF_KEYUP, time=0, dwExtraInfo=0)))
        ])
        time.sleep(TIMING_INPUT_CHAR)

def press_key(key: str) -> None:
    parts = [p.strip() for p in key.strip().lower().split("+") if p.strip()]
    vks = [VK_MAP[p] for p in parts]
    send_input([INPUT(type=INPUT_KEYBOARD, ii=INPUT_I(ki=KEYBDINPUT(wVk=vk, wScan=0, dwFlags=0, time=0, dwExtraInfo=0))) for vk in vks] +
               [INPUT(type=INPUT_KEYBOARD, ii=INPUT_I(ki=KEYBDINPUT(wVk=vk, wScan=0, dwFlags=KEYEVENTF_KEYUP, time=0, dwExtraInfo=0))) for vk in reversed(vks)])

# ============================================================================
# THREE-BODY HIERARCHY PERSONAS
# ============================================================================

STRATEGIST_PROMPT = """You are a **General** (strategic command) for Windows desktop automation.

INPUT: User mission description + initial screenshot.

OUTPUT (structured doctrine, 6 sections):

1. MISSION RESTATEMENT
   [Concise rewrite of user goal in operational terms]

2. PHASE 1: RECONNAISSANCE
   [What must be observed/verified before action - UI state, window presence, cursor position]

3. INTERMEDIATE PHASE OPTIONS (4-7 options)
   [List possible execution paths based on recon findings - each 1-2 sentences]
   Example format:
   - Option A: If calculator visible → direct interaction
   - Option B: If desktop empty → spawn calculator via Windows menu
   - Option C: If wrong app open → close and retry

4. FINAL PHASE: VERIFICATION
   [How success will be confirmed - visual evidence, state checks]

5. OPERATIONAL RISKS
   [Context-specific hazards - always include UI-specific risks]
   Examples:
   - Small brush in Paint → drawings invisible (use 5+ clicks or increase brush)
   - Dropdown menus auto-close → must act within 2s
   - Browser JS delay → wait for full page load

6. FIELD COMMANDER DIRECTIVES
   [High-level guidance for Tactician persona - 150 words max]
   Include:
   - Phase transition criteria
   - Tool selection principles per phase
   - Risk mitigation strategies
   - When to include report_completion tool (verification phase only)

CRITICAL: Be concise. No conversational filler. Output exactly 6 sections."""

TACTICIAN_PROMPT_TEMPLATE = """You are a **Field Commander** managing phase transitions for mission:

{mission}

STRATEGIC DOCTRINE:
{doctrine}

YOUR ROLE:
- Assess current phase via screenshot analysis
- Decide when to transition phases based on visual evidence
- Spawn phase-specific Executor configurations using tools
- Monitor execution progress and adapt tactics

TOOLS AT YOUR DISPOSAL:
1. spawn_executor_prompt - Create/update Executor's system prompt for current phase
2. update_phase_tools - Define available tool subset for Executor

DECISION FRAMEWORK:
- RECONNAISSANCE: Minimal tools (navigation only), no report_completion
- EXECUTION: Full relevant toolset for task, no report_completion
- VERIFICATION: All tools including report_completion

OUTPUT:
- Use spawn_executor_prompt when phase transitions occur
- Use update_phase_tools to match tools to phase needs
- Provide brief text status if no transition needed

CRITICAL: Only spawn new executor when phase actually changes based on visual evidence."""

EXECUTOR_FALLBACK_PROMPT = """You are an **Operative** executing desktop automation actions.

Execute ONE precise action per turn based on current phase goals.

COORDINATES:
- Use [x,y] format only (center point)
- 0-1000 normalized scale
- (0,0)=top-left, (1000,1000)=bottom-right

JUSTIFICATION (per action):
- What I see (visual evidence)
- Why this action (reasoning)
- Expected outcome (prediction)

CRITICAL:
- Single action only - no chaining
- Only interact with visible UI elements
- Provide detailed 50+ word justification"""

# ============================================================================
# TOOL DEFINITIONS
# ============================================================================

JUSTIFICATION_DESC = "Brief reasoning (30-50 words): what you see, why this action, expected outcome"

# NEW: Tactician-only tools (not available to Executor)
TACTICIAN_TOOLS = [
    {
        "type": "function",
        "function": {
            "name": "spawn_executor_prompt",
            "description": "Create or update Executor's system prompt for current phase",
            "parameters": {
                "type": "object",
                "properties": {
                    "prompt": {
                        "type": "string",
                        "description": "Complete system prompt for Executor (200-400 words). Must include: phase goals, precision requirements, risk warnings, coordinate system reminder, justification requirements."
                    },
                    "phase": {
                        "type": "string",
                        "description": "Phase name (e.g., 'RECONNAISSANCE', 'EXECUTION_NOTEPAD', 'VERIFICATION')"
                    },
                    "rationale": {
                        "type": "string",
                        "description": "Why this prompt update is needed (50-100 words)"
                    }
                },
                "required": ["prompt", "phase", "rationale"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "update_phase_tools",
            "description": "Define available tool subset for Executor in current phase",
            "parameters": {
                "type": "object",
                "properties": {
                    "tool_names": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": "List of tool names to enable (e.g., ['click_element', 'press_key', 'report_completion'])"
                    },
                    "rationale": {
                        "type": "string",
                        "description": "Why these specific tools for this phase (50 words)"
                    }
                },
                "required": ["tool_names", "rationale"]
            }
        }
    }
]

# Executor action tools
EXECUTOR_TOOLS = [
    {
        "type": "function",
        "function": {
            "name": "report_completion",
            "description": "Report task completion (ONLY use in verification phase)",
            "parameters": {
                "type": "object",
                "properties": {
                    "evidence": {"type": "string", "description": "Visual proof of completion (100 words)"}
                },
                "required": ["evidence"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "click_element",
            "description": "Click on UI element",
            "parameters": {
                "type": "object",
                "properties": {
                    "justification": {"type": "string", "description": JUSTIFICATION_DESC},
                    "label": {"type": "string", "description": "Element name"},
                    "position": {
                        "type": "array",
                        "items": {"type": "number"},
                        "minItems": 2,
                        "maxItems": 2,
                        "description": "Center point [x,y] in 0-1000 scale"
                    }
                },
                "required": ["justification", "label", "position"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "double_click_element",
            "description": "Double-click element",
            "parameters": {
                "type": "object",
                "properties": {
                    "justification": {"type": "string", "description": JUSTIFICATION_DESC},
                    "label": {"type": "string", "description": "Element name"},
                    "position": {
                        "type": "array",
                        "items": {"type": "number"},
                        "minItems": 2,
                        "maxItems": 2,
                        "description": "Center point [x,y] in 0-1000 scale"
                    }
                },
                "required": ["justification", "label", "position"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "right_click_element",
            "description": "Right-click element",
            "parameters": {
                "type": "object",
                "properties": {
                    "justification": {"type": "string", "description": JUSTIFICATION_DESC},
                    "label": {"type": "string", "description": "Element name"},
                    "position": {
                        "type": "array",
                        "items": {"type": "number"},
                        "minItems": 2,
                        "maxItems": 2,
                        "description": "Center point [x,y] in 0-1000 scale"
                    }
                },
                "required": ["justification", "label", "position"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "drag_element",
            "description": "Drag from start to end",
            "parameters": {
                "type": "object",
                "properties": {
                    "justification": {"type": "string", "description": JUSTIFICATION_DESC},
                    "label": {"type": "string", "description": "Element being dragged"},
                    "start": {"type": "array", "items": {"type": "number"}, "minItems": 2, "maxItems": 2},
                    "end": {"type": "array", "items": {"type": "number"}, "minItems": 2, "maxItems": 2}
                },
                "required": ["justification", "label", "start", "end"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "type_text",
            "description": "Type text",
            "parameters": {
                "type": "object",
                "properties": {
                    "justification": {"type": "string", "description": JUSTIFICATION_DESC},
                    "text": {"type": "string", "description": "Text to type"}
                },
                "required": ["justification", "text"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "press_key",
            "description": "Press keyboard key or combo",
            "parameters": {
                "type": "object",
                "properties": {
                    "justification": {"type": "string", "description": JUSTIFICATION_DESC},
                    "key": {"type": "string", "description": "Key name or combo (e.g. 'enter', 'ctrl+c', 'windows')"}
                },
                "required": ["justification", "key"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "scroll_down",
            "description": "Scroll downward",
            "parameters": {
                "type": "object",
                "properties": {
                    "justification": {"type": "string", "description": JUSTIFICATION_DESC}
                },
                "required": ["justification"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "scroll_up",
            "description": "Scroll upward",
            "parameters": {
                "type": "object",
                "properties": {
                    "justification": {"type": "string", "description": JUSTIFICATION_DESC}
                },
                "required": ["justification"]
            }
        }
    }
]

# Tool name to definition mapping
TOOL_REGISTRY = {tool["function"]["name"]: tool for tool in EXECUTOR_TOOLS}

CLICK_TOOLS_MAP = {
    "click_element": (click, "Clicked"),
    "double_click_element": (double_click, "Double-clicked"),
    "right_click_element": (right_click, "Right-clicked")
}

# ============================================================================
# AGENT STATE
# ============================================================================

class AgentState:
    def __init__(self, task: str, initial_screenshot: bytes, screen_dims: Tuple[int, int]):
        self.task = task
        self.screenshot = initial_screenshot
        self.screen_dims = screen_dims
        self.turn = 0
        self.history: List[Dict[str, Any]] = []
        
        # Three-body hierarchy state
        self.strategist_doctrine: str = ""
        self.tactician_prompt: str = ""
        self.current_executor_prompt: Optional[str] = None
        self.current_phase: str = "INIT"
        self.current_tool_names: List[str] = []  # Tool names, not full definitions
        
        if ENABLE_FULL_ARCHIVE:
            self.full_archive: List[Dict[str, Any]] = []
    
    def increment_turn(self):
        self.turn += 1
    
    def update_screenshot(self, png: bytes):
        self.screenshot = png
    
    def add_history(self, tool: str, args: Dict, justification: str, result: str, screenshot_path: str):
        entry = {
            "turn": self.turn,
            "tool": tool,
            "args": args,
            "justification": justification,
            "result": result,
            "screenshot": screenshot_path
        }
        self.history.append(entry)
        
        if ENABLE_FULL_ARCHIVE:
            self.full_archive.append(entry)
    
    def update_executor_context(self, prompt: str, phase: str, tool_names: List[str]):
        """Update executor configuration from tactician tool calls."""
        self.current_executor_prompt = prompt
        self.current_phase = phase
        self.current_tool_names = tool_names
    
    def get_executor_tools(self) -> List[Dict]:
        """Filter EXECUTOR_TOOLS to only include current phase tools."""
        if not self.current_tool_names:
            return []
        return [TOOL_REGISTRY[name] for name in self.current_tool_names if name in TOOL_REGISTRY]

# ============================================================================
# UTILITY FUNCTIONS
# ============================================================================

def norm_to_px(xn: float, yn: float, sw: int, sh: int) -> Tuple[int, int]:
    xn = max(0.0, min(1000.0, xn))
    yn = max(0.0, min(1000.0, yn))
    px = min(int(round((xn / 1000.0) * sw)), sw - 1)
    py = min(int(round((yn / 1000.0) * sh)), sh - 1)
    return (px, py)

def post_json(payload: Dict[str, Any]) -> Dict[str, Any]:
    data = json.dumps(payload, ensure_ascii=True).encode("utf-8")
    req = urllib.request.Request(LMSTUDIO_ENDPOINT, data=data, headers={"Content-Type": "application/json"}, method="POST")
    try:
        with urllib.request.urlopen(req, timeout=LMSTUDIO_TIMEOUT) as resp:
            return json.loads(resp.read().decode("utf-8"))
    except Exception as e:
        print(f"API failed: {e}")
        raise

def build_history_text(state: AgentState) -> str:
    """Compact history with doctrine context."""
    lines = [f"MISSION: {state.task}\n"]
    
    if state.strategist_doctrine:
        lines.append(f"DOCTRINE:\n{state.strategist_doctrine[:400]}...\n")
    
    lines.append(f"CURRENT PHASE: {state.current_phase}\n")
    
    if state.history:
        lines.append("RECENT ACTIONS:")
        for h in state.history[-8:]:
            target = h['args'].get('label', h['args'].get('text', h['args'].get('key', '')))[:30]
            outcome = h['result'][:60]
            lines.append(f"  T{h['turn']}: {h['tool']}({target}) → {outcome}")
    
    # Loop warnings
    if ENABLE_ACTIVE_LOOP_PREVENTION and len(state.history) >= 2:
        recent = [h for h in state.history[-4:]]
        if len(recent) >= 2:
            last = recent[-1]
            last_sig = (last['tool'], last['args'].get('label', ''))
            matches = sum(1 for h in recent if (h['tool'], h['args'].get('label', '')) == last_sig)
            
            if matches >= LOOP_DETECTION_THRESHOLD:
                lines.append(f"\n⚠️ LOOP: {last['tool']} on '{last['args'].get('label', '')}' repeated {matches}× - CHANGE APPROACH ⚠️")
    
    return "\n".join(lines)

def detect_terminal_loop(state: AgentState) -> bool:
    if not ENABLE_ACTIVE_LOOP_PREVENTION or len(state.history) < 4:
        return False
    
    recent = [h for h in state.history[-5:]]
    
    if len(recent) < LOOP_DETECTION_THRESHOLD:
        return False
    
    last = recent[-1]
    last_sig = (last["tool"], last["args"].get("label", ""))
    matches = sum(1 for h in recent if (h["tool"], h["args"].get("label", "")) == last_sig)
    
    return matches >= LOOP_DETECTION_THRESHOLD

def prune_history(history: List[Dict], max_items: int) -> List[Dict]:
    if len(history) <= max_items:
        return history
    
    recent = history[-max_items:]
    return recent

# ============================================================================
# TOOL EXECUTION
# ============================================================================

def execute_tool_action(name: str, args: Dict[str, Any], sw: int, sh: int) -> str:
    """Execute single tool without screenshot capture."""
    
    if name in CLICK_TOOLS_MAP:
        label = args.get("label", "")
        position = args.get("position")
        if not label or not position or len(position) != 2:
            return "Error: label and position [x,y] required"
        
        px, py = norm_to_px(float(position[0]), float(position[1]), sw, sh)
        move_mouse(px, py)
        time.sleep(TIMING_CURSOR_SETTLE)
        action_func, action_name = CLICK_TOOLS_MAP[name]
        action_func()
        time.sleep(TIMING_UI_RENDER)
        return f"{action_name}: {label}"
    
    elif name == "drag_element":
        label = args.get("label", "")
        start = args.get("start")
        end = args.get("end")
        if not label or not start or not end or len(start) != 2 or len(end) != 2:
            return "Error: label, start [x,y], end [x,y] required"
        
        sx, sy = norm_to_px(float(start[0]), float(start[1]), sw, sh)
        ex, ey = norm_to_px(float(end[0]), float(end[1]), sw, sh)
        drag(sx, sy, ex, ey)
        time.sleep(TIMING_UI_RENDER)
        return f"Dragged {label}"
    
    elif name == "type_text":
        text = str(args.get("text", ""))
        if not text:
            return "Error: text required"
        type_text(text)
        time.sleep(TIMING_UI_RENDER)
        return f"Typed: {text[:50]}"
    
    elif name == "press_key":
        key = str(args.get("key", "")).strip().lower()
        if not key:
            return "Error: key required"
        
        parts = [p.strip() for p in key.split("+")]
        for part in parts:
            if part not in VK_MAP:
                return f"Error: Unknown key '{part}'"
        
        press_key(key)
        time.sleep(TIMING_UI_RENDER)
        return f"Pressed: {key}"
    
    elif name == "scroll_down":
        move_mouse(sw // 2, sh // 2)
        time.sleep(TIMING_CURSOR_SETTLE)
        scroll_action(-1)
        time.sleep(TIMING_UI_RENDER)
        return "Scrolled down"
    
    elif name == "scroll_up":
        move_mouse(sw // 2, sh // 2)
        time.sleep(TIMING_CURSOR_SETTLE)
        scroll_action(1)
        time.sleep(TIMING_UI_RENDER)
        return "Scrolled up"
    
    else:
        return f"Error: unknown tool '{name}'"

# ============================================================================
# PERSONA INVOCATIONS
# ============================================================================

def invoke_strategist(task: str, screenshot: bytes) -> str:
    """Call General once to produce strategic doctrine."""
    b64 = base64.b64encode(screenshot).decode("ascii")
    
    try:
        resp = post_json({
            "model": LMSTUDIO_MODEL,
            "messages": [
                {"role": "system", "content": STRATEGIST_PROMPT},
                {"role": "user", "content": [
                    {"type": "text", "text": f"Mission: {task}"},
                    {"type": "image_url", "image_url": {"url": f"data:image/png;base64,{b64}"}}
                ]}
            ],
            "temperature": 0.3,
            "max_tokens": 1200
        })
        
        return resp["choices"][0]["message"].get("content", "").strip()
    except Exception as e:
        return f"Strategist invocation failed: {e}"

def invoke_tactician(state: AgentState) -> Tuple[Optional[str], Optional[str], Optional[List[str]]]:
    """
    Call Field Commander for oversight and phase management.
    Returns: (executor_prompt, phase_name, tool_names) or (None, None, None) if no update.
    """
    b64 = base64.b64encode(state.screenshot).decode("ascii")
    history_text = build_history_text(state)
    
    prompt = f"""{history_text}

CURRENT SCREENSHOT: [below]

ASSESSMENT REQUIRED:
1. Current phase status (complete/in-progress/blocked)
2. If phase transition needed: use spawn_executor_prompt + update_phase_tools
3. If continuing: provide brief text status only

TOOL USAGE:
- spawn_executor_prompt: Create new executor configuration for phase
- update_phase_tools: Specify tool names (NOT full definitions)

REMEMBER: Include 'report_completion' in tools ONLY during verification phase."""
    
    try:
        resp = post_json({
            "model": LMSTUDIO_MODEL,
            "messages": [
                {"role": "system", "content": state.tactician_prompt},
                {"role": "user", "content": [
                    {"type": "text", "text": prompt},
                    {"type": "image_url", "image_url": {"url": f"data:image/png;base64,{b64}"}}
                ]}
            ],
            "tools": TACTICIAN_TOOLS,
            "tool_choice": "auto",
            "temperature": 0.4,
            "max_tokens": 800
        })
        
        msg = resp["choices"][0]["message"]
        tool_calls = msg.get("tool_calls")
        
        if not tool_calls:
            # No phase transition - status update only
            print(f"Tactician status: {msg.get('content', 'No updates')[:150]}")
            return (None, None, None)
        
        # Extract spawn_executor_prompt and update_phase_tools
        executor_prompt = None
        phase_name = None
        tool_names = None
        
        for tc in tool_calls:
            tool_name = tc["function"]["name"]
            try:
                tool_args = json.loads(tc["function"]["arguments"])
            except json.JSONDecodeError:
                continue
            
            if tool_name == "spawn_executor_prompt":
                executor_prompt = tool_args.get("prompt")
                phase_name = tool_args.get("phase", "UNKNOWN")
                rationale = tool_args.get("rationale", "")
                print(f"\n✓ Executor prompt spawned for phase: {phase_name}")
                print(f"  Rationale: {rationale[:100]}...")
            
            elif tool_name == "update_phase_tools":
                tool_names = tool_args.get("tool_names", [])
                rationale = tool_args.get("rationale", "")
                print(f"✓ Tools updated: {tool_names}")
                print(f"  Rationale: {rationale[:100]}...")
        
        return (executor_prompt, phase_name, tool_names)
    
    except Exception as e:
        print(f"Tactician call failed: {e}")
        return (None, None, None)

def invoke_executor(state: AgentState) -> Optional[Dict]:
    """Call Operative for single action execution."""
    if not state.current_executor_prompt:
        print("⚠️ No executor prompt available - waiting for tactician")
        return None
    
    executor_tools = state.get_executor_tools()
    if not executor_tools:
        print("⚠️ No tools available - using fallback")
        executor_tools = EXECUTOR_TOOLS
    
    b64 = base64.b64encode(state.screenshot).decode("ascii")
    history_text = build_history_text(state)
    
    prompt = f"""{history_text}

CURRENT SCREENSHOT: [below]

EXECUTE: ONE precise action based on current phase goals.
Output single tool call with detailed justification (50+ words)."""
    
    is_looping = detect_terminal_loop(state)
    temperature = LMSTUDIO_TEMPERATURE * 1.5 if is_looping else LMSTUDIO_TEMPERATURE
    
    try:
        resp = post_json({
            "model": LMSTUDIO_MODEL,
            "messages": [
                {"role": "system", "content": state.current_executor_prompt},
                {"role": "user", "content": [
                    {"type": "text", "text": prompt},
                    {"type": "image_url", "image_url": {"url": f"data:image/png;base64,{b64}"}}
                ]}
            ],
            "tools": executor_tools,
            "tool_choice": "auto",
            "temperature": temperature,
            "max_tokens": LMSTUDIO_MAX_TOKENS
        })
        
        msg = resp["choices"][0]["message"]
        tool_calls = msg.get("tool_calls")
        
        if not tool_calls:
            print(f"Executor returned no tool calls: {msg.get('content', '')[:100]}")
            return None
        
        # CRITICAL: Take only first tool call (single action)
        return tool_calls[0]
    
    except Exception as e:
        print(f"Executor call failed: {e}")
        return None

# ============================================================================
# MAIN AGENT LOOP
# ============================================================================

def run_agent(state: AgentState) -> str:
    """Three-body hierarchy execution loop."""
    
    for iteration in range(MAX_STEPS):
        state.increment_turn()
        
        # Capture fresh screenshot
        png, sw, sh = capture_png(AGENT_IMAGE_W, AGENT_IMAGE_H)
        screenshot_path = save_screenshot(png, state.turn)
        state.update_screenshot(png)
        
        print(f"\n{'='*70}")
        print(f"TURN {state.turn} | Phase: {state.current_phase}")
        print(f"{'='*70}")
        
        # TACTICIAN OVERSIGHT (turn 1 and every N turns)
        if state.turn == 1 or state.turn % TACTICIAN_INTERVAL == 0:
            print(f"\n[TACTICIAN] Field Commander oversight...")
            
            executor_prompt, phase_name, tool_names = invoke_tactician(state)
            
            if executor_prompt and phase_name and tool_names:
                print(f"\n✓ Phase Transition: {state.current_phase} → {phase_name}")
                print(f"✓ Executor reconfigured with {len(tool_names)} tools")
                state.update_executor_context(executor_prompt, phase_name, tool_names)
            elif state.turn == 1:
                # Fallback: Use default config if tactician fails on first turn
                print("⚠️ Tactician tool calls missing - using fallback executor config")
                state.update_executor_context(
                    EXECUTOR_FALLBACK_PROMPT,
                    "FALLBACK",
                    ["click_element", "press_key", "type_text", "scroll_down", "scroll_up"]
                )
            
            time.sleep(TIMING_TURN_DELAY)
        
        # EXECUTOR ACTION (every turn after tactician initializes)
        if state.current_executor_prompt:
            print(f"\n[EXECUTOR] Operative action...")
            
            tool_call = invoke_executor(state)
            
            if not tool_call:
                print("⚠️ No action taken this turn")
                time.sleep(TIMING_TURN_DELAY)
                continue
            
            tool_name = tool_call["function"]["name"]
            
            try:
                tool_args = json.loads(tool_call["function"]["arguments"])
            except json.JSONDecodeError as e:
                print(f"✗ Argument parse error: {e}")
                time.sleep(TIMING_TURN_DELAY)
                continue
            
            justification = tool_args.get("justification", "")
            
            # Completion check
            if tool_name == "report_completion":
                evidence = tool_args.get("evidence", "")
                if len(evidence.strip()) < 100:
                    print(f"✗ Insufficient completion evidence")
                    time.sleep(TIMING_TURN_DELAY)
                    continue
                
                print(f"\n{'='*70}")
                print("MISSION COMPLETE")
                print(f"{'='*70}")
                print(f"Evidence: {evidence}")
                print(f"{'='*70}\n")
                return f"Completed in {state.turn} turns"
            
            # Execute action
            print(f"\nAction: {tool_name}")
            print(f"Target: {tool_args.get('label', tool_args.get('text', tool_args.get('key', ''))[:30])}")
            
            result = execute_tool_action(tool_name, tool_args, sw, sh)
            
            if result.startswith("Error:"):
                print(f"✗ {result}")
            else:
                print(f"✓ {result}")
            
            # Record history
            state.add_history(
                tool=tool_name,
                args=tool_args,
                justification=justification,
                result=result,
                screenshot_path=screenshot_path
            )
            
            # Prune history
            state.history = prune_history(state.history, MAX_HISTORY_ITEMS)
        else:
            print("⚠️ Waiting for tactician initialization...")
        
        time.sleep(TIMING_TURN_DELAY)
    
    return f"Max iterations reached ({MAX_STEPS} turns)"

# ============================================================================
# MAIN ENTRY
# ============================================================================

def main() -> None:
    init_dpi()
    
    print("\n" + "="*70)
    print("THREE-BODY MILITARY HIERARCHY AGENT")
    print("="*70)
    print(f"\nConfiguration:")
    print(f"  Max Steps: {MAX_STEPS}")
    print(f"  Tactician Interval: {TACTICIAN_INTERVAL} turns")
    print(f"  Single Action Mode: Enabled")
    print("="*70 + "\n")
    
    task = input("Mission: ").strip()
    if not task:
        sys.exit("Error: Mission required")
    
    # Capture initial screenshot
    png, sw, sh = capture_png(AGENT_IMAGE_W, AGENT_IMAGE_H)
    screenshot_path = save_screenshot(png, 0)
    print(f"Initial recon: {screenshot_path}\n")
    
    print("="*70)
    print("PHASE 0: STRATEGIC COMMAND")
    print("="*70 + "\n")
    
    # Invoke Strategist (General)
    strategist_output = invoke_strategist(task, png)
    print(f"Strategic Doctrine:\n{strategist_output}\n")
    
    # Build Tactician prompt
    tactician_prompt = TACTICIAN_PROMPT_TEMPLATE.format(
        mission=task,
        doctrine=strategist_output
    )
    
    print("="*70)
    print("PHASE 1: FIELD OPERATIONS")
    print("="*70 + "\n")
    
    # Initialize state
    state = AgentState(task, png, (sw, sh))
    state.strategist_doctrine = strategist_output
    state.tactician_prompt = tactician_prompt
    
    try:
        result = run_agent(state)
        
        print("\n" + "="*70)
        print("MISSION DEBRIEF")
        print("="*70)
        print(f"\nStatus: {result}")
        print(f"Total Turns: {state.turn}")
        print(f"Final Phase: {state.current_phase}")
        
        if ENABLE_FULL_ARCHIVE:
            print(f"Full Archive: {len(state.full_archive)} actions")
        
        print("="*70 + "\n")
        
    except KeyboardInterrupt:
        print("\n\n⚠️ Mission Aborted")
        print(f"Progress: {state.turn} turns in phase {state.current_phase}")
        
        if ENABLE_FULL_ARCHIVE:
            checkpoint = os.path.join(DUMP_DIR, f"checkpoint_T{state.turn}.json")
            with open(checkpoint, "w") as f:
                json.dump({
                    "task": state.task,
                    "turn": state.turn,
                    "phase": state.current_phase,
                    "strategist_doctrine": state.strategist_doctrine,
                    "tactician_prompt": state.tactician_prompt,
                    "current_executor_prompt": state.current_executor_prompt,
                    "full_archive": state.full_archive
                }, f, indent=2)
            print(f"Checkpoint saved: {checkpoint}")
        
        sys.exit(1)
    except Exception as e:
        print(f"\n⚠️ Fatal Error: {e}", file=sys.stderr)
        import traceback
        traceback.print_exc()
        raise

if __name__ == "__main__":
    main()
