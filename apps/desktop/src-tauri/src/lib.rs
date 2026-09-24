// 文书通 — Tauri 桌面壳（办公文书 · 智能通办）
//
// Responsibilities:
// 1. Expose `pick_folder` / `pick_skill_file` for native dialogs.
// 2. Auto-start the local Python runtime on 127.0.0.1:8765:
//    - Release: packaged onedir sidecar under resources/runtime/
//    - Debug / fallback: repo `runtime/.venv` (dev workflow)
// 3. Stop owned runtime on Exit / ExitRequested; reclaim stale 8765 on launch.
use std::fs::OpenOptions;
use std::io::{Read, Write};
use std::net::TcpStream;
use std::path::{Path, PathBuf};
use std::process::{Child, Command, Stdio};
use std::sync::atomic::{AtomicBool, Ordering};
use std::sync::Mutex;
use std::time::{Duration, Instant, SystemTime, UNIX_EPOCH};

use serde_json::{Map, Value};
use tauri::path::BaseDirectory;
use tauri::webview::PageLoadEvent;
use tauri::{Manager, RunEvent};
use tauri_plugin_dialog::DialogExt;
use uuid::Uuid;

#[cfg(windows)]
mod native_splash;

#[cfg(windows)]
use std::os::windows::io::AsRawHandle;
#[cfg(windows)]
use std::os::windows::process::CommandExt;

#[cfg(windows)]
const CREATE_NO_WINDOW: u32 = 0x0800_0000;

/// Holds the handle to the auto-spawned runtime process (if any) so it can
/// be terminated when the app exits.
struct RuntimeProcess(Mutex<Option<Child>>);

/// Windows Job Object handle. HANDLE is a raw pointer and is not Send/Sync;
/// the job is only used from the desktop process and closed on process exit.
#[cfg(windows)]
#[derive(Clone, Copy)]
struct JobHandle(windows_sys::Win32::Foundation::HANDLE);

#[cfg(windows)]
unsafe impl Send for JobHandle {}
#[cfg(windows)]
unsafe impl Sync for JobHandle {}

/// Windows Job Object: closing this handle kills assigned sidecar processes.
#[cfg(windows)]
struct RuntimeJob(Mutex<Option<JobHandle>>);

/// True only when this launch attempted to spawn a runtime child (not when
/// skipping because 8765 was already up and accepted our token). Used on Exit
/// as a race fallback when the Child handle is not yet stored in `RuntimeProcess`.
static ATTEMPTED_RUNTIME_SPAWN: AtomicBool = AtomicBool::new(false);

/// Idempotent guard so ExitRequested + Exit only stop once.
static RUNTIME_CLEANUP_DONE: AtomicBool = AtomicBool::new(false);

/// Per-launch API token shared with the spawned runtime and the webview.
struct RuntimeAuthToken(Mutex<String>);

/// Per-desktop-process boot id (also passed to sidecar as OFFICE_AGENT_BOOT_ID).
struct BootId(Mutex<String>);

fn generate_runtime_token() -> String {
    Uuid::new_v4().to_string()
}

fn generate_boot_id() -> String {
    Uuid::new_v4().to_string()
}

/// App data root: `OFFICE_AGENT_DATA` or `~/.office-agent`.
fn app_data_dir() -> PathBuf {
    if let Ok(override_dir) = std::env::var("OFFICE_AGENT_DATA") {
        if !override_dir.trim().is_empty() {
            return PathBuf::from(override_dir);
        }
    }
    let home = std::env::var("HOME")
        .or_else(|_| std::env::var("USERPROFILE"))
        .unwrap_or_else(|_| ".".into());
    PathBuf::from(home).join(".office-agent")
}

