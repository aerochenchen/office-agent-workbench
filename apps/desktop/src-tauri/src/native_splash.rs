//! Windows-only native splash shown before WebView2 paints.
//! Uses pre-rendered BGRA frames (logo + short arc spinner) so GDI never draws spokes.

#![cfg(windows)]

use std::sync::atomic::{AtomicBool, AtomicIsize, AtomicUsize, Ordering};
use std::thread;
use std::time::Duration;

use windows_sys::Win32::Foundation::{HWND, LPARAM, LRESULT, RECT, WPARAM};
use windows_sys::Win32::Graphics::Gdi::{
    BeginPaint, BitBlt, CreateCompatibleDC, CreateDIBSection, CreateSolidBrush, DeleteDC,
    DeleteObject, EndPaint, FillRect, GetDC, InvalidateRect, ReleaseDC, SelectObject, BITMAPINFO,
    BITMAPINFOHEADER, BI_RGB, DIB_RGB_COLORS, HBITMAP, HBRUSH, PAINTSTRUCT, SRCCOPY,
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
const SPINNER_TICK_MS: u32 = 70;
const WINDOW_W: i32 = 420;
const WINDOW_H: i32 = 280;
const FRAME_COUNT: usize = 12;

static RUNNING: AtomicBool = AtomicBool::new(false);
static HWND_RAW: AtomicIsize = AtomicIsize::new(0);
static FRAME_IDX: AtomicUsize = AtomicUsize::new(0);

/// Each blob: u32le width, u32le height, then top-down BGRA pixels.
static FRAME_BGRAS: [&[u8]; FRAME_COUNT] = [
    include_bytes!("../icons/splash/frame_00.bgra"),
    include_bytes!("../icons/splash/frame_01.bgra"),
    include_bytes!("../icons/splash/frame_02.bgra"),
    include_bytes!("../icons/splash/frame_03.bgra"),
    include_bytes!("../icons/splash/frame_04.bgra"),
    include_bytes!("../icons/splash/frame_05.bgra"),
    include_bytes!("../icons/splash/frame_06.bgra"),
    include_bytes!("../icons/splash/frame_07.bgra"),
    include_bytes!("../icons/splash/frame_08.bgra"),
    include_bytes!("../icons/splash/frame_09.bgra"),
    include_bytes!("../icons/splash/frame_10.bgra"),
    include_bytes!("../icons/splash/frame_11.bgra"),
];

struct SplashBitmaps {
    frames: Vec<(HBITMAP, i32, i32)>,
}

impl SplashBitmaps {
    fn load() -> Option<Self> {
        let mut frames = Vec::with_capacity(FRAME_COUNT);
        for blob in FRAME_BGRAS {
            let (hbmp, w, h) = bgra_to_hbitmap(blob)?;
            frames.push((hbmp, w, h));
        }
        Some(Self { frames })
    }
}

impl Drop for SplashBitmaps {
    fn drop(&mut self) {
        for (hbmp, _, _) in &self.frames {
            unsafe {
                DeleteObject(*hbmp as _);
            }
        }
    }
}

fn to_wide(s: &str) -> Vec<u16> {
    s.encode_utf16().chain(std::iter::once(0)).collect()
}

fn paper_color() -> u32 {
    // COLORREF BGR for #f3f4f1
    0x00f1_f4_f3
}

fn bgra_to_hbitmap(blob: &[u8]) -> Option<(HBITMAP, i32, i32)> {
    if blob.len() < 8 {
        return None;
    }
    let width = i32::from_le_bytes(blob[0..4].try_into().ok()?);
    let height = i32::from_le_bytes(blob[4..8].try_into().ok()?);
    if width <= 0 || height <= 0 {
        return None;
    }
    let expected = 8 + (width as usize) * (height as usize) * 4;
    if blob.len() != expected {
        return None;
    }
    let pixels = &blob[8..];

    unsafe {
        let mut bmi = std::mem::zeroed::<BITMAPINFO>();
        bmi.bmiHeader = BITMAPINFOHEADER {
            biSize: std::mem::size_of::<BITMAPINFOHEADER>() as u32,
            biWidth: width,
            biHeight: -height, // top-down
            biPlanes: 1,
            biBitCount: 32,
            biCompression: BI_RGB,
            biSizeImage: 0,
            biXPelsPerMeter: 0,
            biYPelsPerMeter: 0,
            biClrUsed: 0,
            biClrImportant: 0,
        };

        let hdc = GetDC(std::ptr::null_mut());
        if hdc.is_null() {
            return None;
        }
        let mut bits: *mut core::ffi::c_void = std::ptr::null_mut();
        let hbmp = CreateDIBSection(
            hdc,
            &bmi,
            DIB_RGB_COLORS,
            &mut bits,
            std::ptr::null_mut(),
            0,
        );
        ReleaseDC(std::ptr::null_mut(), hdc);
        if hbmp.is_null() || bits.is_null() {
            return None;
        }

        std::ptr::copy_nonoverlapping(pixels.as_ptr(), bits as *mut u8, pixels.len());
        Some((hbmp, width, height))
    }
}

unsafe extern "system" fn wnd_proc(hwnd: HWND, msg: u32, wparam: WPARAM, lparam: LPARAM) -> LRESULT {
    match msg {
        WM_TIMER => {
            if wparam == TIMER_ID as WPARAM {
                FRAME_IDX.fetch_add(1, Ordering::Relaxed);
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

thread_local! {
    static BITMAPS: std::cell::RefCell<Option<SplashBitmaps>> = std::cell::RefCell::new(None);
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

    BITMAPS.with(|cell| {
        let guard = cell.borrow();
        let Some(bmps) = guard.as_ref() else {
            let bg = CreateSolidBrush(paper_color());
            FillRect(hdc, &rect, bg);
            DeleteObject(bg as _);
            return;
        };
        let idx = FRAME_IDX.load(Ordering::Relaxed) % bmps.frames.len();
        let (hbmp, w, h) = bmps.frames[idx];
        let mem = CreateCompatibleDC(hdc);
        if mem.is_null() {
            return;
        }
        let old = SelectObject(mem, hbmp as _);
        BitBlt(hdc, 0, 0, w, h, mem, 0, 0, SRCCOPY);
        SelectObject(mem, old);
        DeleteDC(mem);
    });

    EndPaint(hwnd, &ps);
}

/// Show the native splash on a dedicated UI thread. Idempotent.
pub fn show() {
    if RUNNING.swap(true, Ordering::SeqCst) {
        return;
    }

    FRAME_IDX.store(0, Ordering::Relaxed);

    thread::spawn(|| unsafe {
        let Some(bitmaps) = SplashBitmaps::load() else {
            RUNNING.store(false, Ordering::SeqCst);
            return;
        };
        BITMAPS.with(|cell| {
            *cell.borrow_mut() = Some(bitmaps);
        });

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
            BITMAPS.with(|cell| {
                *cell.borrow_mut() = None;
            });
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

        BITMAPS.with(|cell| {
            *cell.borrow_mut() = None;
        });
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
