import Cocoa
import WebKit

// MARK: - Constants

let SERVER_PORT: Int = 5173
let HEALTH_URL = "http://127.0.0.1:\(SERVER_PORT)/api/health"
let APP_URL = "http://127.0.0.1:\(SERVER_PORT)/auth/login"
let MAX_ATTEMPTS = 60
let POLL_INTERVAL: TimeInterval = 0.3

// MARK: - Splash HTML (Civic Sanctuary aesthetic)

let splashHTML = """
<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<style>
  @import url('https://fonts.googleapis.com/css2?family=Cormorant+Garamond:wght@400;600&family=Noto+Serif+SC:wght@700&display=swap');
  * { margin: 0; padding: 0; box-sizing: border-box; }
  body {
    background: #F2EBE0;
    color: #2A3650;
    font-family: 'Cormorant Garamond', Georgia, serif;
    display: flex;
    flex-direction: column;
    align-items: center;
    justify-content: center;
    height: 100vh;
    overflow: hidden;
  }
  .icon {
    font-family: 'Noto Serif SC', 'PingFang SC', serif;
    font-size: 72px;
    font-weight: 700;
    color: #946070;
    margin-bottom: 16px;
  }
  .title {
    font-size: 24px;
    font-weight: 600;
    color: #2A3650;
    letter-spacing: 0.15em;
    margin-bottom: 32px;
  }
  .spinner {
    width: 28px;
    height: 28px;
    border: 2px solid rgba(148, 96, 112, 0.2);
    border-top-color: #946070;
    border-radius: 50%;
    animation: spin 1s linear infinite;
    margin-bottom: 16px;
  }
  @keyframes spin { to { transform: rotate(360deg); } }
  .status {
    font-size: 14px;
    color: #5A6678;
    letter-spacing: 0.03em;
  }
</style>
</head>
<body>
  <div class="icon">\\u{6F2B}</div>
  <div class="title">Mandarin</div>
  <div class="spinner"></div>
  <div class="status" id="status">Starting...</div>
</body>
</html>
"""

// MARK: - App Delegate

class AppDelegate: NSObject, NSApplicationDelegate {
    var window: NSWindow!
    var webView: WKWebView!
    var serverProcess: Process?
    var pollTimer: Timer?
    var pollAttempts = 0

    func applicationDidFinishLaunching(_ notification: Notification) {
        // Start the server sidecar
        startServer()

        // Configure WKWebView
        let config = WKWebViewConfiguration()
        let prefs = WKPreferences()
        prefs.setValue(true, forKey: "developerExtrasEnabled")
        config.preferences = prefs
        config.preferences.setValue(true, forKey: "mediaDevicesEnabled")
        config.preferences.setValue(true, forKey: "mediaCaptureRequiresSecureConnection")
        config.mediaTypesRequiringUserActionForPlayback = []

        webView = WKWebView(frame: .zero, configuration: config)
        webView.uiDelegate = self
        webView.navigationDelegate = self
        webView.allowsBackForwardNavigationGestures = true
        webView.setValue(false, forKey: "drawsBackground")

        // Window
        let screenFrame = NSScreen.main?.visibleFrame ?? NSRect(x: 0, y: 0, width: 1200, height: 800)
        let windowWidth: CGFloat = 900
        let windowHeight: CGFloat = 700
        let windowX = screenFrame.midX - windowWidth / 2
        let windowY = screenFrame.midY - windowHeight / 2
        let contentRect = NSRect(x: windowX, y: windowY, width: windowWidth, height: windowHeight)

        window = NSWindow(
            contentRect: contentRect,
            styleMask: [.titled, .closable, .miniaturizable, .resizable],
            backing: .buffered,
            defer: false
        )
        window.title = "漫 Mandarin"
        window.minSize = NSSize(width: 480, height: 400)
        window.contentView = webView
        window.backgroundColor = NSColor(red: 0xF2/255.0, green: 0xEB/255.0, blue: 0xE0/255.0, alpha: 1.0)
        window.titlebarAppearsTransparent = true
        window.titleVisibility = .hidden
        window.styleMask.insert(.fullSizeContentView)
        window.makeKeyAndOrderFront(nil)

        // Show splash
        webView.loadHTMLString(splashHTML, baseURL: nil)

        // Start polling for server health
        pollTimer = Timer.scheduledTimer(withTimeInterval: POLL_INTERVAL, repeats: true) { [weak self] _ in
            self?.pollHealth()
        }

        NSApp.activate(ignoringOtherApps: true)
    }

