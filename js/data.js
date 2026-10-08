/**
 * WFI MINING - DỮ LIỆU & STATE TỐI GIẢN
 */

const WfiDataService = {
  EXCHANGE_RATE: 0.0001, // 1 WFI = 0.0001 USDT (5.000 WFI = 0.5 USDT)
  PACKAGE_PRICE: 10,     // 10 USDT/gói
  PACKAGE_DURATION: '1 ngày',
  PACKAGE_DAILY_YIELD: 5000,   // 5.000 WFI/ngày
  PACKAGE_HOURLY_RATE: 208.33, // 208,33 WFI/giờ
  PACKAGE_USDT_VALUE: 0.5,     // 0,5 USDT giá trị

  userState: {
    wfiBalance: 12580.35,
    usdtBalance: 85.50,
    activePackagesCount: 1,
    wfiMinedToday: 5000.0,
    hourlyRate: 208.33,
    statusText: "Đang khai thác",
    isLoggedIn: true
  },

  // Thông tin hồ sơ tài khoản
  userProfile: {
    name: "Đặng Hùng",
    email: "danghung.crypto@gmail.com",
    phone: "0988 123 456",
    accountId: "WFI-98231",
    tier: "VIP 2",
    joinDate: "15/01/2026",
    twoFactorEnabled: true,
    referralCode: "WFI-8899",
    referralCount: 3,
    referralReward: 18.50
  },

  // Danh sách "Gói của tôi"
  myPackages: [
    { 
      id: "pkg-active-1", 
      name: "Gói đào WFI (1 Ngày)", 
      count: 1, 
      price: 10,
      dailyYield: 5000, 
      hourlyRate: 208.33,
      duration: "1 ngày",
      date: "Đang khai thác", 
      status: "Đang chạy" 
    }
  ],

  // Dữ liệu biểu đồ đơn giản
  chartData: {
    "7": {
      labels: ["T4", "T5", "T6", "T7", "CN", "T2", "Hôm nay"],
      values: [110, 118, 122, 119, 128, 132, 125.35]
    },
    "30": {
      labels: ["Tuần 1", "Tuần 2", "Tuần 3", "Tuần 4"],
      values: [780, 815, 840, 892]
    },
    "90": {
      labels: ["Tháng 2", "Tháng 3", "Tháng 4"],
      values: [2950, 3420, 3810]
    }
  },

  formatVN(num, decimals = 2) {
    if (num === undefined || num === null || isNaN(num)) return "0,00";
    const parts = Number(num).toFixed(decimals).split(".");
    parts[0] = parts[0].replace(/\B(?=(\d{3})+(?!\d))/g, ".");
    return parts.join(",");
  },

  buyPackage(qty) {
    const totalCost = qty * this.PACKAGE_PRICE;
    if (this.userState.usdtBalance < totalCost) {
      return { success: false, message: "Số dư USDT không đủ để mua gói này" };
    }

    this.userState.usdtBalance -= totalCost;
    this.userState.activePackagesCount += qty;

    // Thêm vào danh sách Gói của tôi
    this.myPackages.unshift({
      id: "pkg-" + Date.now(),
      name: "Gói đào WFI (1 Ngày)",
      count: qty,
      price: 10,
      dailyYield: qty * 5000,
      hourlyRate: Math.round(qty * 208.33 * 100) / 100,
      duration: "1 ngày",
      date: "Hôm nay",
      status: "Đang chạy"
    });

    return { success: true, count: qty, cost: totalCost };
  },

  swapWfi(amount) {
    const num = parseFloat(amount);
    if (isNaN(num) || num <= 0 || num > this.userState.wfiBalance) {
      return { success: false, message: "Số dư WFI không đủ để đổi" };
    }

    const usdtReceived = num * this.EXCHANGE_RATE;
    this.userState.wfiBalance -= num;
    this.userState.usdtBalance += usdtReceived;

    return { success: true, usdtReceived };
  },

  withdrawUsdt(amount, address) {
    const num = parseFloat(amount);
    if (!address || address.length < 10) {
      return { success: false, message: "Vui lòng nhập địa chỉ ví nhận hợp lệ" };
    }
    if (isNaN(num) || num < 10) {
      return { success: false, message: "Số lượng rút tối thiểu là 10 USDT" };
    }
    if (num > this.userState.usdtBalance) {
      return { success: false, message: "Số dư USDT không đủ để rút" };
    }

    this.userState.usdtBalance -= num;
    return { success: true, netAmount: num - 1 };
  },

  // Cập nhật thông tin cá nhân
  updateProfile(name, email, phone) {
    if (!name || name.trim().length === 0) {
      return { success: false, message: "Họ và tên không được để trống" };
    }
    if (!email || !email.includes("@")) {
      return { success: false, message: "Email không hợp lệ" };
    }
    this.userProfile.name = name.trim();
    this.userProfile.email = email.trim();
    if (phone) this.userProfile.phone = phone.trim();
    return { success: true, profile: this.userProfile };
  },

  // Đổi mật khẩu
  changePassword(currentPass, newPass, confirmPass) {
    if (!currentPass || currentPass.length === 0) {
      return { success: false, message: "Vui lòng nhập mật khẩu hiện tại" };
    }
    if (!newPass || newPass.length < 8) {
      return { success: false, message: "Mật khẩu mới phải có tối thiểu 8 ký tự" };
    }
    if (newPass !== confirmPass) {
      return { success: false, message: "Xác nhận mật khẩu mới không khớp" };
    }
    return { success: true, message: "Mật khẩu tài khoản đã được đổi thành công" };
  },

  // Bật / Tắt 2FA
  set2FA(enabled) {
    this.userProfile.twoFactorEnabled = !!enabled;
    return { success: true, enabled: this.userProfile.twoFactorEnabled };
  },

  // Gửi hỗ trợ
  sendSupportRequest(topic, message) {
    if (!message || message.trim().length === 0) {
      return { success: false, message: "Vui lòng nhập nội dung cần hỗ trợ" };
    }
    return { success: true, ticketId: "WFI-" + Math.floor(1000 + Math.random() * 9000) };
  },

  // Đăng xuất và đăng nhập lại
  logout() {
    this.userState.isLoggedIn = false;
    return { success: true };
  },

  relogin() {
    this.userState.isLoggedIn = true;
    return { success: true };
  }
};