/// UTC civil time (year, month, day, hour, min, sec) from unix epoch seconds.
fn utc_civil_from_unix(secs: u64) -> (i32, u32, u32, u32, u32, u32) {
    let days = (secs / 86400) as i64;
    let tod = (secs % 86400) as u32;
    let hour = tod / 3600;
    let min = (tod % 3600) / 60;
    let sec = tod % 60;
    // Howard Hinnant civil_from_days
    let z = days + 719468;
    let era = if z >= 0 { z } else { z - 146096 } / 146097;
    let doe = (z - era * 146097) as u64;
    let yoe = (doe - doe / 1460 + doe / 36524 - doe / 146096) / 365;
    let y = yoe as i64 + era * 400;
    let doy = doe - (365 * yoe + yoe / 4 - yoe / 100);
    let mp = (5 * doy + 2) / 153;
    let d = doy - (153 * mp + 2) / 5 + 1;
    let m = if mp < 10 { mp + 3 } else { mp - 9 };
    let y = if m <= 2 { y + 1 } else { y };
    (y as i32, m as u32, d as u32, hour, min, sec)
}

fn utc_now() -> (String /* YYYY-MM-DD */, String /* ISO ts */) {
    let secs = SystemTime::now()
        .duration_since(UNIX_EPOCH)
        .map(|d| d.as_secs())
        .unwrap_or(0);
    let (y, mo, d, h, mi, s) = utc_civil_from_unix(secs);
    (
        format!("{y:04}-{mo:02}-{d:02}"),
        format!("{y:04}-{mo:02}-{d:02}T{h:02}:{mi:02}:{s:02}Z"),
    )
}

fn boot_id_from_app(app: &tauri::AppHandle) -> String {
    app.try_state::<BootId>()
        .and_then(|s| s.inner().0.lock().ok().map(|g| g.clone()))
        .unwrap_or_else(|| "-".into())
}

const FORBIDDEN_LOG_KEYS: &[&str] = &["api_key", "key", "token", "password", "passwd", "messages", "content"];

/// Structured desktop event → `logs/desktop-YYYY-MM-DD.jsonl` + plaintext temp log.
///
/// Acceptance (manual): after launch, `~/.office-agent/logs/desktop-*.jsonl` contains
/// `boot` / `sidecar_spawn` rows with `boot_id`; killing health path emits `health_fail`
/// via `desktop_log`; exit emits `sidecar_exit` with `returncode`.
fn log_event(event: &str, level: &str, boot_id: &str, extra: &str) {
    let (day, ts) = utc_now();
    let mut map = Map::new();
    map.insert("ts".into(), Value::String(ts));
    map.insert("level".into(), Value::String(level.to_string()));
    map.insert("event".into(), Value::String(event.to_string()));
    map.insert("boot_id".into(), Value::String(boot_id.to_string()));

    let extra_trim = extra.trim();
    if !extra_trim.is_empty() {
        if let Ok(Value::Object(extra_obj)) = serde_json::from_str::<Value>(extra_trim) {
            for (k, v) in extra_obj {
                if FORBIDDEN_LOG_KEYS.contains(&k.as_str()) {
                    continue;
                }
                map.entry(k).or_insert(v);
            }
        }
    }

    let line = match serde_json::to_string(&Value::Object(map)) {
        Ok(s) => s,
        Err(_) => return,
    };

    let logs_dir = app_data_dir().join("logs");
    let _ = std::fs::create_dir_all(&logs_dir);
    let jsonl_path = logs_dir.join(format!("desktop-{day}.jsonl"));
    if let Ok(mut f) = OpenOptions::new()
        .create(true)
        .append(true)
        .open(&jsonl_path)
    {
        let _ = writeln!(f, "{line}");
    }

    // Dual-write plaintext line to the legacy temp log (runtimeLogHint / Task 11).
    log_line(&format!("[office-agent] {line}"));
}

#[tauri::command]
fn get_runtime_token(state: tauri::State<'_, RuntimeAuthToken>) -> Result<String, String> {
    state
        .0
        .lock()
        .map_err(|e| e.to_string())
        .map(|guard| guard.clone())
}

#[tauri::command]
fn desktop_log(
    event: String,
    level: Option<String>,
    boot: tauri::State<'_, BootId>,
) -> Result<(), String> {
    let boot_id = boot
        .0
        .lock()
        .map_err(|e| e.to_string())?
        .clone();
    let lvl = level.unwrap_or_else(|| "warn".to_string());
    log_event(&event, &lvl, &boot_id, "");
    Ok(())
}

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

