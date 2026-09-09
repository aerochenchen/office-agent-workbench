//! Windows-only native splash shown before WebView2 paints.
//! Runs a dedicated UI thread so the spinner keeps moving while Tauri boots.

#![cfg(windows)]

use std::sync::atomic::{AtomicBool, AtomicIsize, AtomicU32, Ordering};
use std::thread;
use std::time::Duration;

use windows_sys::Win32::Foundation::{COLORREF, HWND, LPARAM, LRESULT, RECT, SIZE, WPARAM};
use windows_sys::Win32::Graphics::Gdi::{
    AngleArc, BeginPaint, CreateFontW, CreatePen, CreateSolidBrush, DeleteObject, EndPaint,
    FillRect, GetStockObject, GetTextExtentPoint32W, InvalidateRect, SelectObject, SetBkMode,
    SetTextColor, TextOutW, CLEARTYPE_QUALITY, CLIP_DEFAULT_PRECIS, DEFAULT_CHARSET, FW_SEMIBOLD,
    HBRUSH, HFONT, NULL_BRUSH, OUT_TT_PRECIS, PAINTSTRUCT, PS_SOLID, TRANSPARENT,
};
use windows_sys::Win32::System::LibraryLoader::GetModuleHandleW;
use windows_sys::Win32::UI::WindowsAndMessaging::{
    CreateWindowExW, DefWindowProcW, DestroyWindow, DispatchMessageW, GetClientRect, GetMessageW,
    GetSystemMetrics, KillTimer, LoadCursorW, PostMessageW, PostQuitMessage, RegisterClassW,
    SetTimer, SetWindowPos, ShowWindow, TranslateMessage, CS_HREDRAW, CS_VREDRAW, IDC_ARROW, MSG,
    SM_CXSCREEN, SM_CYSCREEN, SWP_SHOWWINDOW, SW_SHOW, WM_CLOSE, WM_DESTROY, WM_PAINT, WM_TIMER,
    WNDCLASSW, WS_BORDER, WS_EX_TOOLWINDOW, WS_POPUP,
};

const TIMER_ID: usize = 1;
const SPINNER_TICK_MS: u32 = 50;
const WINDOW_W: i32 = 420;
const WINDOW_H: i32 = 280;

static RUNNING: AtomicBool = AtomicBool::new(false);
static HWND_RAW: AtomicIsize = AtomicIsize::new(0);
static ANGLE: AtomicU32 = AtomicU32::new(0);

fn to_wide(s: &str) -> Vec<u16> {
    s.encode_utf16().chain(std::iter::once(0)).collect()
}

/// windows-sys does not export the Win32 `RGB` macro.
fn rgb(r: u8, g: u8, b: u8) -> COLORREF {
    (r as COLORREF) | ((g as COLORREF) << 8) | ((b as COLORREF) << 16)
}

fn paper_color() -> COLORREF {
    rgb(0xf3, 0xf4, 0xf1)
}

fn ink_color() -> COLORREF {
    rgb(0x1a, 0x1a, 0x1a)
}

fn muted_color() -> COLORREF {
    rgb(0x4b, 0x55, 0x63)
}

fn accent_color() -> COLORREF {
    rgb(0x2f, 0x6f, 0x6a)
}

unsafe fn draw_centered_text(hdc: windows_sys::Win32::Graphics::Gdi::HDC, text: &str, y: i32, area: RECT) {
    let wide = to_wide(text);
    let len = (wide.len() - 1) as i32;
    let mut size = SIZE { cx: 0, cy: 0 };
    GetTextExtentPoint32W(hdc, wide.as_ptr(), len, &mut size);
    let x = area.left + ((area.right - area.left) - size.cx) / 2;
    TextOutW(hdc, x, y, wide.as_ptr(), len);
}

unsafe extern "system" fn wnd_proc(hwnd: HWND, msg: u32, wparam: WPARAM, lparam: LPARAM) -> LRESULT {
    match msg {
        WM_TIMER => {
            if wparam == TIMER_ID as WPARAM {
                ANGLE.fetch_add(12, Ordering::Relaxed);
                InvalidateRect(hwnd, std::ptr::null(), 0);
            }
            0
        }
        WM_PAINT => {
            paint(hwnd);
            0
        }
        WM_CLOSE => {
            DestroyWindow(hwnd);
            0
        }
        WM_DESTROY => {
            KillTimer(hwnd, TIMER_ID);
            HWND_RAW.store(0, Ordering::SeqCst);
            RUNNING.store(false, Ordering::SeqCst);
            PostQuitMessage(0);
            0
        }
        _ => DefWindowProcW(hwnd, msg, wparam, lparam),
    }
}

