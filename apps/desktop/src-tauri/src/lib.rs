// 文书通 — Tauri 桌面壳（政务文书 · 智能通办）
//
// Responsibilities:
// 1. Expose `pick_folder` / `pick_skill_file` for native dialogs.
// 2. Auto-start the local Python runtime on 127.0.0.1:8765:
//    - Release: packaged onedir sidecar under resources/runtime/
//    - Debug / fallback: repo `runtime/.venv` (dev workflow)
use std::fs::OpenOptions;
use std::io::{Read, Write};
use std::net::TcpStream;
use std::path::{Path, PathBuf};
use std::process::{Child, Command, Stdio};
use std::sync::Mutex;
use std::time::Duration;

use tauri::path::BaseDirectory;
use tauri::{Manager, RunEvent};
use tauri_plugin_dialog::DialogExt;

#[cfg(windows)]
use std::os::windows::process::CommandExt;

#[cfg(windows)]
const CREATE_NO_WINDOW: u32 = 0x0800_0000;

/// Holds the handle to the auto-spawned runtime process (if any) so it can
/// be terminated when the app exits.
struct RuntimeProcess(Mutex<Option<Child>>);

#[tauri::command]
async fn pick_folder(app: tauri::AppHandle) -> Result<Option<String>, String> {
    let folder = app.dialog().file().blocking_pick_folder();
    Ok(folder.map(|f| f.to_string()))
}

#[tauri::command]
async fn pick_skill_file(app: tauri::AppHandle) -> Result<Option<String>, String> {
    let file = app
        .dialog()
        .file()
        .add_filter("Skill 包", &["zip", "md"])
        .blocking_pick_file();
    Ok(file.map(|f| f.to_string()))
}

fn log_line(msg: &str) {
    eprintln!("{msg}");
    if let Ok(mut f) = OpenOptions::new()
        .create(true)
        .append(true)
        .open(std::env::temp_dir().join("office-agent-desktop.log"))
    {
        let _ = writeln!(f, "{msg}");
    }
}

/// Locates `runtime/` relative to the dev working directory
/// (`apps/desktop/src-tauri` during `tauri dev`). Returns `None` if it
/// cannot be found; the caller should fall back to manual startup.
fn find_runtime_dir() -> Option<PathBuf> {
    if let Ok(env_dir) = std::env::var("OFFICE_AGENT_RUNTIME_DIR") {
        let p = PathBuf::from(env_dir);
        if p.is_dir() {
            return Some(p);
        }
    }
    let candidates = [
        "../../../runtime", // apps/desktop/src-tauri -> repo root
        "../../runtime",    // when cwd is apps/desktop
        "runtime",
    ];
    for c in candidates {
        let p = PathBuf::from(c);
        if p.join("src/office_agent/app.py").is_file() {
            return p.canonicalize().ok();
        }
    }
    None
}

fn venv_python(runtime_dir: &Path) -> Option<PathBuf> {
    let unix = runtime_dir.join(".venv/bin/python");
    if unix.is_file() {
        return Some(unix);
    }
    let win = runtime_dir.join(".venv/Scripts/python.exe");
    if win.is_file() {
        return Some(win);
    }
    None
}

fn runtime_already_up() -> bool {
    TcpStream::connect_timeout(
        &"127.0.0.1:8765".parse().unwrap(),
        Duration::from_millis(300),
    )
    .is_ok()
}

fn request_runtime_shutdown() {
    if let Ok(mut stream) =
        TcpStream::connect_timeout(&"127.0.0.1:8765".parse().unwrap(), Duration::from_millis(500))
    {
        let _ = stream.set_read_timeout(Some(Duration::from_millis(800)));
        let _ = stream.set_write_timeout(Some(Duration::from_millis(500)));
        let req = b"POST /shutdown HTTP/1.1\r\nHost: 127.0.0.1\r\nContent-Length: 0\r\nConnection: close\r\n\r\n";
        let _ = stream.write_all(req);
        let mut buf = [0u8; 128];
        let _ = stream.read(&mut buf);
    }
}

fn stop_child(child: &mut Child) {
    request_runtime_shutdown();
    std::thread::sleep(Duration::from_millis(400));
    match child.try_wait() {
        Ok(Some(_)) => return,
        _ => {
            let _ = child.kill();
            let _ = child.wait();
        }
    }
}

fn sidecar_exe_name() -> &'static str {
    if cfg!(windows) {
        "office-agent-runtime.exe"
    } else {
        "office-agent-runtime"
    }
}

/// NSIS layout is `{exe_dir}/resources/runtime/…`. Tauri `resource_dir()` may
/// point at either `{exe_dir}` or `{exe_dir}/resources`, so try both.
fn find_sidecar_exe(app: &tauri::AppHandle) -> Option<PathBuf> {
    let name = sidecar_exe_name();
    let mut candidates: Vec<PathBuf> = Vec::new();

    if let Ok(exe) = std::env::current_exe() {
        if let Some(dir) = exe.parent() {
            candidates.push(dir.join("resources").join("runtime").join(name));
            candidates.push(dir.join("runtime").join(name));
        }
    }

    if let Ok(rd) = app.path().resource_dir() {
        candidates.push(rd.join("runtime").join(name));
        candidates.push(rd.join("resources").join("runtime").join(name));
        log_line(&format!("[office-agent] resource_dir={rd:?}"));
    }

    for rel in [
        format!("runtime/{name}"),
        format!("resources/runtime/{name}"),
    ] {
        if let Ok(p) = app.path().resolve(&rel, BaseDirectory::Resource) {
            candidates.push(p);
        }
    }

    for p in candidates {
        if p.is_file() {
            log_line(&format!("[office-agent] found sidecar at {p:?}"));
            return Some(p);
        }
        log_line(&format!("[office-agent] sidecar miss {p:?}"));
    }
    None
}