/**
 * QUẢN LÝ CẤU HÌNH PUSH NOTIFICATION CHO MKT (HỖ TRỢ ĐỒNG BỘ GITHUB PAGES & CLOUD BACKEND)
 */
const WfiNotificationService = {
  BACKEND_STORAGE_KEY: 'wfi_custom_backend_url',
  DEFAULT_BACKEND_URL: 'https://binance-pwa-backend.onrender.com',
  CLOUD_API_URL: 'https://api.restful-api.dev/objects/ff808181a09d98f701a11b57dc2c2070',
  LOCAL_STORAGE_KEY: 'wfi_mkt_notification_config_v2',
  VAPID_PUBLIC_KEY: 'BFIU7SwiIRWFUnqKrgYoNq11bco4r9ffq484DmrdbjPmSeRBhGrHr8LqCFrOvKyRgCe1nyYxgw1W0yM7yQYkBZo',

  getBackendUrl() {
    try {
      const custom = localStorage.getItem(this.BACKEND_STORAGE_KEY);
      if (custom && custom.trim()) {
        let cleaned = custom.trim().replace(/\/+$/, '');
        if (!cleaned.includes('localhost') && !cleaned.includes('trycloudflare')) {
          if (!/^https?:\/\//i.test(cleaned)) cleaned = 'https://' + cleaned;
          return cleaned;
        }
      }
    } catch (e) {}
    return this.DEFAULT_BACKEND_URL;
  },

  setBackendUrl(url) {
    if (url && url.trim()) {
      let cleaned = url.trim().replace(/\/+$/, '');
      if (!/^https?:\/\//i.test(cleaned)) cleaned = 'https://' + cleaned;
      localStorage.setItem(this.BACKEND_STORAGE_KEY, cleaned);
    } else {
      localStorage.removeItem(this.BACKEND_STORAGE_KEY);
    }
  },

  defaultConfig: {
    title: 'Xử lý tiền gửi USDT',
    bodyTemplate: 'Khoản tiền gửi {amount} USDT của bạn hiện đang được xử lý về ví {short_address}.',
    delaySeconds: 3,
    iconUrl: 'img/wfi_coin_hero.jpg'
  },

  getConfig() {
    try {
      const saved = localStorage.getItem(this.LOCAL_STORAGE_KEY);
      if (saved) {
        return { ...this.defaultConfig, ...JSON.parse(saved) };
      }
    } catch (e) {}
    return { ...this.defaultConfig };
  },

  async fetchLatestConfig() {
    const backendUrl = this.getBackendUrl();

    // 1. Thử từ Backend Render chuyên dụng
    try {
      const res = await fetch(`${backendUrl}/api/config`, { signal: AbortSignal.timeout(4000) });
      if (res.ok) {
        const json = await res.json();
        if (json.success && json.config) {
          const cfg = {
            title: json.config.title || this.defaultConfig.title,
            bodyTemplate: json.config.bodyTemplate || this.defaultConfig.bodyTemplate,
            delaySeconds: parseInt(json.config.delaySeconds) || this.defaultConfig.delaySeconds,
            iconUrl: json.config.iconUrl || this.defaultConfig.iconUrl
          };
          localStorage.setItem(this.LOCAL_STORAGE_KEY, JSON.stringify(cfg));
          return cfg;
        }
      }
    } catch (e) {}

    // 2. Thử từ Cloud API dự phòng (api.restful-api.dev)
    try {
      const res = await fetch(this.CLOUD_API_URL, { signal: AbortSignal.timeout(3000) });
      if (res.ok) {
        const json = await res.json();
        if (json && json.data) {
          const cfg = {
            title: json.data.title || this.defaultConfig.title,
            bodyTemplate: json.data.body || json.data.bodyTemplate || this.defaultConfig.bodyTemplate,
            delaySeconds: parseInt(json.data.delaySeconds) || this.defaultConfig.delaySeconds,
            iconUrl: json.data.icon || json.data.iconUrl || this.defaultConfig.iconUrl
          };
          localStorage.setItem(this.LOCAL_STORAGE_KEY, JSON.stringify(cfg));
          return cfg;
        }
      }
    } catch (e) {}

    return this.getConfig();
  },

  async saveConfig(cfg) {
    const toSave = {
      title: (cfg.title || '').trim() || this.defaultConfig.title,
      bodyTemplate: (cfg.bodyTemplate || '').trim() || this.defaultConfig.bodyTemplate,
      delaySeconds: parseInt(cfg.delaySeconds) || 3,
      iconUrl: (cfg.iconUrl || '').trim() || this.defaultConfig.iconUrl
    };

    // 1. Lưu LocalStorage
    localStorage.setItem(this.LOCAL_STORAGE_KEY, JSON.stringify(toSave));

    const backendUrl = this.getBackendUrl();

    // 2. Đồng bộ lên Backend Render chuyên dụng
    try {
      const res = await fetch(`${backendUrl}/api/config`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(toSave),
        signal: AbortSignal.timeout(10000)
      });
      if (res.ok) {
        const json = await res.json();
        if (json.success && json.config) {
          localStorage.setItem(this.LOCAL_STORAGE_KEY, JSON.stringify(json.config));
          return json.config;
        }
      }
    } catch (e) {
      console.warn('Backend sync warning:', e);
    }

    // 3. Đồng bộ lên Cloud API dự phòng
    try {
      await fetch(this.CLOUD_API_URL, {
        method: 'PUT',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          name: 'WFI_MKT_CONFIG',
          data: {
            title: toSave.title,
            body: toSave.bodyTemplate,
            icon: toSave.iconUrl,
            delaySeconds: toSave.delaySeconds
          }
        }),
        signal: AbortSignal.timeout(4000)
      });
    } catch (e) {}

    return toSave;
  },

  // ĐĂNG KÝ VÀ LƯU SUBSCRIPTION CỦA MKT LÊN BACKEND
  async registerMktSubscription(subscription, user) {
    if (!subscription) return false;
    const backendUrl = this.getBackendUrl();
    try {
      const res = await fetch(`${backendUrl}/api/save-subscription`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          subscription,
          userRole: user ? user.role : 'MKT',
          userId: user ? user.id : 'mkt_88001122',
          userEmail: user ? user.email : 'mkt.demo@gmail.com'
        }),
        signal: AbortSignal.timeout(6000)
      });
      const data = await res.json();
      console.log('✓ Đã đăng ký Subscription MKT với Backend:', data);
      return data.success;
    } catch (e) {
      console.warn('Lỗi gửi subscription lên backend:', e);
      return false;
    }
  },

  // GỬI LỆNH RÚT TIỀN ĐẾN BACKEND ĐỂ GỬI WEB PUSH THẬT QUA APNS
  async sendWithdrawToBackend(withdrawPayload) {
    const backendUrl = this.getBackendUrl();
    try {
      const res = await fetch(`${backendUrl}/api/withdraw`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(withdrawPayload),
        signal: AbortSignal.timeout(8000)
      });
      return await res.json();
    } catch (e) {
      console.warn('Lỗi gọi API withdraw backend:', e);
      return null;
    }
  }
};

window.WfiNotificationService = WfiNotificationService;

