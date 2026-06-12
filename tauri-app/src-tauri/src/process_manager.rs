//! 本地后端进程托管：mongod + im_backend (uvicorn)。
//!
//! 设计要点：
//! - 「托管 (managed)」= 由本 App spawn 的子进程；「外部 (external)」= 端口开着但不是我们拉起的
//!   （比如用户自己在终端里启动的），外部实例只展示状态、不允许 stop/kill。
//! - 日志：子进程 stdout/stderr 各起一个读线程，行级推送 `proc-log` 事件 + 环形缓冲区兜底
//!   （前端进入进程页时先拉全量缓冲，再增量收事件）。
//! - 启动顺序：mongod 端口就绪后再拉 im_backend——后端启动时对 Mongo 只有 300ms 的 ping 超时，
//!   失败会静默降级为内存存储，必须避免。

use serde::{Deserialize, Serialize};
use std::collections::VecDeque;
use std::io::{BufRead, BufReader};
use std::net::TcpStream;
use std::process::{Child, Command, Stdio};
use std::sync::{Arc, Mutex};
use std::thread;
use std::time::{Duration, SystemTime, UNIX_EPOCH};

use tauri::{AppHandle, Emitter, Manager};

pub const KIND_MONGOD: &str = "mongod";
pub const KIND_BACKEND: &str = "backend";
const LOG_CAP: usize = 800;
const SETTINGS_FILE: &str = "proc-settings.json";

#[derive(Clone, Serialize, Deserialize)]
#[serde(default)]
pub struct ProcSettings {
    pub repo_dir: String,
    pub python_path: String,
    pub mongod_path: String,
    pub mongo_dbpath: String,
    pub mongo_port: u16,
    pub backend_port: u16,
    pub auto_start: bool,
    pub stop_on_exit: bool,
}

impl Default for ProcSettings {
    fn default() -> Self {
        Self {
            repo_dir: "/Users/zxcvbzzy1/Desktop/项目/ByteDance_AgentHub".into(),
            python_path: "/Users/zxcvbzzy1/miniconda3/envs/MY_env/bin/python".into(),
            mongod_path:
                "/Users/zxcvbzzy1/Desktop/database/mongodb/mongodb-macos-aarch64--8.3.2/bin/mongod"
                    .into(),
            mongo_dbpath: "/Users/zxcvbzzy1/Desktop/database/mongodb/data/db".into(),
            mongo_port: 27017,
            backend_port: 8010,
            auto_start: false,
            stop_on_exit: true,
        }
    }
}

#[derive(Clone, Serialize)]
pub struct LogLine {
    pub kind: String,
    pub stream: String,
    pub line: String,
    pub ts: u64,
}

#[derive(Clone, Serialize)]
pub struct ProcStatus {
    pub kind: String,
    pub managed: bool,
    pub pid: Option<u32>,
    pub port: u16,
    pub port_open: bool,
}

#[derive(Default)]
pub struct ManagedProc {
    child: Option<Child>,
    logs: VecDeque<LogLine>,
}

pub struct ProcState {
    pub mongod: Arc<Mutex<ManagedProc>>,
    pub backend: Arc<Mutex<ManagedProc>>,
    pub settings: Arc<Mutex<ProcSettings>>,
}

impl ProcState {
    pub fn new(settings: ProcSettings) -> Self {
        Self {
            mongod: Arc::new(Mutex::new(ManagedProc::default())),
            backend: Arc::new(Mutex::new(ManagedProc::default())),
            settings: Arc::new(Mutex::new(settings)),
        }
    }

    fn proc_of(&self, kind: &str) -> Result<Arc<Mutex<ManagedProc>>, String> {
        match kind {
            KIND_MONGOD => Ok(self.mongod.clone()),
            KIND_BACKEND => Ok(self.backend.clone()),
            other => Err(format!("未知进程类型: {other}")),
        }
    }
}

fn now_ms() -> u64 {
    SystemTime::now()
        .duration_since(UNIX_EPOCH)
        .map(|d| d.as_millis() as u64)
        .unwrap_or(0)
}

fn port_open(port: u16) -> bool {
    TcpStream::connect_timeout(
        &([127, 0, 0, 1], port).into(),
        Duration::from_millis(400),
    )
    .is_ok()
}

fn push_log(app: &AppHandle, proc_arc: &Arc<Mutex<ManagedProc>>, kind: &str, stream: &str, line: String) {
    let entry = LogLine {
        kind: kind.into(),
        stream: stream.into(),
        line,
        ts: now_ms(),
    };
    if let Ok(mut guard) = proc_arc.lock() {
        if guard.logs.len() >= LOG_CAP {
            guard.logs.pop_front();
        }
        guard.logs.push_back(entry.clone());
    }
    let _ = app.emit("proc-log", entry);
}