unsafe fn paint(hwnd: HWND) {
    let mut ps = std::mem::zeroed::<PAINTSTRUCT>();
    let hdc = BeginPaint(hwnd, &mut ps);
    if hdc.is_null() {
        return;
    }

    let mut rect = RECT {
        left: 0,
        top: 0,
        right: 0,
        bottom: 0,
    };
    GetClientRect(hwnd, &mut rect);
    let bg = CreateSolidBrush(paper_color());
    FillRect(hdc, &rect, bg);
    DeleteObject(bg as _);

    SetBkMode(hdc, TRANSPARENT as _);

    let yahei = to_wide("Microsoft YaHei UI");
    let brand_font: HFONT = CreateFontW(
        42,
        0,
        0,
        0,
        FW_SEMIBOLD as i32,
        0,
        0,
        0,
        DEFAULT_CHARSET as u32,
        OUT_TT_PRECIS as u32,
        CLIP_DEFAULT_PRECIS as u32,
        CLEARTYPE_QUALITY as u32,
        0,
        yahei.as_ptr(),
    );
    let old_font = SelectObject(hdc, brand_font as _);
    SetTextColor(hdc, ink_color());
    draw_centered_text(hdc, "文书通", 56, rect);

    let status_font: HFONT = CreateFontW(
        18,
        0,
        0,
        0,
        400,
        0,
        0,
        0,
        DEFAULT_CHARSET as u32,
        OUT_TT_PRECIS as u32,
        CLIP_DEFAULT_PRECIS as u32,
        CLEARTYPE_QUALITY as u32,
        0,
        yahei.as_ptr(),
    );
    SelectObject(hdc, status_font as _);
    SetTextColor(hdc, muted_color());
    draw_centered_text(hdc, "正在启动本地运行组件…", 118, rect);

    let angle = (ANGLE.load(Ordering::Relaxed) % 360) as f32;
    let cx = (rect.left + rect.right) / 2;
    let cy = 200;
    let r = 16u32;
    let pen = CreatePen(PS_SOLID as i32, 3, accent_color());
    let old_pen = SelectObject(hdc, pen as _);
    let null_brush = GetStockObject(NULL_BRUSH as i32);
    let old_brush = SelectObject(hdc, null_brush);
    AngleArc(hdc, cx, cy, r, angle, 270.0);
    SelectObject(hdc, old_brush);
    SelectObject(hdc, old_pen);
    DeleteObject(pen as _);

    SelectObject(hdc, old_font);
    DeleteObject(brand_font as _);
    DeleteObject(status_font as _);

    EndPaint(hwnd, &ps);
}

/// Show the native splash on a dedicated UI thread. Idempotent.
pub fn show() {
    if RUNNING.swap(true, Ordering::SeqCst) {
        return;
    }

    thread::spawn(|| unsafe {
        let instance = GetModuleHandleW(std::ptr::null());
        let class_name = to_wide("WenshutongNativeSplash");
        let wc = WNDCLASSW {
            style: CS_HREDRAW | CS_VREDRAW,
            lpfnWndProc: Some(wnd_proc),
            cbClsExtra: 0,
            cbWndExtra: 0,
            hInstance: instance,
            hIcon: std::ptr::null_mut(),
            hCursor: LoadCursorW(std::ptr::null_mut(), IDC_ARROW),
            hbrBackground: CreateSolidBrush(paper_color()) as HBRUSH,
            lpszMenuName: std::ptr::null(),
            lpszClassName: class_name.as_ptr(),
        };
        RegisterClassW(&wc);

        let screen_w = GetSystemMetrics(SM_CXSCREEN);
        let screen_h = GetSystemMetrics(SM_CYSCREEN);
        let x = (screen_w - WINDOW_W) / 2;
        let y = (screen_h - WINDOW_H) / 2;

        let title = to_wide("文书通");
        let hwnd = CreateWindowExW(
            WS_EX_TOOLWINDOW,
            class_name.as_ptr(),
            title.as_ptr(),
            WS_POPUP | WS_BORDER,
            x,
            y,
            WINDOW_W,
            WINDOW_H,
            std::ptr::null_mut(),
            std::ptr::null_mut(),
            instance,
            std::ptr::null(),
        );
        if hwnd.is_null() {
            RUNNING.store(false, Ordering::SeqCst);
            return;
        }

        HWND_RAW.store(hwnd as isize, Ordering::SeqCst);
        SetTimer(hwnd, TIMER_ID, SPINNER_TICK_MS, None);
        SetWindowPos(
            hwnd,
            std::ptr::null_mut(),
            x,
            y,
            WINDOW_W,
            WINDOW_H,
            SWP_SHOWWINDOW,
        );
        ShowWindow(hwnd, SW_SHOW);

        let mut msg = std::mem::zeroed::<MSG>();
        while GetMessageW(&mut msg, std::ptr::null_mut(), 0, 0) > 0 {
            TranslateMessage(&msg);
            DispatchMessageW(&msg);
        }
    });

    // Brief yield so the splash thread can paint once before WebView work begins.
    thread::sleep(Duration::from_millis(40));
}

/// Close the splash if it is still open. Safe to call multiple times.
pub fn dismiss() {
    let hwnd = HWND_RAW.swap(0, Ordering::SeqCst);
    if hwnd == 0 {
        RUNNING.store(false, Ordering::SeqCst);
        return;
    }
    unsafe {
        PostMessageW(hwnd as HWND, WM_CLOSE, 0, 0);
    }
}

pub fn is_running() -> bool {
    RUNNING.load(Ordering::SeqCst)
}
