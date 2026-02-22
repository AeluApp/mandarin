// Prevents additional console window on Windows in release, DO NOT REMOVE!!
#![cfg_attr(not(debug_assertions), windows_subsystem = "windows")]

use std::sync::Mutex;
use std::time::Duration;
use tauri::{Manager, RunEvent};
use tauri_plugin_shell::ShellExt;
use tauri_plugin_shell::process::{CommandChild, CommandEvent};

const PORT: u16 = 5173;

struct SidecarState {
    child: Mutex<Option<CommandChild>>,
    pid: Mutex<Option<u32>>,
}

fn kill_process_tree(pid: u32) {
    unsafe {
        // SIGTERM to process group
        libc::kill(-(pid as i32), libc::SIGTERM);
        // SIGTERM to process directly
        libc::kill(pid as i32, libc::SIGTERM);
    }
    std::thread::sleep(Duration::from_millis(500));
    unsafe {
        // Force kill if still alive
        libc::kill(-(pid as i32), libc::SIGKILL);
        libc::kill(pid as i32, libc::SIGKILL);
    }
}

fn main() {
    tauri::Builder::default()
        .plugin(tauri_plugin_shell::init())
        .manage(SidecarState {
            child: Mutex::new(None),
            pid: Mutex::new(None),
        })
        .setup(|app| {
            let shell = app.shell();
            let sidecar = shell
                .sidecar("mandarin-server")
                .map_err(|e| {
                    eprintln!("[tauri] failed to create sidecar command: {}", e);
                    e
                })?
                .args([PORT.to_string()]);

            let (mut rx, child) = sidecar.spawn().map_err(|e| {
                eprintln!("[tauri] failed to spawn sidecar: {}", e);
                e
            })?;

            let child_pid = child.pid();
            eprintln!("[tauri] sidecar spawned with PID {}", child_pid);
            let state = app.state::<SidecarState>();
            *state.child.lock().unwrap() = Some(child);
            *state.pid.lock().unwrap() = Some(child_pid);

            // Log sidecar output in background
            tauri::async_runtime::spawn(async move {
                while let Some(event) = rx.recv().await {
                    match event {
                        CommandEvent::Stdout(line) => {
                            eprintln!("[sidecar stdout] {}", String::from_utf8_lossy(&line));
                        }
                        CommandEvent::Stderr(line) => {
                            eprintln!("[sidecar stderr] {}", String::from_utf8_lossy(&line));
                        }
                        CommandEvent::Terminated(status) => {
                            eprintln!("[sidecar] terminated with {:?}", status);
                            break;
                        }
                        _ => {}
                    }
                }
            });

            Ok(())
        })
        .build(tauri::generate_context!())
        .expect("error while building tauri application")
        .run(|app, event| {
            if let RunEvent::Exit = event {
                let state = app.state::<SidecarState>();
                if let Some(pid) = state.pid.lock().unwrap().take() {
                    eprintln!("[tauri] killing sidecar process tree (PID {})", pid);
                    kill_process_tree(pid);
                }
                let child = state.child.lock().unwrap().take();
                if let Some(child) = child {
                    let _ = child.kill();
                }
            }
        });
}
