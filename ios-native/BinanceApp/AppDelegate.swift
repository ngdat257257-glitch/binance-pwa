import UIKit
import UserNotifications

@main
class AppDelegate: UIResponder, UIApplicationDelegate, UNUserNotificationCenterDelegate {

    var window: UIWindow?

    func application(
        _ application: UIApplication,
        didFinishLaunchingWithOptions launchOptions: [UIApplication.LaunchOptionsKey: Any]?
    ) -> Bool {

        // 1. Cấu hình trung tâm thông báo Native iOS
        let center = UNUserNotificationCenter.current()
        center.delegate = self
        center.requestAuthorization(options: [.alert, .sound, .badge]) { granted, error in
            if granted {
                print("✓ Đã cấp quyền thông báo Native iOS thành công!")
            } else if let error = error {
                print("❌ Lỗi xin quyền thông báo:", error.localizedDescription)
            }
        }

        // 2. Thiết lập cửa sổ chính và ViewController
        let window = UIWindow(frame: UIScreen.main.bounds)
        let mainVC = ViewController()
        window.rootViewController = mainVC
        self.window = window
        window.makeKeyAndVisible()

        return true
    }

    // Xử lý khi app đang mở ở tiền cảnh (Foreground): vẫn hiển thị banner thông báo native
    func userNotificationCenter(
        _ center: UNUserNotificationCenter,
        willPresent notification: UNNotification,
        withCompletionHandler completionHandler: @escaping (UNNotificationPresentationOptions) -> Void
    ) {
        if #available(iOS 14.0, *) {
            completionHandler([.banner, .sound, .badge, .list])
        } else {
            completionHandler([.alert, .sound, .badge])
        }
    }

    // Xử lý khi người dùng CHẠM VÀO THÔNG BÁO trên màn hình khóa hoặc thanh thông báo
    func userNotificationCenter(
        _ center: UNUserNotificationCenter,
        didReceive response: UNNotificationResponse,
        withCompletionHandler completionHandler: @escaping () -> Void
    ) {
        let userInfo = response.notification.request.content.userInfo
        let targetRoute = userInfo["route"] as? String ?? "#withdraw"

        print("✓ Người dùng vừa bấm vào thông báo! Điều hướng đến route:", targetRoute)

        if let mainVC = window?.rootViewController as? ViewController {
            mainVC.navigateToRoute(targetRoute)
        }

        completionHandler()
    }
}