/// Locate bundled `NOTICE` for the About → 查看开源许可 action.
fn find_notice_path(app: &tauri::AppHandle) -> Option<PathBuf> {
    let mut candidates: Vec<PathBuf> = Vec::new();

    if let Ok(rd) = app.path().resource_dir() {
        candidates.push(rd.join("NOTICE"));
        candidates.push(rd.join("resources").join("NOTICE"));
    }
    for rel in ["NOTICE", "resources/NOTICE"] {
        if let Ok(p) = app.path().resolve(rel, BaseDirectory::Resource) {
            candidates.push(p);
        }
    }
    if let Ok(exe) = std::env::current_exe() {
        if let Some(dir) = exe.parent() {
            candidates.push(dir.join("resources").join("NOTICE"));
            candidates.push(dir.join("NOTICE"));
        }
    }

    for p in candidates {
        if p.is_file() {
            log_line(&format!("[office-agent] found NOTICE at {p:?}"));
            return Some(p);
        }
        log_line(&format!("[office-agent] NOTICE miss {p:?}"));
    }
    None
}

#[tauri::command]
fn read_notice_text(app: tauri::AppHandle) -> Result<String, String> {
    let path = find_notice_path(&app).ok_or_else(|| "未找到开源许可文件 NOTICE".to_string())?;
    std::fs::read_to_string(&path).map_err(|e| format!("无法读取开源许可文件：{e}"))
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

/// True when something on 8765 accepts `GET /config` with this Bearer token.
fn runtime_accepts_token(token: &str) -> bool {
    let Ok(mut stream) = TcpStream::connect_timeout(
        &"127.0.0.1:8765".parse().unwrap(),
        Duration::from_millis(500),
    ) else {
        return false;
    };
    let _ = stream.set_read_timeout(Some(Duration::from_millis(800)));
    let _ = stream.set_write_timeout(Some(Duration::from_millis(500)));
    let req = format!(
        "GET /config HTTP/1.1\r\nHost: 127.0.0.1\r\nAuthorization: Bearer {token}\r\nConnection: close\r\n\r\n"
    );
    if stream.write_all(req.as_bytes()).is_err() {
        return false;
    }
    let mut buf = [0u8; 256];
    let n = stream.read(&mut buf).unwrap_or(0);
    if n == 0 {
        return false;
    }
    let head = String::from_utf8_lossy(&buf[..n]);
    head.starts_with("HTTP/1.1 200") || head.starts_with("HTTP/1.0 200")
}

fn wait_runtime_port_free(timeout: Duration) -> bool {
    let start = Instant::now();
    while start.elapsed() < timeout {
        if !runtime_already_up() {
            return true;
        }
        std::thread::sleep(Duration::from_millis(80));
    }
    !runtime_already_up()
}

fn request_runtime_shutdown(token: &str) {
    if let Ok(mut stream) =
        TcpStream::connect_timeout(&"127.0.0.1:8765".parse().unwrap(), Duration::from_millis(500))
    {
        let _ = stream.set_read_timeout(Some(Duration::from_millis(800)));
        let _ = stream.set_write_timeout(Some(Duration::from_millis(500)));
        let req = format!(
            "POST /shutdown HTTP/1.1\r\nHost: 127.0.0.1\r\nAuthorization: Bearer {token}\r\nContent-Length: 0\r\nConnection: close\r\n\r\n"
        );
        let _ = stream.write_all(req.as_bytes());
        let mut buf = [0u8; 128];
        let _ = stream.read(&mut buf);
    }
}

fn runtime_token_from_app(app: &tauri::AppHandle) -> String {
    app.try_state::<RuntimeAuthToken>()
        .and_then(|state| state.inner().0.lock().ok().map(|guard| guard.clone()))
        .unwrap_or_default()
}

fn stop_child(child: &mut Child, token: &str) -> Option<i32> {
    request_runtime_shutdown(token);
    std::thread::sleep(Duration::from_millis(400));
    match child.try_wait() {
        Ok(Some(status)) => status.code(),
        _ => {
            let _ = child.kill();
            match child.wait() {
                Ok(status) => status.code(),
                Err(_) => None,
            }
        }
    }
}

/// Stop the runtime we own this launch. Idempotent across ExitRequested + Exit.
fn stop_owned_runtime(app: &tauri::AppHandle) {
    if RUNTIME_CLEANUP_DONE.swap(true, Ordering::SeqCst) {
        return;
    }
    log_line("[office-agent] stop_owned_runtime: cleaning up");
    let boot_id = boot_id_from_app(app);
    if let Some(state) = app.try_state::<RuntimeProcess>() {
        if let Ok(mut guard) = state.inner().0.lock() {
            if let Some(mut child) = guard.take() {
                let returncode = stop_child(&mut child, &runtime_token_from_app(app));
                let extra = match returncode {
                    Some(code) => format!(r#"{{"returncode":{code}}}"#),
                    None => r#"{"returncode":null}"#.to_string(),
                };
                log_event("sidecar_exit", "info", &boot_id, &extra);
                return;
            }
        }
    }
    if ATTEMPTED_RUNTIME_SPAWN.load(Ordering::SeqCst) {
        // Spawn raced ahead of Mutex store — shut down our child.
        request_runtime_shutdown(&runtime_token_from_app(app));
        log_event("sidecar_exit", "info", &boot_id, r#"{"returncode":null}"#);
    }
    // Else: skipped spawn (external runtime accepted our token) — leave 8765 alone.
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

#[cfg(windows)]
fn assign_child_to_kill_job(app: &tauri::AppHandle, child: &Child) {
    use windows_sys::Win32::Foundation::{CloseHandle, HANDLE};
    use windows_sys::Win32::System::JobObjects::{
        AssignProcessToJobObject, CreateJobObjectW, JobObjectExtendedLimitInformation,
        SetInformationJobObject, JOBOBJECT_EXTENDED_LIMIT_INFORMATION,
        JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE,
    };

    let Some(job_state) = app.try_state::<RuntimeJob>() else {
        return;
    };
    let Ok(mut guard) = job_state.inner().0.lock() else {
        return;
    };

    unsafe {
        if guard.is_none() {
            let job = CreateJobObjectW(std::ptr::null(), std::ptr::null());
            if job.is_null() {
                log_line("[office-agent] CreateJobObjectW failed");
                return;
            }
            let mut info: JOBOBJECT_EXTENDED_LIMIT_INFORMATION = std::mem::zeroed();
            info.BasicLimitInformation.LimitFlags = JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE;
            let ok = SetInformationJobObject(
                job,
                JobObjectExtendedLimitInformation,
                &info as *const _ as *const _,
                std::mem::size_of_val(&info) as u32,
            );
            if ok == 0 {
                log_line("[office-agent] SetInformationJobObject failed");
                CloseHandle(job);
                return;
            }
            *guard = Some(JobHandle(job));
            log_line("[office-agent] created Job Object (KILL_ON_JOB_CLOSE)");
        }

        let Some(JobHandle(job)) = *guard else {
            return;
        };
        let process: HANDLE = child.as_raw_handle() as HANDLE;
        if AssignProcessToJobObject(job, process) == 0 {
            log_line("[office-agent] AssignProcessToJobObject failed (sidecar may orphan on hard kill)");
        } else {
            log_line("[office-agent] sidecar assigned to Job Object");
        }
    }
}

#[cfg(not(windows))]
fn assign_child_to_kill_job(_app: &tauri::AppHandle, _child: &Child) {}

fn apply_deployment_profile_env(cmd: &mut Command, app: &tauri::AppHandle, sidecar: &Path) {
    if let Ok(existing) = std::env::var("OFFICE_AGENT_DEPLOYMENT") {
        if !existing.trim().is_empty() {
            cmd.env("OFFICE_AGENT_DEPLOYMENT", existing);
            log_line("[office-agent] OFFICE_AGENT_DEPLOYMENT from environment");
            return;
        }
    }
    let mut candidates: Vec<PathBuf> = Vec::new();
    if let Some(runtime_dir) = sidecar.parent() {
        if let Some(resources) = runtime_dir.parent() {
            candidates.push(resources.join("deployment-profile"));
        }
    }
    if let Ok(rd) = app.path().resource_dir() {
        candidates.push(rd.join("deployment-profile"));
        candidates.push(rd.join("resources").join("deployment-profile"));
    }
    if let Ok(exe) = std::env::current_exe() {
        if let Some(dir) = exe.parent() {
            candidates.push(dir.join("resources").join("deployment-profile"));
        }
    }
    for path in candidates {
        if let Ok(text) = std::fs::read_to_string(&path) {
            let profile = text.trim().to_ascii_lowercase();
            if profile == "local" || profile == "standard" {
                cmd.env("OFFICE_AGENT_DEPLOYMENT", &profile);
                log_line(&format!(
                    "[office-agent] OFFICE_AGENT_DEPLOYMENT={profile} from {path:?}"
                ));
                return;
            }
        }
    }
}

/// Production path: onedir sidecar staged under Tauri resources.
fn try_spawn_sidecar(app: &tauri::AppHandle, api_token: &str, boot_id: &str) -> Option<Child> {
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
    apply_deployment_profile_env(&mut cmd, app, &sidecar);
    cmd.env("OFFICE_AGENT_API_TOKEN", api_token);
    cmd.env("OFFICE_AGENT_BOOT_ID", boot_id);

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
            log_event("sidecar_spawn", "info", boot_id, r#"{"ok":true}"#);
            Some(c)
        }
        Err(e) => {
            log_line(&format!("[office-agent] could not start packaged runtime: {e}"));
            let err_json = serde_json::to_string(&e.to_string()).unwrap_or_else(|_| "\"spawn_failed\"".into());
            log_event(
                "sidecar_spawn",
                "warn",
                boot_id,
                &format!(r#"{{"ok":false,"error":{err_json}}}"#),
            );
            None
        }
    }
}

/// Dev path: `python -m office_agent` via local `.venv`.
fn try_spawn_venv(api_token: &str, boot_id: &str) -> Option<Child> {
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
    if let Ok(profile) = std::env::var("OFFICE_AGENT_DEPLOYMENT") {
        if !profile.trim().is_empty() {
            cmd.env("OFFICE_AGENT_DEPLOYMENT", profile);
        }
    }
    cmd.env("OFFICE_AGENT_API_TOKEN", api_token);
    cmd.env("OFFICE_AGENT_BOOT_ID", boot_id);

    #[cfg(windows)]
    {
        cmd.creation_flags(CREATE_NO_WINDOW);
    }

    match cmd.spawn() {
        Ok(c) => {
            log_line(&format!(
                "[office-agent] auto-started runtime from {runtime_dir:?}"
            ));
            log_event("sidecar_spawn", "info", boot_id, r#"{"ok":true}"#);
            Some(c)
        }
        Err(e) => {
            log_line(&format!(
                "[office-agent] could not auto-start runtime: {e} (start it manually, see README)"
            ));
            let err_json = serde_json::to_string(&e.to_string()).unwrap_or_else(|_| "\"spawn_failed\"".into());
            log_event(
                "sidecar_spawn",
                "warn",
                boot_id,
                &format!(r#"{{"ok":false,"error":{err_json}}}"#),
            );
            None
        }
    }
}

/// Best-effort spawn of the local runtime. Never panics: any failure is
/// logged and the UI will simply show "runtime offline" until the
/// user starts it manually (see README).
fn try_spawn_runtime(app: &tauri::AppHandle, api_token: &str, boot_id: &str) -> Option<Child> {
    if runtime_already_up() {
        if runtime_accepts_token(api_token) {
            log_line("[office-agent] runtime already listening on 127.0.0.1:8765 — skip auto-start");
            return None;
        }
        log_line(
            "[office-agent] stale runtime on 127.0.0.1:8765 (token rejected) — reclaiming",
        );
        request_runtime_shutdown(api_token);
        if !wait_runtime_port_free(Duration::from_secs(3)) {
            log_line(
                "[office-agent] port 8765 still busy after reclaim shutdown; refusing to start",
            );
            std::process::exit(1);
        }
    }

    // Mark ownership before spawn so Exit can shut down even if the Child
    // handle has not been stored yet (setup thread race).
    ATTEMPTED_RUNTIME_SPAWN.store(true, Ordering::SeqCst);

    // Release builds prefer the packaged sidecar; debug keeps the fast venv loop.
    let child = if !cfg!(debug_assertions) {
        if let Some(child) = try_spawn_sidecar(app, api_token, boot_id) {
            Some(child)
        } else {
            log_line("[office-agent] sidecar unavailable — trying local .venv fallback");
            try_spawn_venv(api_token, boot_id)
        }
    } else {
        try_spawn_venv(api_token, boot_id)
    };

    if let Some(ref c) = child {
        assign_child_to_kill_job(app, c);
    }
    child
}

/// Phytium / 银河麒麟: WebKitGTK hardware compositing often leaves a process
/// with no visible window. Prefer software compositing + X11 unless the user
/// already set overrides.
#[cfg(target_os = "linux")]
fn apply_linux_display_defaults() {
    if std::env::var_os("WEBKIT_DISABLE_COMPOSITING_MODE").is_none() {
        std::env::set_var("WEBKIT_DISABLE_COMPOSITING_MODE", "1");
    }
    if std::env::var_os("GDK_BACKEND").is_none() {
        std::env::set_var("GDK_BACKEND", "x11");
    }
}

#[cfg_attr(mobile, tauri::mobile_entry_point)]
pub fn run() {
    #[cfg(target_os = "linux")]
    apply_linux_display_defaults();

    // Cover WebView2 cold-start blank with a native (non-WebView) splash on Windows.
    #[cfg(windows)]
    native_splash::show();

    let builder = tauri::Builder::default()
        .plugin(tauri_plugin_opener::init())
        .plugin(tauri_plugin_dialog::init())
        .invoke_handler(tauri::generate_handler![
            pick_folder,
            pick_skill_file,
            get_runtime_token,
            read_notice_text,
            desktop_log,
        ])
        .on_page_load(|webview, payload| {
            if webview.label() != "main" {
                return;
            }
            if !matches!(payload.event(), PageLoadEvent::Finished) {
                return;
            }
            reveal_main_window(&webview.app_handle());
        })
        .setup(|app| {
            let boot_id = generate_boot_id();
            app.manage(BootId(Mutex::new(boot_id.clone())));
            let version = env!("CARGO_PKG_VERSION");
            log_event(
                "boot",
                "info",
                &boot_id,
                &format!(r#"{{"version":"{version}"}}"#),
            );

            let api_token = generate_runtime_token();
            app.manage(RuntimeAuthToken(Mutex::new(api_token.clone())));
            app.manage(RuntimeProcess(Mutex::new(None)));
            #[cfg(windows)]
            {
                app.manage(RuntimeJob(Mutex::new(None)));
            }
            let handle = app.handle().clone();
            let boot_id_spawn = boot_id.clone();
            std::thread::spawn(move || {
                let child = try_spawn_runtime(&handle, &api_token, &boot_id_spawn);
                if let Some(state) = handle.try_state::<RuntimeProcess>() {
                    if let Ok(mut guard) = state.inner().0.lock() {
                        *guard = child;
                    }
                }
            });
            // Fallback: never leave the main window invisible forever.
            let fallback = app.handle().clone();
            std::thread::spawn(move || {
                std::thread::sleep(Duration::from_secs(20));
                reveal_main_window(&fallback);
            });
            Ok(())
        });

    builder
        .build(tauri::generate_context!())
        .expect("error while building tauri application")
        .run(|app_handle, event| {
            match event {
                RunEvent::ExitRequested { .. } | RunEvent::Exit => {
                    #[cfg(windows)]
                    native_splash::dismiss();
                    stop_owned_runtime(app_handle);
                }
                _ => {}
            }
        });
}

fn reveal_main_window(app: &tauri::AppHandle) {
    if let Some(win) = app.get_webview_window("main") {
        let _ = win.show();
        let _ = win.set_focus();
    }
    #[cfg(windows)]
    native_splash::dismiss();
}
