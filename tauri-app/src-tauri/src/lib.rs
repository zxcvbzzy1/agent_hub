mod process_manager;

use process_manager::ProcState;
use tauri::{Manager, RunEvent};

#[cfg_attr(mobile, tauri::mobile_entry_point)]
pub fn run() {
    let app = tauri::Builder::default()
        .plugin(tauri_plugin_opener::init())
        .plugin(tauri_plugin_dialog::init())
        .plugin(tauri_plugin_fs::init())
        .plugin(tauri_plugin_notification::init())
        .setup(|app| {
            let settings = process_manager::load_settings(&app.handle().clone());
            app.manage(ProcState::new(settings));
            Ok(())
        })
        .invoke_handler(tauri::generate_handler![
            process_manager::get_proc_settings,
            process_manager::save_proc_settings,
            process_manager::proc_status,
            process_manager::proc_logs,
            process_manager::start_proc,
            process_manager::stop_proc,
            process_manager::restart_proc,
            process_manager::start_all,
        ])
        .build(tauri::generate_context!())
        .expect("error while building tauri application");

    app.run(|app_handle, event| {
        if let RunEvent::Exit = event {
            process_manager::kill_managed_on_exit(app_handle);
        }
    });
}
