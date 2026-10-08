// ==============================================================================
// SERVICE WORKER CHO WFI PWA & WEB PUSH NOTIFICATIONS (CHUẨN IPHONE & ANDROID)
// ==============================================================================

self.addEventListener("install", (event) => {
  self.skipWaiting();
});

self.addEventListener("activate", (event) => {
  event.waitUntil(self.clients.claim());
});

// 1. Lắng nghe sự kiện Push thật từ Backend qua Apple Push Server (APNs) / Web Push
self.addEventListener("push", (event) => {
  let data = {
    title: "Thông báo rút tiền USDT (BEP-20)",
    body: "Lệnh rút tiền của bạn đã được xử lý thành công.",
    icon: "img/wfi_coin_hero.jpg"
  };

  if (event.data) {
    try {
      data = event.data.json();
    } catch (e) {
      data.body = event.data.text();
    }
  }

  const options = {
    body: data.body || "",
    icon: data.icon || "img/wfi_coin_hero.jpg",
    badge: data.badge || data.icon || "img/wfi_coin_hero.jpg",
    vibrate: [200, 100, 200, 100, 200],
    data: data.data || { url: "./index.html" },
    tag: data.tag || ("wfi-withdraw-" + Date.now()),
    renotify: true
  };

  event.waitUntil(
    self.registration.showNotification(data.title || "Thông báo rút tiền", options)
  );
});

// 2. Xử lý khi người dùng chạm vào thông báo trên màn hình khóa iPhone
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

// 3. Lắng nghe lệnh trực tiếp từ Client (In-App trigger)
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
