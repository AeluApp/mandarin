import Flutter
import UIKit

/// AppDelegate with security hardening.
///
/// OWASP M9: Content hiding in task switcher prevents screenshot of sensitive data.
/// CIS Mobile 4.3: Screen capture prevention on iOS via overlay blur.
/// ISO 27001 A.11.2.9: Clear desk/screen policy — hide content when not active.
@main
@objc class AppDelegate: FlutterAppDelegate, FlutterImplicitEngineDelegate {
    private var blurView: UIVisualEffectView?

    override func application(
        _ application: UIApplication,
        didFinishLaunchingWithOptions launchOptions: [UIApplication.LaunchOptionsKey: Any]?
    ) -> Bool {
        return super.application(application, didFinishLaunchingWithOptions: launchOptions)
    }

    func didInitializeImplicitFlutterEngine(_ engineBridge: FlutterImplicitEngineBridge) {
        GeneratedPluginRegistrant.register(with: engineBridge.pluginRegistry)
    }

    // SECURITY: Hide content when app goes to task switcher.
    override func applicationWillResignActive(_ application: UIApplication) {
        addBlurOverlay()
    }

    // SECURITY: Remove blur when app becomes active again.
    override func applicationDidBecomeActive(_ application: UIApplication) {
        removeBlurOverlay()
    }

    private func addBlurOverlay() {
        guard blurView == nil else { return }
        let blur = UIBlurEffect(style: .light)
        let view = UIVisualEffectView(effect: blur)
        view.frame = UIScreen.main.bounds
        view.tag = 999
        self.window?.addSubview(view)
        blurView = view
    }

    private func removeBlurOverlay() {
        blurView?.removeFromSuperview()
        blurView = nil
    }
}