    func startServer() {
        // Resolve project root: check bundle sidecar first, fall back to source tree
        let bundle = Bundle.main
        let sidecarPath = bundle.bundlePath + "/Contents/MacOS/mandarin-server"
        let homeDir = FileManager.default.homeDirectoryForCurrentUser.path
        let projectRoot = homeDir + "/mandarin"
        let venvPython = projectRoot + "/venv/bin/python"
        let entryScript = projectRoot + "/desktop/entry.py"

        let process = Process()

        if FileManager.default.fileExists(atPath: venvPython) &&
           FileManager.default.fileExists(atPath: entryScript) {
            // Use source tree (always up-to-date)
            process.executableURL = URL(fileURLWithPath: venvPython)
            process.arguments = [entryScript, "\(SERVER_PORT)"]
            process.currentDirectoryURL = URL(fileURLWithPath: projectRoot)
            NSLog("[mandarin] starting server from source: \(venvPython) \(entryScript)")
        } else if FileManager.default.fileExists(atPath: sidecarPath) {
            // Fallback to bundled PyInstaller binary
            process.executableURL = URL(fileURLWithPath: sidecarPath)
            process.arguments = ["\(SERVER_PORT)"]
            NSLog("[mandarin] starting server from sidecar: \(sidecarPath)")
        } else {
            NSLog("[mandarin] no server found - neither source nor sidecar available")
            return
        }

        process.standardOutput = FileHandle.nullDevice
        process.standardError = FileHandle.nullDevice
        process.qualityOfService = .userInitiated

        do {
            try process.run()
            serverProcess = process
            NSLog("[mandarin] server started with PID \(process.processIdentifier)")
        } catch {
            NSLog("[mandarin] failed to start server: \(error)")
        }
    }

    func pollHealth() {
        pollAttempts += 1

        guard let url = URL(string: HEALTH_URL) else { return }
        var request = URLRequest(url: url)
        request.timeoutInterval = 2.0

        let task = URLSession.shared.dataTask(with: request) { [weak self] _, response, error in
            guard let self = self else { return }
            if let httpResponse = response as? HTTPURLResponse, httpResponse.statusCode == 200 {
                DispatchQueue.main.async {
                    self.pollTimer?.invalidate()
                    self.pollTimer = nil
                    self.webView.load(URLRequest(url: URL(string: APP_URL)!))
                }
            } else if self.pollAttempts >= MAX_ATTEMPTS {
                DispatchQueue.main.async {
                    self.pollTimer?.invalidate()
                    self.pollTimer = nil
                    self.webView.evaluateJavaScript(
                        "document.getElementById('status').textContent = 'Failed to start. Please relaunch.'",
                        completionHandler: nil
                    )
                }
            }
        }
        task.resume()
    }

    func applicationShouldTerminateAfterLastWindowClosed(_ sender: NSApplication) -> Bool {
        return true
    }

    func applicationWillTerminate(_ notification: Notification) {
        killServer()
    }

    func applicationShouldTerminate(_ sender: NSApplication) -> NSApplication.TerminateReply {
        killServer()
        return .terminateNow
    }

    func killServer() {
        guard let process = serverProcess, process.isRunning else { return }
        let pid = process.processIdentifier
        NSLog("[mandarin] killing server process tree (PID \(pid))")

        // SIGTERM to process group
        kill(-pid, SIGTERM)
        kill(pid, SIGTERM)

        // Give it a moment
        DispatchQueue.global().asyncAfter(deadline: .now() + 0.5) {
            if process.isRunning {
                kill(-pid, SIGKILL)
                kill(pid, SIGKILL)
            }
        }
    }

    func applicationSupportsSecureRestorableState(_ app: NSApplication) -> Bool {
        return true
    }
}

// MARK: - WKUIDelegate

extension AppDelegate: WKUIDelegate {
    @available(macOS 12.0, *)
    func webView(
        _ webView: WKWebView,
        requestMediaCapturePermissionFor origin: WKSecurityOrigin,
        initiatedByFrame frame: WKFrameInfo,
        type: WKMediaCaptureType,
        decisionHandler: @escaping (WKPermissionDecision) -> Void
    ) {
        decisionHandler(.grant)
    }

    func webView(
        _ webView: WKWebView,
        runJavaScriptAlertPanelWithMessage message: String,
        initiatedByFrame frame: WKFrameInfo,
        completionHandler: @escaping () -> Void
    ) {
        let alert = NSAlert()
        alert.messageText = message
        alert.addButton(withTitle: "OK")
        alert.runModal()
        completionHandler()
    }

    func webView(
        _ webView: WKWebView,
        runJavaScriptConfirmPanelWithMessage message: String,
        initiatedByFrame frame: WKFrameInfo,
        completionHandler: @escaping (Bool) -> Void
    ) {
        let alert = NSAlert()
        alert.messageText = message
        alert.addButton(withTitle: "OK")
        alert.addButton(withTitle: "Cancel")
        let response = alert.runModal()
        completionHandler(response == .alertFirstButtonReturn)
    }

    func webView(
        _ webView: WKWebView,
        createWebViewWith configuration: WKWebViewConfiguration,
        for navigationAction: WKNavigationAction,
        windowFeatures: WKWindowFeatures
    ) -> WKWebView? {
        if navigationAction.targetFrame == nil || !(navigationAction.targetFrame!.isMainFrame) {
            webView.load(navigationAction.request)
        }
        return nil
    }
}

// MARK: - WKNavigationDelegate

extension AppDelegate: WKNavigationDelegate {
    func webView(
        _ webView: WKWebView,
        decidePolicyFor navigationAction: WKNavigationAction,
        decisionHandler: @escaping (WKNavigationActionPolicy) -> Void
    ) {
        decisionHandler(.allow)
    }
}

// MARK: - Entry Point

let app = NSApplication.shared
let delegate = AppDelegate()
app.delegate = delegate
app.run()
