// 办公智能体工作台 (Office Agent Workbench) — Tauri shell.
//
// Responsibilities:
// 1. Expose `pick_folder` so the React UI can let the user choose a
//    workspace directory via the native OS dialog.
// 2. Best-effort auto-start of the local Python runtime
//    (`uvicorn office_agent.app:app` on 127.0.0.1:8765) during dev so the
//    UI has something to talk to. This is *not* required — the runtime can
//    always be started manually per the README — so failures here are
//    logged and swallowed rather than treated as fatal.
use std::path::PathBuf;
use std::process::{Child, Command, Stdio};
use std::sync::Mutex;

use tauri::Manager;
use tauri_plugin_dialog::DialogExt;

/// Holds the handle to the auto-spawned runtime process (if any) so it can
/// be terminated when the app exits.
struct RuntimeProcess(Mutex<Option<Child>>);

#[tauri::command]
async fn pick_folder(app: tauri::AppHandle) -> Result<Option<String>, String> {
    let folder = app.dialog().file().blocking_pick_folder();
    Ok(folder.map(|f| f.to_string()))
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

fn venv_python(runtime_dir: &PathBuf) -> Option<PathBuf> {
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
    std::net::TcpStream::connect_timeout(
        &"127.0.0.1:8765".parse().unwrap(),
        std::time::Duration::from_millis(300),
    )
    .is_ok()
}

/// Best-effort spawn of the local runtime. Never panics: any failure is
/// logged to stderr and the UI will simply show "runtime offline" until the
/// user starts it manually (see README).
fn try_spawn_runtime() -> Option<Child> {
    if runtime_already_up() {
        eprintln!("[office-agent] runtime already listening on 127.0.0.1:8765 — skip auto-start");
        return None;
    }
    let runtime_dir = find_runtime_dir()?;
    let python = venv_python(&runtime_dir)?;
    let child = Command::new(python)
        .args([
            "-m",
            "uvicorn",
            "office_agent.app:app",
            "--app-dir",
            "src",
            "--host",
            "127.0.0.1",
            "--port",
            "8765",
        ])
        .current_dir(&runtime_dir)
        .stdout(Stdio::null())
        .stderr(Stdio::null())
        .spawn();

    match child {
        Ok(c) => {
            eprintln!("[office-agent] auto-started runtime from {:?}", runtime_dir);
            Some(c)
        }
        Err(e) => {
            eprintln!("[office-agent] could not auto-start runtime: {e} (start it manually, see README)");
            None
        }
    }
}

#[cfg_attr(mobile, tauri::mobile_entry_point)]
pub fn run() {
    tauri::Builder::default()
        .plugin(tauri_plugin_opener::init())
        .plugin(tauri_plugin_dialog::init())
        .invoke_handler(tauri::generate_handler![pick_folder])
        .setup(|app| {
            let child = try_spawn_runtime();
            app.manage(RuntimeProcess(Mutex::new(child)));
            Ok(())
        })
        .on_window_event(|window, event| {
            if let tauri::WindowEvent::Destroyed = event {
                if let Some(state) = window.app_handle().try_state::<RuntimeProcess>() {
                    if let Ok(mut guard) = state.0.lock() {
                        if let Some(mut child) = guard.take() {
                            let _ = child.kill();
                        }
                    }
                }
            }
        })
        .run(tauri::generate_context!())
        .expect("error while running tauri application");
}