fn spawn_reader<R: std::io::Read + Send + 'static>(
    app: AppHandle,
    proc_arc: Arc<Mutex<ManagedProc>>,
    kind: String,
    stream: String,
    pipe: R,
) {
    thread::spawn(move || {
        let reader = BufReader::new(pipe);
        for line in reader.lines() {
            match line {
                Ok(text) => push_log(&app, &proc_arc, &kind, &stream, text),
                Err(_) => break,
            }
        }
    });
}

/// 收割已退出的托管子进程；返回 (managed, pid)。
fn reap(app: &AppHandle, proc_arc: &Arc<Mutex<ManagedProc>>, kind: &str) -> (bool, Option<u32>) {
    let mut exited: Option<String> = None;
    let result = {
        let mut guard = match proc_arc.lock() {
            Ok(g) => g,
            Err(_) => return (false, None),
        };
        if let Some(child) = guard.child.as_mut() {
            match child.try_wait() {
                Ok(Some(status)) => {
                    exited = Some(format!("进程已退出 ({status})"));
                    guard.child = None;
                    (false, None)
                }
                Ok(None) => (true, Some(child.id())),
                Err(_) => (true, Some(child.id())),
            }
        } else {
            (false, None)
        }
    };
    if let Some(text) = exited {
        push_log(app, proc_arc, kind, "system", text);
        let _ = app.emit("proc-exit", kind.to_string());
    }
    result
}

fn build_command(kind: &str, settings: &ProcSettings) -> Result<Command, String> {
    match kind {
        KIND_MONGOD => {
            let mut cmd = Command::new(&settings.mongod_path);
            cmd.arg("--dbpath")
                .arg(&settings.mongo_dbpath)
                .arg("--port")
                .arg(settings.mongo_port.to_string())
                .arg("--bind_ip")
                .arg("127.0.0.1");
            Ok(cmd)
        }
        KIND_BACKEND => {
            let mut cmd = Command::new(&settings.python_path);
            cmd.arg("-m")
                .arg("uvicorn")
                .arg("im_backend.api.index:app")
                .arg("--host")
                .arg("127.0.0.1")
                .arg("--port")
                .arg(settings.backend_port.to_string())
                .current_dir(&settings.repo_dir)
                .env("PYTHONPATH", &settings.repo_dir)
                .env("PYTHONUNBUFFERED", "1");
            Ok(cmd)
        }
        other => Err(format!("未知进程类型: {other}")),
    }
}

fn port_for(kind: &str, settings: &ProcSettings) -> u16 {
    if kind == KIND_MONGOD {
        settings.mongo_port
    } else {
        settings.backend_port
    }
}

fn start_one(app: &AppHandle, state: &ProcState, kind: &str) -> Result<(), String> {
    let proc_arc = state.proc_of(kind)?;
    let settings = state.settings.lock().map_err(|_| "settings 锁损坏")?.clone();

    let (managed, _) = reap(app, &proc_arc, kind);
    if managed {
        return Err("进程已在托管运行中".into());
    }
    if port_open(port_for(kind, &settings)) {
        return Err(format!(
            "端口 {} 已被占用：检测到外部实例在运行，请先停掉它或直接使用",
            port_for(kind, &settings)
        ));
    }

    let mut cmd = build_command(kind, &settings)?;
    cmd.stdout(Stdio::piped()).stderr(Stdio::piped()).stdin(Stdio::null());
    let mut child = cmd
        .spawn()
        .map_err(|e| format!("启动失败: {e}（请到设置里检查路径）"))?;

    if let Some(stdout) = child.stdout.take() {
        spawn_reader(app.clone(), proc_arc.clone(), kind.into(), "stdout".into(), stdout);
    }
    if let Some(stderr) = child.stderr.take() {
        spawn_reader(app.clone(), proc_arc.clone(), kind.into(), "stderr".into(), stderr);
    }
    let pid = child.id();
    {
        let mut guard = proc_arc.lock().map_err(|_| "进程锁损坏")?;
        guard.child = Some(child);
    }
    push_log(app, &proc_arc, kind, "system", format!("已启动 (pid {pid})"));
    Ok(())
}

fn stop_one(app: &AppHandle, state: &ProcState, kind: &str) -> Result<(), String> {
    let proc_arc = state.proc_of(kind)?;
    let mut guard = proc_arc.lock().map_err(|_| "进程锁损坏")?;
    match guard.child.take() {
        Some(mut child) => {
            let _ = child.kill();
            let _ = child.wait();
            drop(guard);
            push_log(app, &proc_arc, kind, "system", "已停止".into());
            Ok(())
        }
        None => Err("该进程不是由桌面端托管的（外部实例请在原终端里停止）".into()),
    }
}

fn wait_port(port: u16, timeout: Duration) -> bool {
    let deadline = SystemTime::now() + timeout;
    while SystemTime::now() < deadline {
        if port_open(port) {
            return true;
        }
        thread::sleep(Duration::from_millis(300));
    }
    false
}

