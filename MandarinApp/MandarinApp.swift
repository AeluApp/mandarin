import Cocoa
import WebKit

// MARK: - App Delegate

class AppDelegate: NSObject, NSApplicationDelegate {
    var window: NSWindow!
    var webView: WKWebView!

    func applicationDidFinishLaunching(_ notification: Notification) {
        // -- WKWebView configuration --
        let config = WKWebViewConfiguration()
        let prefs = WKPreferences()
        prefs.setValue(true, forKey: "developerExtrasEnabled")
        config.preferences = prefs

        // Enable getUserMedia (microphone/camera)
        // The undocumented but widely-used key for enabling media devices
        config.preferences.setValue(true, forKey: "mediaDevicesEnabled")
        config.preferences.setValue(true, forKey: "mediaCaptureRequiresSecureConnection")

        // Allow media playback without user gesture (for TTS etc.)
        config.mediaTypesRequiringUserActionForPlayback = []

        webView = WKWebView(frame: .zero, configuration: config)
        webView.uiDelegate = self
        webView.navigationDelegate = self
        webView.allowsBackForwardNavigationGestures = true

        // Transparent background so dark mode works naturally
        webView.setValue(false, forKey: "drawsBackground")

        // -- Window --
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
        window.title = "Mandarin"
        window.minSize = NSSize(width: 480, height: 400)
        window.contentView = webView
        window.makeKeyAndOrderFront(nil)
        window.titlebarAppearsTransparent = true
        window.titleVisibility = .hidden

        // Full-size content so web content extends behind titlebar
        window.styleMask.insert(.fullSizeContentView)

        // Load the dev server
        let url = URL(string: "http://127.0.0.1:5173")!
        webView.load(URLRequest(url: url))

        // Activate the app
        NSApp.activate(ignoringOtherApps: true)
    }

    func applicationShouldTerminateAfterLastWindowClosed(_ sender: NSApplication) -> Bool {
        return true
    }

    func applicationSupportsSecureRestorableState(_ app: NSApplication) -> Bool {
        return true
    }
}

// MARK: - WKUIDelegate (microphone permission)

extension AppDelegate: WKUIDelegate {

    // Modern API (macOS 12+): auto-grant microphone/camera permission
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

    // Handle JavaScript alerts
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

    // Handle JavaScript confirms
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

    // Handle new window requests (open in same webview)
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
    // Allow all navigation (including localhost HTTP)
    func webView(
        _ webView: WKWebView,
        decidePolicyFor navigationAction: WKNavigationAction,
        decisionHandler: @escaping (WKNavigationActionPolicy) -> Void
    ) {
        decisionHandler(.allow)
    }

    // Handle navigation failures (e.g., server not running)
    func webView(_ webView: WKWebView, didFailProvisionalNavigation navigation: WKNavigation!, withError error: Error) {
        let nsError = error as NSError
        // NSURLErrorCannotConnectToHost or NSURLErrorConnectionRefused
        if nsError.domain == NSURLErrorDomain &&
           (nsError.code == NSURLErrorCannotConnectToHost || nsError.code == -1004) {
            showRetryPage(in: webView)
        }
    }

    private func showRetryPage(in webView: WKWebView) {
        let html = """
        <!DOCTYPE html>
        <html>
        <head>
        <meta charset="utf-8">
        <style>
            * { margin: 0; padding: 0; box-sizing: border-box; }
            body {
                font-family: -apple-system, BlinkMacSystemFont, sans-serif;
                display: flex;
                align-items: center;
                justify-content: center;
                height: 100vh;
                background: #F2EBE0;
                color: #4A4A4A;
            }
            @media (prefers-color-scheme: dark) {
                body { background: #2A2520; color: #D4C8BC; }
                .card { background: #3A3530; }
                button { background: #946070; }
                button:hover { background: #A07080; }
            }
            .card {
                text-align: center;
                padding: 3rem;
                border-radius: 12px;
                background: white;
                box-shadow: 0 2px 12px rgba(0,0,0,0.08);
            }
            .hanzi { font-size: 4rem; color: #946070; margin-bottom: 1rem; }
            h2 { font-weight: 500; margin-bottom: 0.5rem; }
            p { color: #888; margin-bottom: 1.5rem; font-size: 0.95rem; }
            code { background: #f0ece6; padding: 2px 8px; border-radius: 4px; font-size: 0.9rem; }
            button {
                background: #946070;
                color: white;
                border: none;
                padding: 10px 28px;
                border-radius: 8px;
                font-size: 1rem;
                cursor: pointer;
                margin-top: 1rem;
            }
            button:hover { background: #7A5060; }
        </style>
        </head>
        <body>
        <div class="card">
            <div class="hanzi">\u{6F2B}</div>
            <h2>Waiting for server</h2>
            <p>Start the dev server with <code>./run app</code></p>
            <button onclick="location.href='http://127.0.0.1:5173'">Retry</button>
        </div>
        </body>
        </html>
        """
        webView.loadHTMLString(html, baseURL: nil)
    }
}

// MARK: - Entry Point

let app = NSApplication.shared
let delegate = AppDelegate()
app.delegate = delegate
app.run()