fn find_bundled_dir(app: &tauri::AppHandle, sidecar: &Path) -> Option<PathBuf> {
    let mut candidates: Vec<PathBuf> = Vec::new();
    if let Some(runtime_dir) = sidecar.parent() {
        // {…}/resources/runtime → {…}/resources/bundled
        if let Some(resources) = runtime_dir.parent() {
            candidates.push(resources.join("bundled"));
        }
        // {…}/runtime → {…}/bundled
        if let Some(parent) = runtime_dir.parent() {
            candidates.push(parent.join("bundled"));
        }
    }
    if let Ok(exe) = std::env::current_exe() {
        if let Some(dir) = exe.parent() {
            candidates.push(dir.join("resources").join("bundled"));
            candidates.push(dir.join("bundled"));
        }
    }
    if let Ok(rd) = app.path().resource_dir() {
        candidates.push(rd.join("bundled"));
        candidates.push(rd.join("resources").join("bundled"));
    }
    candidates.into_iter().find(|p| p.is_dir())
}

/// Production path: onedir sidecar staged under Tauri resources.
fn try_spawn_sidecar(app: &tauri::AppHandle) -> Option<Child> {
    let sidecar = find_sidecar_exe(app)?;
    let bundled = find_bundled_dir(app, &sidecar);

    let mut cmd = Command::new(&sidecar);
    cmd.args(["--host", "127.0.0.1", "--port", "8765"]);
    if let Some(parent) = sidecar.parent() {
        cmd.current_dir(parent);
    }
    if let Some(ref b) = bundled {
        cmd.env("OFFICE_AGENT_BUNDLED", b);
        log_line(&format!("[office-agent] OFFICE_AGENT_BUNDLED={b:?}"));
    }

    // Keep logs for packaged installs (stderr was previously discarded).
    let log_path = std::env::temp_dir().join("office-agent-runtime.err.log");
    match OpenOptions::new()
        .create(true)
        .append(true)
        .open(&log_path)
    {
        Ok(f) => {
            cmd.stderr(Stdio::from(f));
        }
        Err(_) => {
            cmd.stderr(Stdio::null());
        }
    }
    cmd.stdout(Stdio::null());

    #[cfg(windows)]
    {
        cmd.creation_flags(CREATE_NO_WINDOW);
    }

    match cmd.spawn() {
        Ok(c) => {
            log_line(&format!(
                "[office-agent] auto-started packaged runtime from {sidecar:?}"
            ));
            // Give uvicorn a moment before the UI's first health check.
            std::thread::sleep(Duration::from_millis(800));
            Some(c)
        }
        Err(e) => {
            log_line(&format!("[office-agent] could not start packaged runtime: {e}"));
            None
        }
    }
}

/// Dev path: `python -m office_agent` via local `.venv`.
fn try_spawn_venv() -> Option<Child> {
    let runtime_dir = find_runtime_dir()?;
    let python = venv_python(&runtime_dir)?;
    let bundled = runtime_dir
        .parent()
        .map(|root| root.join("bundled"))
        .filter(|p| p.is_dir());

    let mut cmd = Command::new(python);
    cmd.args([
        "-m",
        "office_agent",
        "--host",
        "127.0.0.1",
        "--port",
        "8765",
    ])
    .current_dir(&runtime_dir)
    .env("PYTHONPATH", runtime_dir.join("src"))
    .stdout(Stdio::null())
    .stderr(Stdio::null());
    if let Some(b) = bundled {
        cmd.env("OFFICE_AGENT_BUNDLED", b);
    }

    #[cfg(windows)]
    {
        cmd.creation_flags(CREATE_NO_WINDOW);
    }

    match cmd.spawn() {
        Ok(c) => {
            log_line(&format!(
                "[office-agent] auto-started runtime from {runtime_dir:?}"
            ));
            Some(c)
        }
        Err(e) => {
            log_line(&format!(
                "[office-agent] could not auto-start runtime: {e} (start it manually, see README)"
            ));
            None
        }
    }
}

/// Best-effort spawn of the local runtime. Never panics: any failure is
/// logged and the UI will simply show "runtime offline" until the
/// user starts it manually (see README).
fn try_spawn_runtime(app: &tauri::AppHandle) -> Option<Child> {
    if runtime_already_up() {
        log_line("[office-agent] runtime already listening on 127.0.0.1:8765 — skip auto-start");
        return None;
    }

    // Release builds prefer the packaged sidecar; debug keeps the fast venv loop.
    if !cfg!(debug_assertions) {
        if let Some(child) = try_spawn_sidecar(app) {
            return Some(child);
        }
        log_line("[office-agent] sidecar unavailable — trying local .venv fallback");
    }

    try_spawn_venv()
}

#[cfg_attr(mobile, tauri::mobile_entry_point)]
pub fn run() {
    let builder = tauri::Builder::default()
        .plugin(tauri_plugin_opener::init())
        .plugin(tauri_plugin_dialog::init())
        .invoke_handler(tauri::generate_handler![pick_folder, pick_skill_file])
        .setup(|app| {
            let child = try_spawn_runtime(app.handle());
            app.manage(RuntimeProcess(Mutex::new(child)));
            Ok(())
        });

    builder
        .build(tauri::generate_context!())
        .expect("error while building tauri application")
        .run(|app_handle, event| {
            if let RunEvent::Exit = event {
                if let Some(state) = app_handle.try_state::<RuntimeProcess>() {
                    if let Ok(mut guard) = state.0.lock() {
                        if let Some(mut child) = guard.take() {
                            stop_child(&mut child);
                        }
                    }
                }
            }
        });
}