pub fn kill_managed_on_exit(app: &AppHandle) {
    let state = app.state::<ProcState>();
    let stop_on_exit = state
        .settings
        .lock()
        .map(|s| s.stop_on_exit)
        .unwrap_or(true);
    if !stop_on_exit {
        return;
    }
    // 先停后端再停 mongod，避免后端在 Mongo 消失后刷错误日志。
    for proc_arc in [state.backend.clone(), state.mongod.clone()] {
        if let Ok(mut guard) = proc_arc.lock() {
            if let Some(mut child) = guard.child.take() {
                let _ = child.kill();
                let _ = child.wait();
            }
        }
    }
}

fn settings_path(app: &AppHandle) -> Result<std::path::PathBuf, String> {
    let dir = app
        .path()
        .app_config_dir()
        .map_err(|e| format!("无法定位配置目录: {e}"))?;
    std::fs::create_dir_all(&dir).map_err(|e| format!("创建配置目录失败: {e}"))?;
    Ok(dir.join(SETTINGS_FILE))
}

pub fn load_settings(app: &AppHandle) -> ProcSettings {
    settings_path(app)
        .ok()
        .and_then(|p| std::fs::read_to_string(p).ok())
        .and_then(|text| serde_json::from_str(&text).ok())
        .unwrap_or_default()
}

// ---------------- Tauri commands ----------------

#[tauri::command]
pub fn get_proc_settings(state: tauri::State<'_, ProcState>) -> Result<ProcSettings, String> {
    state
        .settings
        .lock()
        .map(|s| s.clone())
        .map_err(|_| "settings 锁损坏".into())
}

#[tauri::command]
pub fn save_proc_settings(
    app: AppHandle,
    state: tauri::State<'_, ProcState>,
    settings: ProcSettings,
) -> Result<(), String> {
    let path = settings_path(&app)?;
    let text = serde_json::to_string_pretty(&settings).map_err(|e| e.to_string())?;
    std::fs::write(&path, text).map_err(|e| format!("写入配置失败: {e}"))?;
    *state.settings.lock().map_err(|_| "settings 锁损坏")? = settings;
    Ok(())
}

#[tauri::command]
pub fn proc_status(app: AppHandle, state: tauri::State<'_, ProcState>) -> Result<Vec<ProcStatus>, String> {
    let settings = state.settings.lock().map_err(|_| "settings 锁损坏")?.clone();
    let mut out = Vec::new();
    for kind in [KIND_MONGOD, KIND_BACKEND] {
        let proc_arc = state.proc_of(kind)?;
        let (managed, pid) = reap(&app, &proc_arc, kind);
        let port = port_for(kind, &settings);
        out.push(ProcStatus {
            kind: kind.into(),
            managed,
            pid,
            port,
            port_open: port_open(port),
        });
    }
    Ok(out)
}

#[tauri::command]
pub fn proc_logs(state: tauri::State<'_, ProcState>, kind: String) -> Result<Vec<LogLine>, String> {
    let proc_arc = state.proc_of(&kind)?;
    let guard = proc_arc.lock().map_err(|_| "进程锁损坏")?;
    Ok(guard.logs.iter().cloned().collect())
}

#[tauri::command]
pub async fn start_proc(app: AppHandle, kind: String) -> Result<(), String> {
    let state = app.state::<ProcState>();
    start_one(&app, &state, &kind)
}

#[tauri::command]
pub async fn stop_proc(app: AppHandle, kind: String) -> Result<(), String> {
    let state = app.state::<ProcState>();
    stop_one(&app, &state, &kind)
}

#[tauri::command]
pub async fn restart_proc(app: AppHandle, kind: String) -> Result<(), String> {
    let state = app.state::<ProcState>();
    // 外部实例不允许 restart；托管实例先停再起。
    let _ = stop_one(&app, &state, &kind);
    thread::sleep(Duration::from_millis(500));
    start_one(&app, &state, &kind)
}

/// 一键启动：mongod 端口就绪后再拉后端，规避后端 300ms ping 的内存降级。
#[tauri::command]
pub async fn start_all(app: AppHandle) -> Result<Vec<String>, String> {
    let state = app.state::<ProcState>();
    let settings = state.settings.lock().map_err(|_| "settings 锁损坏")?.clone();
    let mut report = Vec::new();

    if port_open(settings.mongo_port) {
        report.push("mongod: 已在运行".into());
    } else {
        start_one(&app, &state, KIND_MONGOD)?;
        if !wait_port(settings.mongo_port, Duration::from_secs(20)) {
            return Err("mongod 启动超时（20s 内端口未就绪），请查看日志".into());
        }
        // 端口开了再多等一拍，确保 Mongo 完全可服务（后端 ping 超时只有 300ms）。
        thread::sleep(Duration::from_secs(1));
        report.push("mongod: 启动成功".into());
    }

    if port_open(settings.backend_port) {
        report.push("im_backend: 已在运行".into());
    } else {
        start_one(&app, &state, KIND_BACKEND)?;
        if !wait_port(settings.backend_port, Duration::from_secs(30)) {
            return Err("im_backend 启动超时（30s 内端口未就绪），请查看日志".into());
        }
        report.push("im_backend: 启动成功".into());
    }
    Ok(report)
}
