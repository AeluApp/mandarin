// Prevents additional console window on Windows in release, DO NOT REMOVE!!
#![cfg_attr(not(debug_assertions), windows_subsystem = "windows")]

use std::sync::Mutex;
use std::time::Duration;
use tauri::{Manager, RunEvent};
use tauri_plugin_shell::ShellExt;
use tauri_plugin_shell::process::{CommandChild, CommandEvent};

#[cfg(target_os = "macos")]
use objc::{msg_send, sel, sel_impl, runtime::Object};

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

/// Configure the WKWebView to allow media capture (microphone) and inline playback.
/// This is required for `navigator.mediaDevices.getUserMedia` to work in WKWebView.
#[cfg(target_os = "macos")]
fn configure_webview_media(app: &tauri::App) {
    use tauri::WebviewWindow;

    let window: WebviewWindow = app.get_webview_window("main")
        .expect("main window not found");

    // Access the underlying WKWebView via the webview's ns_view
    window.with_webview(|webview| {
        unsafe {
            // The wry webview inner is a WKWebView. Access its configuration.
            let wk_webview: *mut Object = webview.inner().cast();
            let configuration: *mut Object = msg_send![wk_webview, configuration];
            let preferences: *mut Object = msg_send![configuration, preferences];

            // WKPreferences: enable JavaScript (should already be on, but be explicit)
            let _: () = msg_send![preferences, _setMediaDevicesEnabled: true];
            let _: () = msg_send![preferences, _setMediaCaptureRequiresSecureConnection: false];

            // WKWebViewConfiguration: allow inline media playback
            let _: () = msg_send![configuration, setAllowsInlineMediaPlayback: true];

            // Set mediaTypesRequiringUserActionForPlayback to none (0 = WKAudiovisualMediaTypeNone)
            let _: () = msg_send![configuration, setMediaTypesRequiringUserActionForPlayback: 0u64];

            eprintln!("[tauri] WKWebView media capture configured");
        }
    }).unwrap_or_else(|e| {
        eprintln!("[tauri] failed to configure webview media: {:?}", e);
    });
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

            // Configure WKWebView for microphone access and inline media playback
            #[cfg(target_os = "macos")]
            configure_webview_media(app);

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
