// ==============================================================================
// SERVICE WORKER CHO WFI PWA & WEB PUSH NOTIFICATIONS (CHUẨN IPHONE & ANDROID)
// ==============================================================================

self.addEventListener("install", (event) => {
  self.skipWaiting();
});

self.addEventListener("activate", (event) => {
  event.waitUntil(self.clients.claim());
});

// Xử lý khi người dùng chạm vào thông báo trên điện thoại / iPhone
self.addEventListener("notificationclick", (event) => {
  event.notification.close();
  event.waitUntil(
    clients.matchAll({ type: "window", includeUncontrolled: true }).then((clientList) => {
      for (const client of clientList) {
        if (client.url && "focus" in client) {
          return client.focus();
        }
      }
      if (clients.openWindow) {
        return clients.openWindow("./index.html");
      }
    })
  );
});

// Lắng nghe lệnh từ Client
self.addEventListener("message", (event) => {
  if (event.data && event.data.type === "SHOW_NOTIFICATION") {
    const { title, body, icon, badge, data, tag } = event.data;
    const options = {
      body: body || "",
      icon: icon || "img/wfi_coin_hero.jpg",
      badge: badge || icon || "img/wfi_coin_hero.jpg",
      vibrate: [200, 100, 200],
      data: data || {},
      tag: tag || ("wfi-withdraw-" + Date.now()),
      renotify: true
    };
    self.registration.showNotification(title || "Thông báo rút tiền", options);
  }
});
