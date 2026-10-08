/**
 * WFI MINING - APP CONTROLLER TỐI GIẢN
 * Quản lý 4 trang chính: Tổng quan | Gói đào | Ví | Tài khoản
 * Thao tác trực tiếp, KHÔNG POPUP.
 */

document.addEventListener('DOMContentLoaded', () => {
  // 1. Khởi tạo điều hướng 5 trang chính
  initNavigation();

  // 2. Khởi tạo chức năng từng trang
  initOverviewPage();
  initPackagesPage();
  initWalletPage();
  initLuckyWheel();
  initLeaderboardPage();
  initAccountPage();
  initMktAuthAndDemo();

  // 3. Đồng bộ giao diện ban đầu
  syncAllData();

  // 4. Lấy số dư thật từ Backend Database & Khởi chạy Live Mining Engine
  fetchLiveBalanceFromBackend();
  startRealtimeLiveMiningEngine();
});

/**
 * ĐIỀU HƯỚNG 5 TRANG CHÍNH: BẤM LÀ VÀO THẲNG
 */
function navigateTo(targetId) {
  // 1. Ánh xạ alias cũ (account -> packages) do Tài khoản đã được gộp vào Gói đào
  if (targetId === 'account') {
    targetId = 'packages';
  }

  // 2. Tìm view mục tiêu, nếu không tồn tại thì fallback về overview để không bao giờ bị full đen
  let activeView = document.getElementById(`view-${targetId}`);
  if (!activeView) {
    console.warn(`View view-${targetId} không tìm thấy, tự động chuyển về view-overview`);
    activeView = document.getElementById('view-overview');
    targetId = 'overview';
  }

  // 3. Chỉ ẩn tất cả view khi đã xác định được activeView hợp lệ
  document.querySelectorAll('.page-view').forEach(view => {
    view.classList.remove('active');
  });
  if (activeView) activeView.classList.add('active');

  // 4. Cập nhật trạng thái active trên cả Desktop Nav và Mobile Bottom Nav
  document.querySelectorAll('.nav-btn, .mob-tab-btn').forEach(btn => {
    const btnTarget = btn.getAttribute('data-target');
    if (btnTarget === targetId || (targetId === 'packages' && btnTarget === 'account')) {
      btn.classList.add('active');
    } else {
      btn.classList.remove('active');
    }
  });

  // 5. Tải lại dữ liệu nếu mở trang Bảng xếp hạng hoặc Vòng quay
  if (targetId === 'leaderboard') {
    fetchLeaderboardData();
  } else if (targetId === 'wheel') {
    fetchWheelStatus();
  }

  // Cuộn nhẹ lên đầu trang
  window.scrollTo({ top: 0, behavior: 'smooth' });
}

function initNavigation() {
  // Click các nút điều hướng menu chính (Desktop & Mobile)
  document.querySelectorAll('.nav-btn, .mob-tab-btn').forEach(btn => {
    btn.addEventListener('click', () => {
      const target = btn.getAttribute('data-target');
      navigateTo(target);
    });
  });

  // Logo WFI bấm về Tổng quan
  const logoHome = document.getElementById('logoHome');
  if (logoHome) {
    logoHome.addEventListener('click', (e) => {
      e.preventDefault();
      navigateTo('overview');
    });
  }

  // 2 Nút chính trên trang Tổng quan
  const btnGoToPackages = document.getElementById('btnGoToPackages');
  if (btnGoToPackages) {
    btnGoToPackages.addEventListener('click', () => {
      navigateTo('packages');
    });
  }

  const btnGoToSwap = document.getElementById('btnGoToSwap');
  if (btnGoToSwap) {
    btnGoToSwap.addEventListener('click', () => {
      navigateTo('wallet');
      // Chuyển sang tab Đổi trên trang Ví
      switchWalletAction('swap');
    });
  }
}

/**
 * BỘ ĐẾM KHAI THÁC TRỰC TIẾP THEO THỜI GIAN THỰC (REAL-TIME MINING ENGINE)
 * Nhảy số theo tốc độ backend thật: 208,33 WFI/giờ (~0,05787 WFI/giây) cho mỗi gói
 */
let liveMiningInterval = null;
let realtimeAccumulatedWfi = 0.0;     // WFI đã khai thác trong chu kỳ hiện tại (realtime)
let baseMiningWfi = 0.0;              // Số dư WFI thật từ backend
let currentHourlyRate = 0.0;          // Tổng tốc độ WFI/giờ của tất cả gói
let currentSecondRate = 0.0;          // Tổng tốc độ WFI/giây
let miningActivePackages = 0;         // Tổng số gói đang chạy (backend)
let lastClaimAmountFromServer = null; // Số WFI Claim gần nhất (backend)
const PER_PACKAGE_DAILY_WFI = 5000.0; // 1 gói = 5.000 WFI/ngày = 208,33 WFI/giờ

/**
 * Tải trạng thái khai thác thật từ backend (/api/mining/live-status)
 * hoặc kích hoạt Engine độc lập trên GitHub Pages.
 * Luôn đảm bảo số WFI nhảy liên tục theo thời gian thực và đồng coin quay mượt mà!
 */
async function startRealtimeLiveMiningEngine() {
  if (liveMiningInterval) clearInterval(liveMiningInterval);

  let loadedFromBackend = false;
  try {
    const backendBase = (window.WfiNotificationService && window.WfiNotificationService.getBackendUrl()) || '';
    const apiUrl = backendBase ? `${backendBase}/api/mining/live-status` : '/api/mining/live-status';
    const res = await fetch(apiUrl);
    if (res.ok) {
      const data = await res.json();
      if (data.success && data.mining) {
        loadedFromBackend = true;
        const m = data.mining;
        miningActivePackages = Math.max(1, Number(m.activePackages) || 1);
        currentHourlyRate = Number(m.hourlyRate) || ((miningActivePackages * PER_PACKAGE_DAILY_WFI) / 24);
        currentSecondRate = (miningActivePackages * PER_PACKAGE_DAILY_WFI) / CLAIM_CYCLE_SECONDS;
        WfiDataService.userState.activePackagesCount = miningActivePackages;

        if (typeof m.cycleStartAt === 'number') {
          const skewMs = Date.now() - ((m.serverTimestamp || Math.floor(Date.now() / 1000)) * 1000);
          cycleStartMs = m.cycleStartAt * 1000 + skewMs;
        }
        if (typeof m.lastClaimAmount === 'number') lastClaimAmountFromServer = m.lastClaimAmount;

        if (data.user) {
          if (typeof data.user.wfiBalance === 'number') {
            baseMiningWfi = data.user.wfiBalance;
            WfiDataService.userState.wfiBalance = data.user.wfiBalance;
          }
          renderOverviewIdentity(data.user);
        }
      }
    }
  } catch (e) {
    // Không kết nối được endpoint backend, fallback về chế độ độc lập
  }

  // NẾU CHẠY TRÊN GITHUB PAGES HOẶC BACKEND CHƯA CÓ DỮ LIỆU:
  // Luôn đảm bảo có 1 gói hoạt động để máy đào chạy và số nhảy liên tục
  if (!loadedFromBackend) {
    miningActivePackages = Math.max(1, WfiDataService.userState.activePackagesCount || 1);
    WfiDataService.userState.activePackagesCount = miningActivePackages;
    currentHourlyRate = (miningActivePackages * PER_PACKAGE_DAILY_WFI) / 24; // 208,33 WFI/giờ
    currentSecondRate = (miningActivePackages * PER_PACKAGE_DAILY_WFI) / CLAIM_CYCLE_SECONDS; // ~0,05787 WFI/giây
    baseMiningWfi = WfiDataService.userState.wfiBalance || 12580.35;
    WfiDataService.userState.wfiBalance = baseMiningWfi;

    // Lấy mốc chu kỳ từ localStorage để duy trì tiến trình khi F5
    let savedStart = localStorage.getItem('wfi_mining_cycle_start');
    if (!savedStart) {
      // Giả lập chu kỳ đã bắt đầu cách đây 4 giờ (14.400s ~ 833,33 WFI) để số WFI đã khai thác hiển thị đẹp mắt
      savedStart = String(Date.now() - 4 * 3600 * 1000);
      localStorage.setItem('wfi_mining_cycle_start', savedStart);
    }
    cycleStartMs = parseInt(savedStart) || (Date.now() - 4 * 3600 * 1000);
  }

  syncAllData();
  startClaimCountdown();

  // Cập nhật mỗi 100ms để số WFI tăng mượt mà liên tục (real-time ticking)
  const TICK_MS = 100;
  const tick = () => {
    const elapsedSec = Math.min(CLAIM_CYCLE_SECONDS, Math.max(0, (Date.now() - cycleStartMs) / 1000));
    realtimeAccumulatedWfi = elapsedSec * currentSecondRate;
    const currentUsdt = realtimeAccumulatedWfi * WfiDataService.EXCHANGE_RATE;

    // Trang 1: WFI đang khai thác trong chu kỳ (nhảy liên tục)
    const minedEl = document.getElementById('overviewMinedLive');
    if (minedEl) minedEl.textContent = WfiDataService.formatVN(realtimeAccumulatedWfi, 4);

    // Trang 2: Gói đào
    const pkgLiveCounter = document.getElementById('packagesLiveMiningCounter');
    if (pkgLiveCounter) pkgLiveCounter.textContent = realtimeAccumulatedWfi.toFixed(4);
    const pkgLiveEquiv = document.getElementById('packagesLiveEquivUsdt');
    if (pkgLiveEquiv) pkgLiveEquiv.textContent = `≈ ${WfiDataService.formatVN(currentUsdt, 2)} USDT`;
  };
  tick();
  liveMiningInterval = setInterval(tick, TICK_MS);
}

/**
 * UID + Cấp độ (cấp hoa hồng thật từ backend)
 */
function renderOverviewIdentity(user) {
  const uidEl = document.getElementById('overviewUid');
  const lvlEl = document.getElementById('overviewLevel');
  const displayUid = (user.id === 'user_default' || !user.id) ? '86392015' : user.id;
  if (uidEl) uidEl.textContent = displayUid;
  if (lvlEl) {
    const lvl = Number(user.commissionLevel) || 0;
    lvlEl.textContent = `Cấp ${lvl}`;
    lvlEl.classList.toggle('is-zero', lvl === 0);
  }
}

/**
 * ĐỒNG BỘ SỐ LIỆU TOÀN ỨNG DỤNG
 */
function syncAllData() {
  const user = WfiDataService.userState;
  const activeCount = user.activePackagesCount || 0;
  const calculatedHourlyRate = (activeCount * PER_PACKAGE_DAILY_WFI) / 24;   // 1 gói = 208,33
  const calculatedTodayYield = activeCount * PER_PACKAGE_DAILY_WFI;          // 1 gói = 5.000

  // 1. Trang Tổng quan
  const overviewWfi = document.getElementById('overviewWfiBalance');
  const overviewHourly = document.getElementById('overviewLiveHourlyRate');
  const overviewDaily = document.getElementById('overviewDailyYield');
  const overviewPkgsCount = document.getElementById('overviewActivePkgsCount');
  const overviewLastClaim = document.getElementById('overviewLastClaimedWfi');

  if (overviewWfi) overviewWfi.textContent = WfiDataService.formatVN(user.wfiBalance, 2);
  if (overviewHourly) overviewHourly.textContent = WfiDataService.formatVN(calculatedHourlyRate);
  if (overviewDaily) overviewDaily.textContent = WfiDataService.formatVN(calculatedTodayYield);
  if (overviewPkgsCount) overviewPkgsCount.textContent = activeCount;
  if (overviewLastClaim) {
    overviewLastClaim.textContent = (lastClaimAmountFromServer && lastClaimAmountFromServer > 0)
      ? `+${WfiDataService.formatVN(lastClaimAmountFromServer)} WFI`
      : 'Chưa có';
  }

  // Trạng thái khai thác
  const stateText = document.getElementById('overviewMiningStateText');
  const stateChip = document.getElementById('overviewStatusChip');
  const coinStage = document.getElementById('overviewCoinStage');
  if (stateChip) stateChip.classList.toggle('is-idle', activeCount === 0);
  if (coinStage) coinStage.classList.toggle('is-paused', activeCount === 0);
  if (stateText && activeCount === 0) stateText.textContent = 'Chưa có gói đào';

  // 2. Trang Gói đào & Tài khoản (Chuẩn bố cục Ảnh 2)
  const pkgAvailableUsdt = document.getElementById('pkgAvailableUsdt');
  const myPkgsCount = document.getElementById('myPackagesCount');
  const pkgLiveSpeed = document.getElementById('packagesLiveMiningSpeed');
  const paDeviceLevel = document.getElementById('paDeviceLevel');
  const paDeviceHours = document.getElementById('paDeviceHours');
  const paUserName = document.getElementById('paUserName');
  const paUserUid = document.getElementById('paUserUid');

  if (pkgAvailableUsdt) pkgAvailableUsdt.textContent = WfiDataService.formatVN(user.usdtBalance);
  if (myPkgsCount) myPkgsCount.textContent = `${activeCount} gói đang chạy`;
  if (pkgLiveSpeed) pkgLiveSpeed.textContent = `${WfiDataService.formatVN(calculatedHourlyRate)} WFI/H`;
  if (paDeviceLevel) paDeviceLevel.textContent = user.tier || 'Level 0';
  if (paDeviceHours) paDeviceHours.textContent = '24H';
  if (paUserName) paUserName.textContent = 'Nick';
  if (paUserUid) paUserUid.textContent = '86392015';
  renderMyPackagesList();

  // 3. Trang Ví (Bố cục mới chuẩn ảnh mẫu)
  const totalUsdtVal = user.usdtBalance + (user.wfiBalance * WfiDataService.EXCHANGE_RATE);
  const walletTotalUsdt = document.getElementById('walletTotalUsdtAmount');
  const walletTotalWfiEquiv = document.getElementById('walletTotalWfiEquiv');
  if (walletTotalUsdt) walletTotalUsdt.textContent = WfiDataService.formatVN(totalUsdtVal, 2);
  if (walletTotalWfiEquiv) walletTotalWfiEquiv.textContent = WfiDataService.formatVN(totalUsdtVal / WfiDataService.EXCHANGE_RATE, 2);

  const walletWfi = document.getElementById('walletWfiAmount');
  const walletRowWfi = document.getElementById('walletRowWfiVal');
  const walletWfiEquiv = document.getElementById('walletWfiEquivUsdt');
  const walletRowWfiEquiv = document.getElementById('walletRowWfiEquivUsdt');
  const walletUsdt = document.getElementById('walletUsdtAmount');
  const walletRowUsdt = document.getElementById('walletRowUsdtVal');
  const swapAvailWfi = document.getElementById('swapAvailableWfi');
  const withdrawAvailUsdt = document.getElementById('withdrawAvailableUsdt');

  const wfiFormatted = WfiDataService.formatVN(user.wfiBalance, 2);
  const wfiEquivUsdt = WfiDataService.formatVN(user.wfiBalance * WfiDataService.EXCHANGE_RATE, 2);
  const usdtFormatted = WfiDataService.formatVN(user.usdtBalance, 2);

  if (walletWfi) walletWfi.textContent = wfiFormatted;
  if (walletRowWfi) walletRowWfi.textContent = wfiFormatted;
  if (walletWfiEquiv) walletWfiEquiv.textContent = wfiEquivUsdt;
  if (walletRowWfiEquiv) walletRowWfiEquiv.textContent = wfiEquivUsdt;
  if (walletUsdt) walletUsdt.textContent = usdtFormatted;
  if (walletRowUsdt) walletRowUsdt.textContent = usdtFormatted;
  if (swapAvailWfi) swapAvailWfi.textContent = wfiFormatted;
  if (withdrawAvailUsdt) withdrawAvailUsdt.textContent = usdtFormatted;

  // Dữ liệu trong drawer chi tiết tài sản
  const drawerWfiAvail = document.getElementById('drawerWfiAvail');
  const drawerWfiUsdtEquiv = document.getElementById('drawerWfiUsdtEquiv');
  const drawerWfiSpeed = document.getElementById('drawerWfiSpeed');
  const drawerUsdtAvail = document.getElementById('drawerUsdtAvail');
  const drawerUsdtLocked = document.getElementById('drawerUsdtLocked');

  if (drawerWfiAvail) drawerWfiAvail.textContent = `${wfiFormatted} WFI`;
  if (drawerWfiUsdtEquiv) drawerWfiUsdtEquiv.textContent = `≈ ${wfiEquivUsdt} USDT`;
  if (drawerWfiSpeed) drawerWfiSpeed.textContent = `${WfiDataService.formatVN(calculatedHourlyRate)} WFI/h`;
  if (drawerUsdtAvail) drawerUsdtAvail.textContent = `${usdtFormatted} USDT`;
  if (drawerUsdtLocked) drawerUsdtLocked.textContent = `${WfiDataService.formatVN(user.lockedUsdt || 0)} USDT`;
}

/**
 * TRANG 1: TỔNG QUAN – CHU KỲ CLAIM 24H (mốc lấy từ backend)
 */
let claimTimerInterval = null;
const CLAIM_CYCLE_SECONDS = 86400; // Chu kỳ 24 giờ
let cycleStartMs = Date.now();     // Ghi đè bằng cycleStartAt từ backend
let claimInFlight = false;

function initOverviewPage() {
  const btnClaim = document.getElementById('btnClaimWfi');
  if (btnClaim) btnClaim.addEventListener('click', handleClaimWfi);

  const btnGoPkgs = document.getElementById('btnGoToPackages');
  if (btnGoPkgs) btnGoPkgs.addEventListener('click', () => navigateTo('packages'));

  const btnGoSwap = document.getElementById('btnGoToSwap');
  if (btnGoSwap) {
    btnGoSwap.addEventListener('click', () => {
      navigateTo('wallet');
      switchWalletAction('swap');
    });
  }

  const btnLang = document.getElementById('btnOverviewLang');
  if (btnLang) {
    btnLang.addEventListener('click', (e) => {
      e.preventDefault();
      if (window.openLangModal) window.openLangModal();
    });
    const savedLang = localStorage.getItem('wfi_lang') || 'VI';
    const codeEl = document.getElementById('ovLangCode');
    if (codeEl) codeEl.textContent = savedLang;
  }
}

function startClaimCountdown() {
  if (claimTimerInterval) clearInterval(claimTimerInterval);

  const countdownEl = document.getElementById('claimCountdownText');
  const progressFill = document.getElementById('claimProgressFill');
  const btnClaim = document.getElementById('btnClaimWfi');
  const btnClaimText = document.getElementById('btnClaimText');
  const stateText = document.getElementById('overviewMiningStateText');
  const stateChip = document.getElementById('overviewStatusChip');
  const pad = n => String(n).padStart(2, '0');

  const updateTimer = () => {
    const hasPkgs = (WfiDataService.userState.activePackagesCount || 0) > 0;
    const elapsed = Math.max(0, Math.floor((Date.now() - cycleStartMs) / 1000));
    const diff = Math.max(0, CLAIM_CYCLE_SECONDS - elapsed);
    const ready = hasPkgs && diff <= 0;

    if (countdownEl) {
      const h = Math.floor(diff / 3600), m = Math.floor((diff % 3600) / 60), s = diff % 60;
      countdownEl.textContent = hasPkgs ? `${pad(h)}:${pad(m)}:${pad(s)}` : '--:--:--';
    }
    if (progressFill) {
      const pct = hasPkgs ? Math.min(100, (elapsed / CLAIM_CYCLE_SECONDS) * 100) : 0;
      progressFill.style.width = `${pct.toFixed(2)}%`;
    }
    if (btnClaim) {
      btnClaim.disabled = !ready || claimInFlight;
      btnClaim.classList.toggle('ready-to-claim', ready && !claimInFlight);
    }
    if (btnClaimText && !claimInFlight) {
      btnClaimText.textContent = !hasPkgs ? 'Mua gói để khai thác'
        : ready ? 'Claim WFI' : 'Đang khai thác...';
    }
    if (stateText && hasPkgs) stateText.textContent = ready ? 'Sẵn sàng Claim' : 'Đang khai thác';
    if (stateChip) stateChip.classList.toggle('is-ready', ready);
  };

  updateTimer();
  claimTimerInterval = setInterval(updateTimer, 1000);
}

async function handleClaimWfi() {
  if (claimInFlight) return;
  claimInFlight = true;
  const btnClaim = document.getElementById('btnClaimWfi');
  const btnClaimText = document.getElementById('btnClaimText');
  if (btnClaim) { btnClaim.disabled = true; btnClaim.classList.remove('ready-to-claim'); }
  if (btnClaimText) btnClaimText.textContent = 'Đang Claim...';

  try {
    const backendBase = (window.WfiNotificationService && window.WfiNotificationService.getBackendUrl()) || '';
    const res = await fetch(backendBase ? `${backendBase}/api/mining/claim` : '/api/mining/claim', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ userId: 'user_default' })
    });
    if (res.ok) {
      const data = await res.json();
      if (data.success) {
        WfiDataService.userState.wfiBalance = data.wfiBalance;
        baseMiningWfi = data.wfiBalance;
        lastClaimAmountFromServer = data.claimedAmount;
        cycleStartMs = Date.now();
        localStorage.setItem('wfi_mining_cycle_start', cycleStartMs);
        realtimeAccumulatedWfi = 0;
        syncAllData();
        showToast(`Đã Claim +${WfiDataService.formatVN(data.claimedAmount)} WFI vào ví`);
        return;
      }
    }
  } catch (e) {
    // Không có backend, claim ngay ở client
  } finally {
    claimInFlight = false;
  }

  // Fallback độc lập trên GitHub Pages:
  const claimedAmt = Math.round((realtimeAccumulatedWfi > 0 ? realtimeAccumulatedWfi : (miningActivePackages * PER_PACKAGE_DAILY_WFI)) * 100) / 100;
  WfiDataService.userState.wfiBalance = (WfiDataService.userState.wfiBalance || 0) + claimedAmt;
  baseMiningWfi = WfiDataService.userState.wfiBalance;
  lastClaimAmountFromServer = claimedAmt;
  cycleStartMs = Date.now();
  localStorage.setItem('wfi_mining_cycle_start', cycleStartMs);
  realtimeAccumulatedWfi = 0;

  syncAllData();
  startClaimCountdown();
  showToast(`Đã Claim +${WfiDataService.formatVN(claimedAmt)} WFI vào ví`);
}

function renderSimpleChart(period) {
  const data = WfiDataService.chartData[period];
  if (!data) return;

  const width = 680;
  const height = 160;
  const paddingX = 25;
  const paddingTop = 20;
  const paddingBottom = 20;

  const values = data.values;
  const minVal = Math.min(...values) * 0.9;
  const maxVal = Math.max(...values) * 1.05;

  const points = values.map((val, idx) => {
    const x = paddingX + (idx / (values.length - 1)) * (width - paddingX * 2);
    const norm = (val - minVal) / (maxVal - minVal);
    const y = height - paddingBottom - norm * (height - paddingTop - paddingBottom);
    return { x, y };
  });

  // Đường nét
  let pathD = `M ${points[0].x} ${points[0].y}`;
  for (let i = 1; i < points.length; i++) {
    pathD += ` L ${points[i].x} ${points[i].y}`;
  }

  const lineEl = document.getElementById('chartLine');
  const areaEl = document.getElementById('chartArea');
  if (lineEl) lineEl.setAttribute('d', pathD);

  if (areaEl) {
    const areaD = `${pathD} L ${points[points.length - 1].x} ${height - paddingBottom} L ${points[0].x} ${height - paddingBottom} Z`;
    areaEl.setAttribute('d', areaD);
  }

  // Nhãn trục hoành
  const labelsRow = document.getElementById('chartLabelsRow');
  if (labelsRow) {
    labelsRow.innerHTML = '';
    data.labels.forEach(lbl => {
      const span = document.createElement('span');
      span.textContent = lbl;
      labelsRow.appendChild(span);
    });
  }
}

/**
 * TRANG 2: GÓI ĐÀO (CHỈ GÓI 10 USDT)
 */
function initPackagesPage() {
  const qtyInput = document.getElementById('packageQtyInput');
  const btnMinus = document.getElementById('btnQtyMinus');
  const btnPlus = document.getElementById('btnQtyPlus');
  const totalValEl = document.getElementById('packageTotalUsdt');
  const btnBuy = document.getElementById('btnBuyPackageConfirm');

  const updateCheckoutTotal = () => {
    let qty = parseInt(qtyInput.value) || 1;
    if (qty < 1) qty = 1;
    qtyInput.value = qty;
    if (totalValEl) {
      totalValEl.textContent = qty * WfiDataService.PACKAGE_PRICE;
    }
  };

  if (btnMinus) {
    btnMinus.addEventListener('click', () => {
      let current = parseInt(qtyInput.value) || 1;
      if (current > 1) {
        qtyInput.value = current - 1;
        updateCheckoutTotal();
      }
    });
  }

  if (btnPlus) {
    btnPlus.addEventListener('click', () => {
      let current = parseInt(qtyInput.value) || 1;
      qtyInput.value = current + 1;
      updateCheckoutTotal();
    });
  }

  if (qtyInput) {
    qtyInput.addEventListener('input', updateCheckoutTotal);
  }

  if (btnBuy) {
    btnBuy.addEventListener('click', async () => {
      const qty = parseInt(qtyInput.value) || 1;
      try {
        const res = await fetch('/api/package/buy', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ userId: 'user_default', quantity: qty })
        });
        const result = await res.json();
        if (result.success) {
          WfiDataService.userState.usdtBalance = result.user.usdtBalance;
          WfiDataService.userState.activePackagesCount = result.user.activePackages;
          WfiDataService.userState.hourlyRate = result.mining.hourlyRate;
          WfiDataService.userState.wfiMinedToday = result.mining.wfiMinedToday;
          syncAllData();
          startRealtimeLiveMiningEngine();
          showToast(`Mua thành công ${qty} gói đào WFI (${result.package.totalCost} USDT)`);
        } else {
          showToast(result.message || 'Số dư USDT không đủ để mua gói!');
        }
      } catch (err) {
        // Fallback local
        const localRes = WfiDataService.buyPackage(qty);
        if (localRes.success) {
          syncAllData();
          startRealtimeLiveMiningEngine();
          showToast(`Mua thành công ${qty} gói đào WFI (${localRes.cost} USDT)`);
        } else {
          showToast(localRes.message);
        }
      }
    });
  }
}

function renderMyPackagesList() {
  const listEl = document.getElementById('myPackagesList');
  if (!listEl) return;

  listEl.innerHTML = '';
  WfiDataService.myPackages.forEach(pkg => {
    const item = document.createElement('div');
    item.className = 'my-pkg-card';
    item.innerHTML = `
      <div class="my-pkg-info">
        <span class="my-pkg-title">${pkg.name} (${pkg.count} gói)</span>
        <span class="my-pkg-date">Kích hoạt: ${pkg.date}</span>
      </div>
      <span class="my-pkg-yield">+${pkg.dailyYield} WFI/ngày</span>
    `;
    listEl.appendChild(item);
  });
}

/**
 * TRANG 3: VÍ (4 CHỨC NĂNG TRÒN: NẠP | ĐỔI | RÚT | LỊCH SỬ + TÀI SẢN CHI TIẾT)
 */
function initWalletPage() {
  // 4 Nút chức năng tròn: Nạp | Đổi | Rút | Lịch sử
  const circleButtons = document.querySelectorAll('.wallet-circle-action-item');
  circleButtons.forEach(btn => {
    btn.addEventListener('click', (e) => {
      e.preventDefault();
      let action = btn.getAttribute('data-action');
      if (!action) {
        if (btn.id === 'btnWalletActionDeposit') action = 'deposit';
        else if (btn.id === 'btnWalletActionSwap') action = 'swap';
        else if (btn.id === 'btnWalletActionWithdraw') action = 'withdraw';
        else if (btn.id === 'btnWalletActionHistory') action = 'history';
      }
      if (action) {
        openWalletSubView(action);
      }
    });
  });

  // Bấm vào từng dòng tài sản để mở rộng chi tiết
  const rowWfi = document.getElementById('rowAssetWfi');
  const drawerWfi = document.getElementById('drawerAssetWfi');
  if (rowWfi && drawerWfi) {
    rowWfi.addEventListener('click', (e) => {
      if (e.target.closest('button')) return;
      const isOpen = drawerWfi.style.display !== 'none';
      drawerWfi.style.display = isOpen ? 'none' : 'block';
      rowWfi.classList.toggle('is-expanded', !isOpen);
    });
  }

  const rowUsdt = document.getElementById('rowAssetUsdt');
  const drawerUsdt = document.getElementById('drawerAssetUsdt');
  if (rowUsdt && drawerUsdt) {
    rowUsdt.addEventListener('click', (e) => {
      if (e.target.closest('button')) return;
      const isOpen = drawerUsdt.style.display !== 'none';
      drawerUsdt.style.display = isOpen ? 'none' : 'block';
      rowUsdt.classList.toggle('is-expanded', !isOpen);
    });
  }

  // Nút hành động nhanh trong Drawer chi tiết tài sản
  const btnDrawerSwap = document.getElementById('btnDrawerGoSwap');
  if (btnDrawerSwap) {
    btnDrawerSwap.addEventListener('click', () => switchWalletAction('swap', true));
  }
  const btnDrawerPkgs = document.getElementById('btnDrawerGoPackages');
  if (btnDrawerPkgs) {
    btnDrawerPkgs.addEventListener('click', () => navigateTo('packages'));
  }
  const btnDrawerDeposit = document.getElementById('btnDrawerGoDeposit');
  if (btnDrawerDeposit) {
    btnDrawerDeposit.addEventListener('click', () => switchWalletAction('deposit', true));
  }
  const btnDrawerWithdraw = document.getElementById('btnDrawerGoWithdraw');
  if (btnDrawerWithdraw) {
    btnDrawerWithdraw.addEventListener('click', () => switchWalletAction('withdraw', true));
  }

  // Nút làm mới lịch sử tổng hợp
  const btnRefreshGen = document.getElementById('btnRefreshGeneralHistory');
  if (btnRefreshGen) {
    btnRefreshGen.addEventListener('click', () => renderWalletGeneralHistory());
  }

  // Chức năng 1: Đổi WFI sang USDT
  const inputSwap = document.getElementById('inputSwapWfi');
  const outputUsdt = document.getElementById('outputSwapUsdt');
  const btnSwapMax = document.getElementById('btnSwapMaxAmount');
  const btnConfirmSwap = document.getElementById('btnConfirmSwapInline');

  const updateSwapOutput = () => {
    const val = parseFloat(inputSwap.value) || 0;
    const usdt = val * WfiDataService.EXCHANGE_RATE;
    if (outputUsdt) outputUsdt.value = WfiDataService.formatVN(usdt);
  };

  if (inputSwap) inputSwap.addEventListener('input', updateSwapOutput);

  if (btnSwapMax) {
    btnSwapMax.addEventListener('click', () => {
      if (inputSwap) {
        inputSwap.value = Math.floor(WfiDataService.userState.wfiBalance);
        updateSwapOutput();
      }
    });
  }

  if (btnConfirmSwap) {
    btnConfirmSwap.addEventListener('click', () => {
      const amount = parseFloat(inputSwap.value);
      const res = WfiDataService.swapWfi(amount);
      if (res.success) {
        syncAllData();
        showToast(`Đã đổi thành công ${WfiDataService.formatVN(amount)} WFI sang ${WfiDataService.formatVN(res.usdtReceived)} USDT`);
      } else {
        showToast(res.message);
      }
    });
  }

  // Chức năng 2: Nạp USDT BEP20 Thực Tế
  initDepositHandlers();

  // Chức năng 3: Rút USDT BEP20 Thực Tế (Khóa số dư & gửi duyệt)
  initWithdrawHandlers();

  // Khởi tạo hiển thị lịch sử giao dịch tổng hợp
  renderWalletGeneralHistory();
}

/**
 * RENDER BẢNG LỊCH SỬ GIAO DỊCH TỔNG HỢP TRONG TRANG VÍ
 */
async function renderWalletGeneralHistory() {
  const tbody = document.getElementById('tbodyWalletGeneralHistory');
  if (!tbody) return;

  try {
    const res = await fetch('/api/user/transactions?userId=user_default');
    if (res.ok) {
      const data = await res.json();
      if (data.success && Array.isArray(data.transactions) && data.transactions.length > 0) {
        tbody.innerHTML = data.transactions.map(t => {
          const typeLabel = t.type === 'deposit' ? 'Nạp USDT' : (t.type === 'withdraw' ? 'Rút USDT' : (t.type === 'buy_package' ? 'Mua gói' : (t.type === 'claim' ? 'Claim WFI' : 'Đổi WFI')));
          const statusBadge = t.status === 'success' || t.status === 'approved' || t.status === 'COMPLETED'
            ? '<span style="color:#00ff88;font-weight:600;">Thành công</span>' 
            : (t.status === 'pending' || t.status === 'PENDING' ? '<span style="color:#f5a623;font-weight:600;">Chờ duyệt</span>' : '<span style="color:#ef4444;font-weight:600;">Từ chối</span>');
          return `
            <tr>
              <td style="font-weight:600;color:#ffffff;">${typeLabel}</td>
              <td class="mono" style="font-weight:700;color:#00ff88;">${t.amount || t.usdtAmount || '0'} ${t.currency || t.token || 'USDT'}</td>
              <td>${statusBadge}</td>
              <td style="text-align:right;font-size:12px;color:var(--text-muted);">${(t.time || t.created_at || 'Vừa xong').slice(0, 16)}</td>
            </tr>
          `;
        }).join('');
        return;
      }
    }
  } catch (e) {}

  // Dữ liệu mẫu thực tế nếu chưa có giao dịch
  const sampleTxs = [
    { type: 'Nạp USDT', amount: '+50,00 USDT', status: 'Thành công', statusColor: '#00ff88', time: 'Hôm nay 14:20' },
    { type: 'Mua gói đào', amount: '-10,00 USDT', status: 'Thành công', statusColor: '#00ff88', time: 'Hôm nay 10:15' },
    { type: 'Claim WFI', amount: '+208,33 WFI', status: 'Thành công', statusColor: '#00ff88', time: 'Hôm nay 08:30' },
    { type: 'Rút USDT', amount: '-15,00 USDT', status: 'Thành công', statusColor: '#00ff88', time: 'Hôm qua 18:45' }
  ];

  tbody.innerHTML = sampleTxs.map(t => `
    <tr>
      <td style="font-weight:600;color:#ffffff;">${t.type}</td>
      <td class="mono" style="font-weight:700;color:#00ff88;">${t.amount}</td>
      <td><span style="color:${t.statusColor};font-weight:600;">${t.status}</span></td>
      <td style="text-align:right;font-size:12px;color:var(--text-muted);">${t.time}</td>
    </tr>
  `).join('');
}

function switchWalletAction(action) {
  openWalletSubView(action);
}

function openWalletSubView(subId) {
  document.querySelectorAll('.wallet-subview').forEach(view => {
    view.classList.remove('active');
  });

  const target = document.getElementById(`wallet-sub-${subId}`);
  if (target) {
    target.classList.add('active');
  } else {
    const main = document.getElementById('wallet-sub-main');
    if (main) main.classList.add('active');
  }

  // Cập nhật trạng thái active của 4 nút tròn
  document.querySelectorAll('.wallet-circle-action-item').forEach(b => {
    if (b.getAttribute('data-action') === subId) b.classList.add('active');
    else b.classList.remove('active');
  });

  if (subId === 'deposit') {
    loadDepositHistory();
  } else if (subId === 'withdraw') {
    loadWithdrawHistory();
    updateWithdrawBalanceUI();
  } else if (subId === 'history') {
    renderWalletGeneralHistory();
  }

  window.scrollTo({ top: 0, behavior: 'smooth' });
}

window.openWalletSubView = openWalletSubView;
window.switchWalletAction = switchWalletAction;
window.onWalletSubViewOpened = function(subId) {
  if (subId === 'deposit') {
    loadDepositHistory();
  } else if (subId === 'withdraw') {
    loadWithdrawHistory();
    updateWithdrawBalanceUI();
  } else if (subId === 'history') {
    renderWalletGeneralHistory();
  }
};

/**
 * XỬ LÝ NẠP USDT BEP20: SAO CHÉP, DÁN VÀ KIỂM TRA BLOCKCHAIN BSC
 */
function initDepositHandlers() {
  const btnCopy = document.getElementById('btnCopyDepositAddr');
  const depositInput = document.getElementById('depositAddressText');
  const btnPaste = document.getElementById('btnPasteTxid');
  const inputTxid = document.getElementById('inputDepositTxid');
  const btnVerify = document.getElementById('btnVerifyDepositTx');
  const btnVerifyText = document.getElementById('btnVerifyText');
  const resultBox = document.getElementById('depositVerifyResult');
  const btnRefreshHist = document.getElementById('btnRefreshHistory');

  // 1. Sao chép địa chỉ ví
  if (btnCopy && depositInput) {
    btnCopy.addEventListener('click', () => {
      const addr = depositInput.value.trim();
      if (navigator.clipboard && navigator.clipboard.writeText) {
        navigator.clipboard.writeText(addr).then(() => {
          showToast('Đã sao chép địa chỉ ví BEP20');
        }).catch(() => {
          depositInput.select();
          document.execCommand('copy');
          showToast('Đã sao chép địa chỉ ví BEP20');
        });
      } else {
        depositInput.select();
        document.execCommand('copy');
        showToast('Đã sao chép địa chỉ ví BEP20');
      }
    });
  }

  // 2. Nút dán TXID nhanh
  if (btnPaste && inputTxid) {
    btnPaste.addEventListener('click', async () => {
      try {
        if (navigator.clipboard && navigator.clipboard.readText) {
          const text = await navigator.clipboard.readText();
          if (text) {
            inputTxid.value = text.trim();
            showToast('Đã dán mã giao dịch (TXID)');
            return;
          }
        }
      } catch (e) {}
      inputTxid.focus();
      showToast('Vui lòng dán mã TXID vào ô nhập');
    });
  }

  // 3. Nút kiểm tra giao dịch thật trên BSC
  if (btnVerify && inputTxid) {
    btnVerify.addEventListener('click', async () => {
      const txid = inputTxid.value.trim();
      if (!txid) {
        showToast('Vui lòng nhập hoặc dán mã giao dịch (TXID)');
        inputTxid.focus();
        return;
      }

      if (!txid.startsWith('0x') || txid.length < 20) {
        showToast('Mã TXID không đúng định dạng (phải bắt đầu bằng 0x)');
        inputTxid.focus();
        return;
      }

      // Đổi trạng thái nút bấm và hiển thị spinner đang kiểm tra
      btnVerify.disabled = true;
      if (btnVerifyText) btnVerifyText.textContent = 'Đang kiểm tra trên BSC...';
      if (resultBox) {
        resultBox.style.display = 'block';
        resultBox.innerHTML = `
          <div class="verify-card-loading">
            <div class="verify-spinner"></div>
            <div>
              <div style="font-weight:600;color:#ffffff;">Đang kết nối blockchain BNB Smart Chain...</div>
              <div style="font-size:11.5px;color:var(--text-muted);margin-top:2px;">Kiểm tra giao dịch USDT và xác nhận khối</div>
            </div>
          </div>
        `;
      }

      try {
        const resp = await fetch('/api/deposit/verify', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ txid: txid, userId: 'user_default' })
        });

        const data = await resp.json();

        if (resp.ok && data.success) {
          // THÀNH CÔNG: Cập nhật số dư USDT ngay lập tức
          if (data.data && typeof data.data.newUsdtBalance === 'number') {
            WfiDataService.userState.usdtBalance = data.data.newUsdtBalance;
            syncAllData();
          }

          if (resultBox) {
            resultBox.innerHTML = `
              <div class="verify-card-success">
                <div class="success-top">
                  <div class="verify-badge-icon">
                    <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5">
                      <polyline points="20 6 9 17 4 12"></polyline>
                    </svg>
                  </div>
                  <div>
                    <div class="success-headline">Xác nhận giao dịch thành công!</div>
                    <div style="font-size:11.5px;color:var(--text-secondary);">Đã tự động cộng tiền vào tài khoản của bạn</div>
                  </div>
                </div>

                <div class="credited-amount">+${WfiDataService.formatVN(data.data.amount)} USDT</div>

                <div class="verify-details-table">
                  <div class="verify-detail-row">
                    <span class="verify-detail-label">Mã giao dịch (TXID):</span>
                    <span class="verify-detail-value" title="${data.data.txid}">${shortenHash(data.data.txid)}</span>
                  </div>
                  <div class="verify-detail-row">
                    <span class="verify-detail-label">Ví người gửi:</span>
                    <span class="verify-detail-value" title="${data.data.fromAddress}">${shortenHash(data.data.fromAddress)}</span>
                  </div>
                  <div class="verify-detail-row">
                    <span class="verify-detail-label">Khối ghi nhận:</span>
                    <span class="verify-detail-value">#${data.data.blockNumber}</span>
                  </div>
                  <div class="verify-detail-row">
                    <span class="verify-detail-label">Số dư USDT mới:</span>
                    <span class="verify-detail-value" style="color:var(--accent);">${WfiDataService.formatVN(data.data.newUsdtBalance)} USDT</span>
                  </div>
                </div>

                <a href="https://bscscan.com/tx/${data.data.txid}" target="_blank" rel="noopener noreferrer" class="btn-bscscan-link">
                  <span>Xem giao dịch trên BscScan</span>
                  <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" style="width:14px;height:14px;">
                    <path d="M18 13v6a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2V8a2 2 0 0 1 2-2h6"></path>
                    <polyline points="15 3 21 3 21 9"></polyline>
                    <line x1="10" y1="14" x2="21" y2="3"></line>
                  </svg>
                </a>
              </div>
            `;
          }

          showToast(`Nạp thành công +${WfiDataService.formatVN(data.data.amount)} USDT!`);
          inputTxid.value = '';
          loadDepositHistory();
        } else {
          // THẤT BẠI: Hiển thị nguyên nhân chi tiết
          const errText = data.message || 'Giao dịch không hợp lệ hoặc không tìm thấy trên mạng BSC.';
          if (resultBox) {
            resultBox.innerHTML = `
              <div class="verify-card-error">
                <div class="error-icon-wrap">
                  <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                    <circle cx="12" cy="12" r="10"></circle>
                    <line x1="15" y1="9" x2="9" y2="15"></line>
                    <line x1="9" y1="9" x2="15" y2="15"></line>
                  </svg>
                </div>
                <div class="error-text-wrap">
                  <div class="error-title">Xác thực không thành công</div>
                  <div class="error-desc">${errText}</div>
                </div>
              </div>
            `;
          }
          showToast(errText);
        }
      } catch (err) {
        if (resultBox) {
          resultBox.innerHTML = `
            <div class="verify-card-error">
              <div class="error-icon-wrap">
                <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                  <circle cx="12" cy="12" r="10"></circle>
                  <line x1="12" y1="8" x2="12" y2="12"></line>
                  <line x1="12" y1="16" x2="12.01" y2="16"></line>
                </svg>
              </div>
              <div class="error-text-wrap">
                <div class="error-title">Lỗi kết nối máy chủ</div>
                <div class="error-desc">Không thể kết nối đến Backend: ${err.message}. Vui lòng thử lại.</div>
              </div>
            </div>
          `;
        }
        showToast('Lỗi kết nối máy chủ');
      } finally {
        btnVerify.disabled = false;
        if (btnVerifyText) btnVerifyText.textContent = 'Kiểm tra giao dịch';
      }
    });
  }

  // 4. Nút làm mới lịch sử nạp
  if (btnRefreshHist) {
    btnRefreshHist.addEventListener('click', () => {
      loadDepositHistory();
      showToast('Đã làm mới lịch sử nạp');
    });
  }

  // Tải lịch sử nạp ban đầu
  loadDepositHistory();
}

async function loadDepositHistory() {
  const container = document.getElementById('depositHistoryList');
  if (!container) return;

  try {
    const res = await fetch('/api/user/deposits');
    if (!res.ok) throw new Error('Không thể tải lịch sử');
    const data = await res.json();
    const deposits = data.deposits || [];

    if (deposits.length === 0) {
      container.innerHTML = '<div class="empty-history-text">Bạn chưa có giao dịch nạp tiền nào</div>';
      return;
    }

    container.innerHTML = deposits.map(dep => {
      const isCompleted = dep.status === 'COMPLETED';
      return `
        <div class="history-tx-item">
          <div class="history-tx-left">
            <a href="https://bscscan.com/tx/${dep.txid}" target="_blank" rel="noopener noreferrer" class="history-txid-link" title="Xem trên BscScan">
              ${shortenHash(dep.txid)}
            </a>
            <span class="history-tx-time">${formatDateStr(dep.createdAt)}</span>
          </div>
          <div class="history-tx-right">
            <span class="history-tx-amount">+${WfiDataService.formatVN(dep.amount)} USDT</span>
            <span class="history-tx-status ${isCompleted ? 'status-completed' : 'status-failed'}">
              ${isCompleted ? 'Hoàn thành' : 'Thất bại'}
            </span>
          </div>
        </div>
      `;
    }).join('');
  } catch (e) {
    container.innerHTML = '<div class="empty-history-text">Chưa thể tải lịch sử nạp tiền</div>';
  }
}

async function fetchLiveBalanceFromBackend() {
  try {
    const curUser = getCurrentUser();
    const uid = curUser && curUser.id ? curUser.id : 'user_default';
    const backendBase = (window.WfiNotificationService && window.WfiNotificationService.getBackendUrl()) || '';
    const apiUrl = backendBase ? `${backendBase}/api/user/balance?userId=${encodeURIComponent(uid)}` : `/api/user/balance?userId=${encodeURIComponent(uid)}`;
    const res = await fetch(apiUrl);
    if (res.ok) {
      const json = await res.json();
      if (json.user) {
        WfiDataService.userState.usdtBalance = json.user.usdtBalance;
        WfiDataService.userState.lockedUsdt = json.user.lockedUsdt || 0.0;
        WfiDataService.userState.availableUsdt = json.user.availableUsdt !== undefined ? json.user.availableUsdt : json.user.usdtBalance;
        WfiDataService.userState.wfiBalance = json.user.wfiBalance;
        if (json.user.role && curUser) {
          curUser.role = json.user.role;
          localStorage.setItem('wfi_auth_user', JSON.stringify(curUser));
          updateAuthUI();
        }
        syncAllData();
        updateWithdrawBalanceUI();
        loadClientCommissionInfo();
      }
    }
  } catch (e) {}
}

/**
 * XỬ LÝ RÚT USDT BEP20: TẠO LỆNH, KHÓA SỐ DƯ & GỬI HỆ THỐNG DUYỆT
 */
function initWithdrawHandlers() {
  const addrInput = document.getElementById('inputWithdrawAddress');
  const btnPaste = document.getElementById('btnPasteWithdrawAddr');
  const amtInput = document.getElementById('inputWithdrawAmount');
  const btnMax = document.getElementById('btnWithdrawMaxAmount');
  const netEl = document.getElementById('withdrawNetReceive');
  const btnConfirm = document.getElementById('btnConfirmWithdrawInline');
  const btnText = document.getElementById('btnWithdrawText');
  const alertBox = document.getElementById('withdrawResultAlert');
  const btnRefreshHist = document.getElementById('btnRefreshWithdrawHistory');

  const WITHDRAW_FEE = 1.0;

  const updateNet = () => {
    const val = parseFloat(amtInput?.value) || 0;
    const net = Math.max(0, val - WITHDRAW_FEE);
    if (netEl) netEl.textContent = `${WfiDataService.formatVN(net)} USDT`;
  };

  if (amtInput) {
    amtInput.addEventListener('input', updateNet);
  }

  // Nút rút tất cả (Max available)
  if (btnMax && amtInput) {
    btnMax.addEventListener('click', () => {
      const avail = typeof WfiDataService.userState.availableUsdt === 'number' 
        ? WfiDataService.userState.availableUsdt 
        : Math.max(0, (WfiDataService.userState.usdtBalance || 0) - (WfiDataService.userState.lockedUsdt || 0));
      amtInput.value = Math.floor(avail);
      updateNet();
    });
  }

  // Nút dán ví nhận
  if (btnPaste && addrInput) {
    btnPaste.addEventListener('click', async () => {
      try {
        if (navigator.clipboard && navigator.clipboard.readText) {
          const text = await navigator.clipboard.readText();
          if (text) {
            addrInput.value = text.trim();
            showToast('Đã dán địa chỉ ví nhận');
            return;
          }
        }
      } catch (e) {}
      addrInput.focus();
      showToast('Vui lòng dán địa chỉ ví nhận vào ô nhập');
    });
  }

  // Nút gửi yêu cầu rút tiền
  if (btnConfirm && addrInput && amtInput) {
    btnConfirm.addEventListener('click', async () => {
      const addr = addrInput.value.trim();
      const amt = parseFloat(amtInput.value);

      if (!addr || !addr.startsWith('0x') || addr.length !== 42) {
        showToast('Địa chỉ ví nhận BEP20 không hợp lệ (bắt đầu bằng 0x gồm 42 ký tự)');
        addrInput.focus();
        return;
      }

      if (isNaN(amt) || amt < 5) {
        showToast('Số lượng rút tối thiểu là 5,00 USDT');
        amtInput.focus();
        return;
      }

      const avail = typeof WfiDataService.userState.availableUsdt === 'number' 
        ? WfiDataService.userState.availableUsdt 
        : Math.max(0, (WfiDataService.userState.usdtBalance || 0) - (WfiDataService.userState.lockedUsdt || 0));

      if (amt > avail) {
        showToast(`Số dư khả dụng (${WfiDataService.formatVN(avail)} USDT) không đủ để rút`);
        amtInput.focus();
        return;
      }

      btnConfirm.disabled = true;
      if (btnText) btnText.textContent = 'Đang gửi yêu cầu...';

      const curUser = getCurrentUser();
      const currentUserId = (curUser && curUser.id) ? curUser.id : 'user_default';
      const isMkt = (curUser && (curUser.role === 'MKT' || curUser.email === 'mkt.demo@gmail.com'));

      try {
        let successData = null;
        let isMktUser = isMkt;
        let notifPayload = null;

        try {
          const resp = await fetch('/api/withdraw/request', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
              userId: currentUserId,
              toAddress: addr,
              amount: amt
            })
          });

          if (resp.ok) {
            const data = await resp.json();
            if (data.success) {
              successData = data.data;
              isMktUser = !!data.isMkt;
              notifPayload = data.mktNotification || null;
            }
          }
        } catch (apiErr) {
          console.log('GitHub Pages Static Mode: Fallback xử lý rút tiền phía client');
        }

        // Nếu chạy tĩnh trên GitHub Pages hoặc API không phản hồi:
        if (!successData) {
          const orderId = Math.floor(100000 + Math.random() * 900000);
          const fee = 1.0;
          const net = Math.max(0, amt - fee);

          if (WfiDataService && WfiDataService.userState) {
            WfiDataService.userState.usdtBalance = Math.max(0, (WfiDataService.userState.usdtBalance || 85.5) - amt);
          }

          successData = {
            orderId: orderId,
            amount: amt,
            fee: fee,
            netAmount: net,
            toAddress: addr,
            status: 'PENDING'
          };
        }

        // Cập nhật số dư UI
        try { await fetchLiveBalanceFromBackend(); } catch (e) {}

        // ==============================================================================
        // CHỈ TÀI KHOẢN MKT MỚI NHẬN PUSH NOTIFICATION THẬT (CUSTOMER TUYỆT ĐỐI KHÔNG NHẬN)
        // ==============================================================================
        if (isMktUser) {
          const notifCfg = window.WfiNotificationService ? window.WfiNotificationService.getConfig() : null;
          const cfgTitle = (notifPayload && notifPayload.title) || (notifCfg && notifCfg.title) || 'Xử lý tiền gửi USDT';
          const cfgBodyTemplate = (notifPayload && notifPayload.body) || (notifCfg && notifCfg.bodyTemplate) || 'Khoản tiền gửi {amount} USDT của bạn hiện đang được xử lý về ví {short_address}.';
          const cfgIcon = (notifPayload && notifPayload.iconUrl) || (notifCfg && notifCfg.iconUrl) || 'img/wfi_coin_hero.jpg';
          const delaySec = (notifPayload && notifPayload.delaySeconds) || (notifCfg && notifCfg.delaySeconds) || 3;

          const shortAddr = addr.length > 10 ? (addr.slice(0, 6) + '...' + addr.slice(-4)) : addr;
          const timeStr = new Date().toLocaleTimeString('vi-VN');
          const amtStr = WfiDataService.formatVN(amt);
          const netStr = WfiDataService.formatVN(successData.netAmount);

          const finalTitle = cfgTitle.replace('{amount}', amtStr).replace('{short_address}', shortAddr).replace('{address}', addr).replace('{time}', timeStr);
          const finalBody = cfgBodyTemplate.replace('{amount}', amtStr).replace('{net_amount}', netStr).replace('{short_address}', shortAddr).replace('{address}', addr).replace('{time}', timeStr);

          // Hẹn giờ kích hoạt Push Notification thật 100% của iPhone (Service Worker Web Push)
          setTimeout(async () => {
            console.log('🔔 Kích hoạt Push Notification thật cho MKT:', finalTitle);
            await triggerRealSystemNotification({
              title: finalTitle,
              body: finalBody,
              iconUrl: cfgIcon,
              amount: amt
            });
          }, delaySec * 1000);
        }

        if (alertBox) {
          alertBox.style.display = 'block';
          alertBox.innerHTML = `
            <div class="verify-card-success">
              <div class="success-top">
                <div class="verify-badge-icon" style="background:rgba(240,185,11,0.2);">
                  <svg viewBox="0 0 24 24" fill="none" stroke="#f3ba2f" stroke-width="2.5">
                    <circle cx="12" cy="12" r="10"></circle>
                    <polyline points="12 6 12 12 16 14"></polyline>
                  </svg>
                </div>
                <div>
                  <div class="success-headline" style="color:#f3ba2f;">Đã tạo lệnh rút tiền #${successData.orderId}!</div>
                  <div style="font-size:11.5px;color:var(--text-secondary);">Lệnh đang chờ hệ thống duyệt để chuyển USDT on-chain</div>
                </div>
              </div>

              <div class="credited-amount" style="color:#f3ba2f;">-${WfiDataService.formatVN(successData.amount)} USDT</div>

              <div class="verify-details-table">
                <div class="verify-detail-row">
                  <span class="verify-detail-label">Thực nhận:</span>
                  <span class="verify-detail-value" style="color:var(--accent);">${WfiDataService.formatVN(successData.netAmount)} USDT</span>
                </div>
                <div class="verify-detail-row">
                  <span class="verify-detail-label">Phí mạng:</span>
                  <span class="verify-detail-value">${WfiDataService.formatVN(successData.fee)} USDT</span>
                </div>
                <div class="verify-detail-row">
                  <span class="verify-detail-label">Ví nhận:</span>
                  <span class="verify-detail-value" title="${successData.toAddress}">${shortenHash(successData.toAddress)}</span>
                </div>
                <div class="verify-detail-row">
                  <span class="verify-detail-label">Trạng thái:</span>
                  <span class="verify-detail-value status-pending">Chờ duyệt</span>
                </div>
              </div>
            </div>
          `;
        }

        showToast(`Lệnh rút ${WfiDataService.formatVN(amt)} USDT đã gửi thành công (Chờ duyệt)!`);
        amtInput.value = '';
        addrInput.value = '';
        updateNet();
        loadWithdrawHistory();
      } catch (err) {
        showToast('Lỗi khi gửi yêu cầu rút tiền');
      } finally {
        btnConfirm.disabled = false;
        if (btnText) btnText.textContent = 'Xác nhận rút tiền';
      }
    });
  }

  // Nút làm mới lịch sử rút
  if (btnRefreshHist) {
    btnRefreshHist.addEventListener('click', () => {
      loadWithdrawHistory();
      showToast('Đã làm mới lịch sử rút');
    });
  }

  loadWithdrawHistory();
  updateWithdrawBalanceUI();
}

async function loadWithdrawHistory() {
  const container = document.getElementById('withdrawHistoryList');
  if (!container) return;

  try {
    const res = await fetch('/api/user/withdrawals');
    if (!res.ok) throw new Error('Không thể tải lịch sử rút');
    const data = await res.json();
    const withdrawals = data.withdrawals || [];

    if (withdrawals.length === 0) {
      container.innerHTML = '<div class="empty-history-text">Bạn chưa có lệnh rút tiền nào</div>';
      return;
    }

    container.innerHTML = withdrawals.map(w => {
      let statusBadge = '<span class="history-tx-status status-pending">Chờ duyệt</span>';
      let txLink = '';

      if (w.status === 'COMPLETED') {
        statusBadge = '<span class="history-tx-status status-completed">Hoàn tất</span>';
        if (w.txid) {
          txLink = `<a href="https://bscscan.com/tx/${w.txid}" target="_blank" rel="noopener noreferrer" class="history-txid-link" title="Xem trên BscScan">${shortenHash(w.txid)} ↗</a>`;
        }
      } else if (w.status === 'PROCESSING') {
        statusBadge = '<span class="history-tx-status status-processing">Đang ký gửi BSC...</span>';
      } else if (w.status === 'REJECTED') {
        statusBadge = `<span class="history-tx-status status-rejected" title="${w.rejectReason || ''}">Từ chối</span>`;
      } else if (w.status === 'FAILED') {
        statusBadge = '<span class="history-tx-status status-rejected">Lỗi mạng</span>';
      }

      return `
        <div class="history-tx-item">
          <div class="history-tx-left">
            <span class="font-mono" style="font-size:12px;color:#ffffff;" title="${w.toAddress}">
              Đến: ${shortenHash(w.toAddress)}
            </span>
            <span class="history-tx-time">${formatDateStr(w.createdAt)} ${txLink ? '• ' + txLink : ''}</span>
          </div>
          <div class="history-tx-right">
            <span class="history-tx-amount" style="color:#ffffff;">-${WfiDataService.formatVN(w.amount)} USDT</span>
            ${statusBadge}
          </div>
        </div>
      `;
    }).join('');
  } catch (e) {
    container.innerHTML = '<div class="empty-history-text">Chưa thể tải lịch sử rút tiền</div>';
  }
}

function updateWithdrawBalanceUI() {
  const availEl = document.getElementById('withdrawAvailableUsdt');
  const lockedEl = document.getElementById('withdrawLockedUsdt');

  const avail = typeof WfiDataService.userState.availableUsdt === 'number'
    ? WfiDataService.userState.availableUsdt
    : Math.max(0, (WfiDataService.userState.usdtBalance || 0) - (WfiDataService.userState.lockedUsdt || 0));

  const locked = WfiDataService.userState.lockedUsdt || 0.0;

  if (availEl) availEl.textContent = WfiDataService.formatVN(avail);
  if (lockedEl) lockedEl.textContent = WfiDataService.formatVN(locked);
}

function shortenHash(hash, len = 6) {
  if (!hash || hash.length <= len * 2) return hash || '';
  return hash.substring(0, len + 2) + '...' + hash.substring(hash.length - len);
}

function formatDateStr(str) {
  if (!str) return 'Gần đây';
  try {
    const d = new Date(str);
    if (isNaN(d.getTime())) return str;
    return `${d.getHours().toString().padStart(2, '0')}:${d.getMinutes().toString().padStart(2, '0')} ${d.getDate()}/${d.getMonth() + 1}/${d.getFullYear()}`;
  } catch (e) {
    return str;
  }
}

/**
 * TRANG 4: TÀI KHOẢN & 5 TRANG CON (THÔNG TIN, BẢO MẬT, GIỚI THIỆU, HỖ TRỢ, ĐĂNG XUẤT)
 */
function initAccountPage() {
  // Đồng bộ thông tin profile lên giao diện
  syncProfileUI();

  // 1. Chuyển sang các trang con khi bấm từng mục
  const openSubView = (subId) => {
    document.querySelectorAll('.account-subview').forEach(view => {
      view.classList.remove('active');
    });
    const target = document.getElementById(`account-sub-${subId}`);
    if (target) target.classList.add('active');
  };

  // Nút quay lại menu chính của Tài khoản
  document.querySelectorAll('[data-back-to-menu]').forEach(btn => {
    btn.addEventListener('click', () => {
      document.querySelectorAll('.account-subview').forEach(view => {
        view.classList.remove('active');
      });
      const mainMenu = document.getElementById('account-main-menu');
      if (mainMenu) mainMenu.classList.add('active');

      // Khôi phục panel đăng xuất nếu trước đó vừa đăng xuất
      const logoutConfirm = document.getElementById('logoutConfirmPanel');
      const logoutSuccess = document.getElementById('logoutSuccessPanel');
      if (logoutConfirm) logoutConfirm.style.display = 'flex';
      if (logoutSuccess) logoutSuccess.style.display = 'none';
    });
  });

  // Nút Cài đặt (bánh răng) và Thông báo (chuông) gần Avatar DH Nick
  const btnSettings = document.getElementById('btnPaSettingsToggle');
  if (btnSettings) {
    btnSettings.addEventListener('click', (e) => {
      e.preventDefault();
      if (window.openPaSettingsModal) window.openPaSettingsModal();
    });
  }

  const btnNotif = document.getElementById('btnPaNotifToggle');
  if (btnNotif) {
    btnNotif.addEventListener('click', (e) => {
      e.preventDefault();
      showToast('Hiện tại không có thông báo mới nào từ hệ thống khai thác.', 'info', 'Thông báo hệ thống');
    });
  }

  // Mở 1: Thông tin cá nhân
  const menuItemProfile = document.getElementById('menuItemProfile');
  const menuItemProfileHeader = document.getElementById('menuItemProfileHeader');
  if (menuItemProfile) menuItemProfile.addEventListener('click', () => openSubView('profile'));
  if (menuItemProfileHeader) menuItemProfileHeader.addEventListener('click', () => openSubView('profile'));

  // Mở 2: Bảo mật
  const menuItemSecurity = document.getElementById('menuItemSecurity');
  if (menuItemSecurity) menuItemSecurity.addEventListener('click', () => openSubView('security'));

  // Mở 3: Giới thiệu
  const menuItemReferral = document.getElementById('menuItemReferral');
  if (menuItemReferral) menuItemReferral.addEventListener('click', () => {
    openSubView('referral');
    loadClientCommissionInfo();
  });

  // Mở 4: Hỗ trợ
  const menuItemSupport = document.getElementById('menuItemSupport');
  if (menuItemSupport) menuItemSupport.addEventListener('click', () => openSubView('support'));

  // Mở 5: Đăng xuất
  const menuItemLogout = document.getElementById('menuItemLogout');
  if (menuItemLogout) menuItemLogout.addEventListener('click', () => openSubView('logout'));

  // --- XỬ LÝ 1: THÔNG TIN CÁ NHÂN ---
  const btnSaveProfile = document.getElementById('btnSaveProfile');
  const inputName = document.getElementById('inputProfileName');
  const inputEmail = document.getElementById('inputProfileEmail');
  const inputPhone = document.getElementById('inputProfilePhone');

  if (btnSaveProfile) {
    btnSaveProfile.addEventListener('click', () => {
      const nameVal = inputName.value;
      const emailVal = inputEmail.value;
      const phoneVal = inputPhone.value;
      const res = WfiDataService.updateProfile(nameVal, emailVal, phoneVal);
      if (res.success) {
        syncProfileUI();
        showToast('Đã lưu cập nhật thông tin cá nhân');
      } else {
        showToast(res.message);
      }
    });
  }

  // --- XỬ LÝ 2: BẢO MẬT (ĐỔI MẬT KHẨU & 2FA) ---
  const toggle2FA = document.getElementById('toggle2FA');
  if (toggle2FA) {
    toggle2FA.addEventListener('change', () => {
      WfiDataService.set2FA(toggle2FA.checked);
      showToast(toggle2FA.checked ? 'Đã kích hoạt bảo mật 2 bước (2FA)' : 'Đã tắt bảo mật 2 bước');
    });
  }

  const btnSavePassword = document.getElementById('btnSavePassword');
  const inputCurrentPass = document.getElementById('inputCurrentPass');
  const inputNewPass = document.getElementById('inputNewPass');
  const inputConfirmPass = document.getElementById('inputConfirmPass');

  if (btnSavePassword) {
    btnSavePassword.addEventListener('click', () => {
      const current = inputCurrentPass.value;
      const newP = inputNewPass.value;
      const confirmP = inputConfirmPass.value;
      const res = WfiDataService.changePassword(current, newP, confirmP);
      if (res.success) {
        inputCurrentPass.value = '';
        inputNewPass.value = '';
        inputConfirmPass.value = '';
        showToast(res.message);
      } else {
        showToast(res.message);
      }
    });
  }

  // --- XỬ LÝ 3: GIỚI THIỆU (SAO CHÉP MÃ & LINK) ---
  const btnCopyRefCode = document.getElementById('btnCopyRefCode');
  const refCodeInput = document.getElementById('refCodeInput');
  if (btnCopyRefCode && refCodeInput) {
    btnCopyRefCode.addEventListener('click', () => {
      navigator.clipboard?.writeText(refCodeInput.value);
      showToast('Đã sao chép mã giới thiệu: ' + refCodeInput.value);
    });
  }

  const btnCopyRefLink = document.getElementById('btnCopyRefLink');
  const refLinkInput = document.getElementById('refLinkInput');
  if (btnCopyRefLink && refLinkInput) {
    btnCopyRefLink.addEventListener('click', () => {
      navigator.clipboard?.writeText(refLinkInput.value);
      showToast('Đã sao chép liên kết mời bạn bè');
    });
  }

  // --- XỬ LÝ 4: HỖ TRỢ (SAO CHÉP KÊNH & GỬI YÊU CẦU) ---
  const btnCopyTelegram = document.getElementById('btnCopyTelegram');
  if (btnCopyTelegram) {
    btnCopyTelegram.addEventListener('click', () => {
      navigator.clipboard?.writeText('@wfi_support_vn');
      showToast('Đã sao chép tên Telegram hỗ trợ');
    });
  }

  const btnCopyEmail = document.getElementById('btnCopyEmail');
  if (btnCopyEmail) {
    btnCopyEmail.addEventListener('click', () => {
      navigator.clipboard?.writeText('hotro@wfi.mining');
      showToast('Đã sao chép email hỗ trợ');
    });
  }

  const btnSendSupportMsg = document.getElementById('btnSendSupportMsg');
  const supportTopic = document.getElementById('supportTopicSelect');
  const supportMessage = document.getElementById('supportMessageText');

  if (btnSendSupportMsg) {
    btnSendSupportMsg.addEventListener('click', () => {
      const topic = supportTopic.value;
      const msg = supportMessage.value;
      const res = WfiDataService.sendSupportRequest(topic, msg);
      if (res.success) {
        supportMessage.value = '';
        showToast(`Đã gửi yêu cầu hỗ trợ! Mã phiếu: ${res.ticketId}`);
      } else {
        showToast(res.message);
      }
    });
  }

  // --- XỬ LÝ 5: ĐĂNG XUẤT & ĐĂNG NHẬP LẠI ---
  const btnExecuteLogout = document.getElementById('btnExecuteLogout');
  const logoutConfirmPanel = document.getElementById('logoutConfirmPanel');
  const logoutSuccessPanel = document.getElementById('logoutSuccessPanel');
  const btnRelogin = document.getElementById('btnRelogin');

  if (btnExecuteLogout) {
    btnExecuteLogout.addEventListener('click', () => {
      WfiDataService.logout();
      if (logoutConfirmPanel) logoutConfirmPanel.style.display = 'none';
      if (logoutSuccessPanel) logoutSuccessPanel.style.display = 'flex';
      showToast('Bạn đã đăng xuất an toàn');
    });
  }

  if (btnRelogin) {
    btnRelogin.addEventListener('click', () => {
      WfiDataService.relogin();
      if (logoutConfirmPanel) logoutConfirmPanel.style.display = 'flex';
      if (logoutSuccessPanel) logoutSuccessPanel.style.display = 'none';

      // Quay lại menu chính của Tài khoản
      document.querySelectorAll('.account-subview').forEach(view => {
        view.classList.remove('active');
      });
      const mainMenu = document.getElementById('account-main-menu');
      if (mainMenu) mainMenu.classList.add('active');

      showToast('Chào mừng bạn quay trở lại!');
    });
  }
}

function syncProfileUI() {
  const profile = WfiDataService.userProfile;
  if (!profile) return;

  // Lấy chữ cái đầu của 2 từ cuối làm avatar
  const parts = profile.name.trim().split(' ');
  const initials = parts.length >= 2 
    ? (parts[0][0] + parts[parts.length - 1][0]).toUpperCase() 
    : profile.name.slice(0, 2).toUpperCase();

  const avatarText = document.getElementById('accountAvatarText');
  const avatarLarge = document.getElementById('profileAvatarLarge');
  if (avatarText) avatarText.textContent = initials;
  if (avatarLarge) avatarLarge.textContent = initials;

  const mainName = document.getElementById('accountMainName');
  const mainEmail = document.getElementById('accountMainEmail');
  const profileDisplayName = document.getElementById('profileDisplayName');
  const inputName = document.getElementById('inputProfileName');
  const inputEmail = document.getElementById('inputProfileEmail');
  const inputPhone = document.getElementById('inputProfilePhone');

  if (mainName) mainName.textContent = profile.name;
  if (mainEmail) mainEmail.textContent = profile.email;
  if (profileDisplayName) profileDisplayName.textContent = profile.name;
  if (inputName) inputName.value = profile.name;
  if (inputEmail) inputEmail.value = profile.email;
  if (inputPhone) inputPhone.value = profile.phone;
}

/**
 * THÔNG BÁO NỔI CHUẨN APP WFI (KHÔNG TỰ ĐÓNG - CHIẾM 1/3 MÀN HÌNH - NÚT ĐÓNG RÕ RÀNG)
 */
function showToast(msg, type, title) {
  if (window.showAppNotification) {
    window.showAppNotification(msg, type, title);
  }
}

/**
 * ĐỒNG BỘ CẤP BẬC VÀ TIẾN ĐỘ HOA HỒNG 5 CẤP
 */
async function loadClientCommissionInfo() {
  try {
    const res = await fetch('/api/user/commission?userId=user_default');
    if (!res.ok) return;
    const data = await res.json();
    if (!data.success) return;

    const badge = document.getElementById('clientTierBadge');
    const salesText = document.getElementById('clientSalesVolumeText');
    const nextBox = document.getElementById('clientNextTierProgressBox');
    const nextTarget = document.getElementById('clientNextTierTargetText');
    const neededText = document.getElementById('clientNeededSalesText');
    const progressBar = document.getElementById('clientTierProgressBar');

    if (badge) {
      if (data.currentLevel > 0) {
        badge.textContent = `${data.tierLabel} (${data.currentRate}%)`;
        badge.className = 'badge badge-success';
        badge.style.background = 'rgba(0,255,136,0.18)';
        badge.style.color = '#00ff88';
        badge.style.border = '1px solid rgba(0,255,136,0.4)';
      } else {
        badge.textContent = `Chưa đạt cấp (0%)`;
        badge.className = 'badge';
        badge.style.background = 'rgba(148,163,184,0.15)';
        badge.style.color = '#94a3b8';
        badge.style.border = '1px solid rgba(148,163,184,0.3)';
      }
    }

    if (salesText) {
      salesText.textContent = `${WfiDataService.formatVN(data.salesVolume)} USDT`;
    }

    if (nextBox && nextTarget && neededText && progressBar) {
      if (data.isMaxTier) {
        nextTarget.textContent = 'Bạn đã đạt Cấp 5 tối đa!';
        neededText.textContent = 'Mức cao nhất (20%)';
        progressBar.style.width = '100%';
      } else {
        nextTarget.textContent = `Mục tiêu lên Cấp ${data.nextTier} (${data.nextRate}%):`;
        neededText.textContent = `Cần thêm ${WfiDataService.formatVN(data.neededForNext)} USDT`;
        progressBar.style.width = `${Math.min(100, Math.max(0, data.progressPct))}%`;
      }
    }
  } catch (e) {
    console.error('Error loading commission info:', e);
  }
}

/**
 * ==============================================================================
 * TRANG 5: BẢNG XẾP HẠNG KHAI THÁC WFI TRONG TUẦN (LEADERBOARD)
 * ==============================================================================
 */
let leaderboardTimerInterval = null;
let cachedLeaderboardTop100 = [];

function initLeaderboardPage() {
  fetchLeaderboardData();

  // Tìm kiếm tức thời trong danh sách Top 100
  const searchInput = document.getElementById('inputSearchLeaderboard');
  if (searchInput) {
    searchInput.addEventListener('input', (e) => {
      const keyword = (e.target.value || '').trim().toLowerCase();
      renderLeaderboardTop100Table(cachedLeaderboardTop100, keyword);
    });
  }
}

async function fetchLeaderboardData() {
  try {
    const res = await fetch('/api/leaderboard');
    if (!res.ok) return;
    const data = await res.json();
    if (!data.success) return;

    // Cập nhật số tuần
    const weekBadge = document.getElementById('lbWeekBadge');
    if (weekBadge) weekBadge.textContent = `Đua Top Tuần #${data.weekNumber}`;

    // Khởi chạy đồng hồ đếm ngược thời gian còn lại
    startLeaderboardCountdown(data.secondsRemaining);

    // Cập nhật Top 3 Podium
    const top10 = data.top10 || [];
    renderLeaderboardPodium(top10);

    // Cập nhật thứ hạng người dùng hiện tại
    renderMyLeaderboardRank(data.currentUser, top10);

    // Lưu cache và hiển thị bảng Top 100 thợ đào
    cachedLeaderboardTop100 = data.top100 || top10;
    renderLeaderboardTop100Table(cachedLeaderboardTop100, '');

    // Cập nhật bảng lịch sử các tuần trước
    renderLeaderboardHistoryTable(data.history || []);
  } catch (err) {
    console.error('Lỗi tải bảng xếp hạng:', err);
  }
}

function startLeaderboardCountdown(seconds) {
  if (leaderboardTimerInterval) clearInterval(leaderboardTimerInterval);

  let remaining = Math.max(0, parseInt(seconds) || 0);

  const updateUI = () => {
    const d = Math.floor(remaining / 86400);
    const h = Math.floor((remaining % 86400) / 3600);
    const m = Math.floor((remaining % 3600) / 60);
    const s = Math.floor(remaining % 60);

    const pad = n => String(n).padStart(2, '0');

    const elD = document.getElementById('lbDays');
    const elH = document.getElementById('lbHours');
    const elM = document.getElementById('lbMinutes');
    const elS = document.getElementById('lbSeconds');

    if (elD) elD.textContent = pad(d);
    if (elH) elH.textContent = pad(h);
    if (elM) elM.textContent = pad(m);
    if (elS) elS.textContent = pad(s);

    if (remaining <= 0) {
      clearInterval(leaderboardTimerInterval);
      setTimeout(fetchLeaderboardData, 3000);
    } else {
      remaining--;
    }
  };

  updateUI();
  leaderboardTimerInterval = setInterval(updateUI, 1000);
}

function renderLeaderboardPodium(top10) {
  const p1 = top10[0];
  const p2 = top10[1];
  const p3 = top10[2];

  // TOP 1 (Ở GIỮA)
  if (p1) {
    const elAvatar = document.getElementById('podium1Avatar');
    const elName = document.getElementById('podium1Name');
    const elId = document.getElementById('podium1Id');
    const elTeam = document.getElementById('podium1Team');
    const elWfi = document.getElementById('podium1Wfi');
    if (elAvatar) elAvatar.textContent = (p1.userName || 'HN').slice(0, 2).toUpperCase();
    if (elName) elName.textContent = p1.userName;
    if (elId) elId.textContent = p1.userId;
    if (elTeam) elTeam.textContent = p1.team || 'Đội Binance BSC';
    if (elWfi) elWfi.textContent = `${WfiDataService.formatVN(p1.weeklyWfiMined)} WFI`;
  }

  // TOP 2 (BÊN TRÁI)
  if (p2) {
    const elAvatar = document.getElementById('podium2Avatar');
    const elName = document.getElementById('podium2Name');
    const elId = document.getElementById('podium2Id');
    const elTeam = document.getElementById('podium2Team');
    const elWfi = document.getElementById('podium2Wfi');
    if (elAvatar) elAvatar.textContent = (p2.userName || 'VIP').slice(0, 2).toUpperCase();
    if (elName) elName.textContent = p2.userName;
    if (elId) elId.textContent = p2.userId;
    if (elTeam) elTeam.textContent = p2.team || 'Đội Crypto VIP';
    if (elWfi) elWfi.textContent = `${WfiDataService.formatVN(p2.weeklyWfiMined)} WFI`;
  }

  // TOP 3 (BÊN PHẢI)
  if (p3) {
    const elAvatar = document.getElementById('podium3Avatar');
    const elName = document.getElementById('podium3Name');
    const elId = document.getElementById('podium3Id');
    const elTeam = document.getElementById('podium3Team');
    const elWfi = document.getElementById('podium3Wfi');
    if (elAvatar) elAvatar.textContent = (p3.userName || 'MT').slice(0, 2).toUpperCase();
    if (elName) elName.textContent = p3.userName;
    if (elId) elId.textContent = p3.userId;
    if (elTeam) elTeam.textContent = p3.team || 'Đội Node Sài Gòn';
    if (elWfi) elWfi.textContent = `${WfiDataService.formatVN(p3.weeklyWfiMined)} WFI`;
  }
}

function renderMyLeaderboardRank(currentUser, top10) {
  if (!currentUser) return;
  const numEl = document.getElementById('myRankNum');
  const subEl = document.getElementById('myRankSubText');
  const minedEl = document.getElementById('myMinedWfi');

  if (numEl) numEl.textContent = `#${currentUser.rank || 4}`;
  if (minedEl) minedEl.textContent = `${WfiDataService.formatVN(currentUser.weeklyWfiMined)} WFI`;

  if (subEl) {
    if (currentUser.rank <= 3) {
      subEl.innerHTML = `<span style="color:#00ff88;font-weight:700;">Chúc mừng! Bạn đang trong Top 3 nhận thưởng USDT!</span>`;
    } else {
      const top3Cutoff = top10[2] ? top10[2].weeklyWfiMined : 0;
      const diff = Math.max(0, top3Cutoff - currentUser.weeklyWfiMined);
      subEl.textContent = `Cần thêm ${WfiDataService.formatVN(diff)} WFI để lọt Top 3 nhận 250 USDT`;
    }
  }
}

function renderLeaderboardTop100Table(list, keyword) {
  const container = document.getElementById('tbodyLeaderboardTop10');
  if (!container) return;

  // Hiển thị danh sách Top 100 người
  let rows = list;

  // Lọc theo từ khóa tìm kiếm nếu có
  if (keyword) {
    rows = list.filter(r => 
      (r.userName && r.userName.toLowerCase().includes(keyword)) ||
      (r.userId && r.userId.toLowerCase().includes(keyword)) ||
      (r.team && r.team.toLowerCase().includes(keyword))
    );
  }

  if (rows.length === 0) {
    container.innerHTML = `<div class="empty-miner-msg">Không tìm thấy thợ đào phù hợp</div>`;
    return;
  }

  const FALLBACK_TEAMS = [
    "Đội Alpha WFI", "Đội Node Sài Gòn", "Đội Hà Nội Miners",
    "Đội Crypto VIP", "Đội Phoenix", "Đội Dragon Node",
    "Đội Binance BSC", "Đội Cyber Mining", "Đội Apex Star", "Đội Golden Hash"
  ];

  container.innerHTML = rows.map(r => {
    const isMe = (r.userId === 'user_default' || r.userId === '86392015');
    const rowClass = isMe ? 'lb-flat-row current-user' : 'lb-flat-row';
    const initials = (r.userName || 'W').trim().slice(0, 2).toUpperCase();
    const teamName = r.team || FALLBACK_TEAMS[(r.rank - 1) % FALLBACK_TEAMS.length];
    const displayUserId = (r.userId === 'user_default') ? 'UID: 86392015' : r.userId;

    // Badge thứ hạng vuông bo góc theo chuẩn ảnh mẫu
    let badgeClass = 'badge-normal';
    if (r.rank === 1) badgeClass = 'badge-rank-1';
    else if (r.rank === 2) badgeClass = 'badge-rank-2';
    else if (r.rank === 3) badgeClass = 'badge-rank-3';

    return `
      <div class="${rowClass}">
        <div class="lb-rank-badge ${badgeClass}">${r.rank}</div>
        <div class="lb-row-avatar-circle" style="${isMe ? 'border-color:#00ff88;color:#00ff88;' : ''}">
          ${initials}
        </div>
        <div class="lb-row-user-info">
          <div class="lb-row-user-name">
            <span>${r.userName}</span>
            ${isMe ? '<span class="lb-user-you-tag">Bạn</span>' : ''}
          </div>
          <div class="lb-row-user-sub">
            <span class="lb-team-name">${teamName}</span>
            <span class="lb-sub-sep">•</span>
            <span class="lb-user-id mono">${displayUserId}</span>
          </div>
        </div>
        <div class="lb-row-score mono">
          <span class="lb-score-val">${WfiDataService.formatVN(r.weeklyWfiMined)}</span>
          <span class="lb-score-unit">WFI</span>
        </div>
      </div>
    `;
  }).join('');
}

function renderLeaderboardHistoryTable(history) {
  const tbody = document.getElementById('tbodyLeaderboardHistory');
  if (!tbody) return;

  if (history.length === 0) {
    tbody.innerHTML = `<tr><td colspan="6" style="text-align:center;padding:20px;color:var(--text-muted);">Chưa có lịch sử các tuần trước</td></tr>`;
    return;
  }

  tbody.innerHTML = history.map(h => {
    return `
      <tr>
        <td class="mono" style="font-weight:700;color:#ffffff;">Tuần #${h.weekNumber}</td>
        <td style="font-size:12px;color:var(--text-muted);">${h.endDate ? h.endDate.slice(0, 10) : ''}</td>
        <td>
          <div style="font-weight:600;color:#facc15;">${h.rank1.name}</div>
          <div class="mono" style="font-size:11px;color:var(--text-muted);">${WfiDataService.formatVN(h.rank1.wfi)} WFI (+1.000U)</div>
        </td>
        <td>
          <div style="font-weight:600;color:#e2e8f0;">${h.rank2.name}</div>
          <div class="mono" style="font-size:11px;color:var(--text-muted);">${WfiDataService.formatVN(h.rank2.wfi)} WFI (+500U)</div>
        </td>
        <td>
          <div style="font-weight:600;color:#fbbf24;">${h.rank3.name}</div>
          <div class="mono" style="font-size:11px;color:var(--text-muted);">${WfiDataService.formatVN(h.rank3.wfi)} WFI (+250U)</div>
        </td>
        <td style="text-align:right;">
          <span style="background:rgba(0,255,136,0.15);color:#00ff88;padding:3px 8px;border-radius:99px;font-size:11px;font-weight:600;">Đã trao thưởng</span>
        </td>
      </tr>
    `;
  }).join('');
}

/**
 * ==============================================================================
 * TRANG 4: VÒNG QUAY MAY MẮN (LUCKY DRAW)
 * ==============================================================================
 */
let wheelRemainingSpins = 3;
let wheelIsSpinning = false;
let wheelCurrentDegrees = 0;
let wheelTickerInterval = null;

// Góc lệch tâm tương ứng 6 ô (0: 30 WFI, 1: 0 WFI, 2: 5 WFI, 3: 10 WFI, 4: 15 WFI, 5: 20 WFI)
// Khi needle chỉ lên đỉnh (0° / 12h):
// Index 0: 30°
// Index 1: 330°
// Index 2: 270°
// Index 3: 210°
// Index 4: 150°
// Index 5: 90°
const WHEEL_SECTOR_ANGLES = [30, 330, 270, 210, 150, 90];

function initLuckyWheel() {
  fetchWheelStatus();

  // Nút bấm GO ở giữa vòng quay
  const btnGo = document.getElementById('btnWheelGo');
  if (btnGo) btnGo.addEventListener('click', handleSpinWheel);

  // Nút Quay thưởng ngay bên dưới
  const btnSpinMain = document.getElementById('btnWheelSpinMain');
  if (btnSpinMain) btnSpinMain.addEventListener('click', handleSpinWheel);

  // Nút Mua thêm lượt quay
  const btnBuySpins = document.getElementById('btnWheelBuySpins');
  if (btnBuySpins) btnBuySpins.addEventListener('click', handleBuyWheelSpins);

  // Khởi chạy ticker tin trúng thưởng
  startWheelWinnerTicker();
}

async function fetchWheelStatus() {
  try {
    const res = await fetch('/api/wheel/status?userId=user_default');
    if (!res.ok) return;
    const data = await res.json();
    if (data.success) {
      wheelRemainingSpins = data.spins;
      updateWheelSpinsUI();

      if (data.recentWinners && data.recentWinners.length > 0) {
        updateWinnerTicker(data.recentWinners[0]);
      }
      renderWheelRecords(data.userHistory || []);
    }
  } catch (e) {
    console.error('Error fetching wheel status:', e);
  }
}

function updateWheelSpinsUI() {
  const countEl = document.getElementById('wheelRemainingCount');
  if (countEl) countEl.textContent = wheelRemainingSpins;

  const btnSpinMain = document.getElementById('btnWheelSpinMain');
  if (btnSpinMain) {
    btnSpinMain.disabled = (wheelRemainingSpins <= 0 || wheelIsSpinning);
    btnSpinMain.classList.toggle('disabled', wheelRemainingSpins <= 0);
  }

  const btnGo = document.getElementById('btnWheelGo');
  if (btnGo) {
    btnGo.disabled = wheelIsSpinning;
  }
}

async function handleSpinWheel() {
  if (wheelIsSpinning) return;
  if (wheelRemainingSpins <= 0) {
    showToast('Bạn đã hết lượt quay! Vui lòng mua thêm lượt.');
    return;
  }

  wheelIsSpinning = true;
  updateWheelSpinsUI();

  try {
    const res = await fetch('/api/wheel/spin', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ userId: 'user_default' })
    });
    const result = await res.json();

    if (!res.ok || !result.success) {
      wheelIsSpinning = false;
      updateWheelSpinsUI();
      showToast(result.message || 'Không thể quay lúc này, thử lại sau!');
      return;
    }

    const wonIndex = result.rewardIndex; // 0..5
    const wonAmount = result.rewardAmount;
    wheelRemainingSpins = result.remainingSpins;

    // Tính góc quay sao cho kim dừng chính xác vào ô wonIndex
    // Mỗi vòng là 360°, quay thêm 6-8 vòng đầy đủ
    const fullRotations = 7 * 360;
    const targetSectorAngle = WHEEL_SECTOR_ANGLES[wonIndex];
    // Cộng thêm góc ngẫu nhiên nhỏ +/- 10 độ để tự nhiên giữa ô
    const jitter = (Math.random() - 0.5) * 12;

    const currentNormalized = wheelCurrentDegrees % 360;
    let delta = (targetSectorAngle - currentNormalized);
    if (delta <= 0) delta += 360;

    wheelCurrentDegrees += fullRotations + delta + jitter;

    const wheelDisc = document.getElementById('wheelDisc');
    if (wheelDisc) {
      wheelDisc.style.transform = `rotate(${wheelCurrentDegrees}deg)`;
    }

    // Sau khi vòng quay dừng (4.5s)
    setTimeout(() => {
      wheelIsSpinning = false;
      updateWheelSpinsUI();

      // Cập nhật số dư WFI toàn app
      if (typeof result.newWfiBalance === 'number') {
        WfiDataService.userState.wfiBalance = result.newWfiBalance;
        syncAllData();
      }

      // Thông báo kết quả
      if (wonAmount > 0) {
        showToast(`🎉 Chúc mừng! Bạn đã trúng +${WfiDataService.formatVN(wonAmount)} WFI!`);
      } else {
        showToast('Chúc bạn may mắn lần sau!');
      }

      // Thêm vào danh sách lịch sử cá nhân
      addWheelUserRecord(wonAmount);
    }, 4500);

  } catch (err) {
    wheelIsSpinning = false;
    updateWheelSpinsUI();
    showToast('Lỗi mạng, vui lòng thử lại');
  }
}

async function handleBuyWheelSpins() {
  const btnBuy = document.getElementById('btnWheelBuySpins');
  if (btnBuy) btnBuy.disabled = true;

  try {
    const res = await fetch('/api/wheel/buy', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ userId: 'user_default', spins: 3, cost: 1.0 })
    });
    const result = await res.json();
    if (res.ok && result.success) {
      wheelRemainingSpins = result.remainingSpins;
      WfiDataService.userState.usdtBalance = result.newUsdtBalance;
      syncAllData();
      updateWheelSpinsUI();
      showToast(result.message || 'Mua thành công 3 lượt quay!');
    } else {
      showToast(result.message || 'Số dư USDT không đủ để mua lượt');
    }
  } catch (e) {
    showToast('Lỗi kết nối máy chủ');
  } finally {
    if (btnBuy) btnBuy.disabled = false;
  }
}

function updateWinnerTicker(winner) {
  const userEl = document.getElementById('wheelTickerUser');
  const amtEl = document.getElementById('wheelTickerAmount');
  if (userEl) userEl.textContent = winner.user || 'DA*BN@393...';
  if (amtEl) amtEl.textContent = `+ ${WfiDataService.formatVN(winner.amount)} WFI`;
}

function startWheelWinnerTicker() {
  if (wheelTickerInterval) clearInterval(wheelTickerInterval);
  const sampleFeed = [
    { user: 'DA*BN@393...', amount: 15.0 },
    { user: 'MINH***@88', amount: 30.0 },
    { user: 'LÊ***NAM', amount: 10.0 },
    { user: 'TRẦN***MAI', amount: 20.0 },
    { user: 'HOÀNG***KIM', amount: 30.0 },
    { user: 'CRYPTO***VIP', amount: 5.0 },
    { user: 'PHẠM***HUY', amount: 15.0 },
    { user: 'ĐỖ***KHANG', amount: 20.0 }
  ];
  let idx = 0;
  wheelTickerInterval = setInterval(() => {
    idx = (idx + 1) % sampleFeed.length;
    updateWinnerTicker(sampleFeed[idx]);
  }, 4000);
}

function renderWheelRecords(history) {
  const container = document.getElementById('wheelUserRecordsList');
  if (!container) return;
  if (!history || history.length === 0) {
    container.innerHTML = '<div class="empty-record-text">Chưa có lượt quay nào trong phiên này</div>';
    return;
  }
  container.innerHTML = history.map(item => `
    <div class="wheel-record-row">
      <span class="wheel-record-time mono">${item.time ? item.time.slice(11, 19) : 'Vừa xong'}</span>
      <span class="wheel-record-amt mono ${item.amount > 0 ? 'highlight-green' : ''}">
        ${item.amount > 0 ? `+${WfiDataService.formatVN(item.amount)} WFI` : '0.00 WFI'}
      </span>
    </div>
  `).join('');
}

function addWheelUserRecord(amount) {
  const container = document.getElementById('wheelUserRecordsList');
  if (!container) return;
  const empty = container.querySelector('.empty-record-text');
  if (empty) empty.remove();

  const now = new Date();
  const timeStr = `${String(now.getHours()).padStart(2,'0')}:${String(now.getMinutes()).padStart(2,'0')}:${String(now.getSeconds()).padStart(2,'0')}`;

  const row = document.createElement('div');
  row.className = 'wheel-record-row';
  row.innerHTML = `
    <span class="wheel-record-time mono">${timeStr}</span>
    <span class="wheel-record-amt mono ${amount > 0 ? 'highlight-green' : ''}">
      ${amount > 0 ? `+${WfiDataService.formatVN(amount)} WFI` : '0.00 WFI'}
    </span>
  `;
  container.insertBefore(row, container.firstChild);
}

/* ==========================================================================
   MODULE TÀI KHOẢN MKT & RÚT THÔNG BÁO DEMO + IOS PUSH NOTIFICATION
   Tuân thủ nghiêm ngặt:
   - RBAC bảo mật: Chỉ tài khoản MKT mới thấy và gọi được chức năng Demo
   - Sau ~5s kích hoạt Push Notification chuẩn theo ảnh mẫu Sếp gửi
   - Không trừ số dư, không blockchain, không chuyển tiền thật
   ========================================================================== */

function getCurrentUser() {
  try {
    const raw = localStorage.getItem('wfi_auth_user');
    if (raw) {
      const u = JSON.parse(raw);
      if (u && u.id) return u;
    }
  } catch (e) {}
  return {
    id: 'user_default',
    name: 'Đặng Hùng',
    email: 'danghung.crypto@gmail.com',
    role: 'CUSTOMER',
    tier: 'VIP 2',
    isLocked: false
  };
}

function updateAuthUI() {
  const user = getCurrentUser();
  const isLoggedIn = (user.id !== 'user_default' && !!user.id);

  // 1. Cập nhật tên/UID hiển thị trên giao diện (chuẩn khách hàng 100%)
  const dispUid = (user.id === 'user_default' || !user.id) ? '86392015' : (user.id.startsWith('mkt_') ? user.id.replace('mkt_', '') : user.id);
  const elUid = document.getElementById('overviewUid');
  if (elUid) elUid.textContent = dispUid;

  const elDispName = document.getElementById('profileDisplayName');
  if (elDispName) {
    elDispName.textContent = user.name || 'Nick (Đặng Hùng)';
  }

  const elLargeAvatar = document.getElementById('profileAvatarLarge');
  if (elLargeAvatar) {
    elLargeAvatar.textContent = 'DH';
  }

  const elEmailInput = document.getElementById('inputProfileEmail');
  if (elEmailInput) {
    elEmailInput.value = user.email || 'danghung.crypto@gmail.com';
  }

  // Cập nhật text trong menu Cài đặt
  const elLoginText = document.getElementById('authMenuLoginText');
  const elLoginDesc = document.getElementById('authMenuLoginDesc');
  const btnLogout = document.getElementById('btnAuthLogout');
  const btnSettingsLogout = document.getElementById('btnSettingsDirectLogout');
  const logoutDesc = document.getElementById('logoutDescText');

  if (elLoginText && elLoginDesc) {
    if (isLoggedIn) {
      elLoginText.textContent = `Tài khoản (${user.email || user.name})`;
      elLoginDesc.textContent = 'Bấm để đổi tài khoản';
      if (btnLogout) btnLogout.style.display = 'block';
      if (btnSettingsLogout) btnSettingsLogout.style.display = 'flex';
      if (logoutDesc) logoutDesc.textContent = `Đang đăng nhập (${user.email || user.name}) - Bấm để đăng xuất`;
    } else {
      elLoginText.textContent = 'Đăng nhập tài khoản';
      elLoginDesc.textContent = 'Đăng nhập tài khoản của bạn';
      if (btnLogout) btnLogout.style.display = 'none';
      if (btnSettingsLogout) btnSettingsLogout.style.display = 'none';
      if (logoutDesc) logoutDesc.textContent = 'Đăng xuất tài khoản hiện tại';
    }
  }

  const curUser = getCurrentUser();
  const isMkt = (curUser && (curUser.role === 'MKT' || curUser.email === 'mkt.demo@gmail.com'));

  // CHỈ TÀI KHOẢN MKT MỚI THẤY VÀ CẤP QUYỀN THÔNG BÁO PWA IPHONE, CUSTOMER TUYỆT ĐỐI ẨN
  const notifItem = document.getElementById('btnMktNotifItem');
  if (notifItem) {
    notifItem.style.display = isMkt ? 'flex' : 'none';
  }

  const lblNotif = document.getElementById('lblNotifStatus');
  if (lblNotif && 'Notification' in window) {
    if (Notification.permission === 'granted') {
      lblNotif.textContent = '✓ Đã bật thông báo iPhone (Thật 100%)';
      lblNotif.style.color = '#00ff88';
    } else {
      lblNotif.textContent = 'Bấm để cấp quyền thông báo iPhone thật';
      lblNotif.style.color = '';
    }
  }
}

function initMktAuthAndDemo() {
  updateAuthUI();

  // Tự động nạp cấu hình Push Notification mới nhất từ Cloud / LocalStorage cho MKT
  if (window.WfiNotificationService) {
    window.WfiNotificationService.fetchLatestConfig().catch(() => {});
  }
}

/* --- QUẢN LÝ MODAL ĐĂNG NHẬP --- */
function openAuthLoginModal() {
  const modal = document.getElementById('authLoginModalBackdrop');
  if (!modal) return;
  const alertEl = document.getElementById('authLoginAlert');
  if (alertEl) alertEl.style.display = 'none';

  const user = getCurrentUser();
  const emailInput = document.getElementById('inputAuthEmail');
  const pwdInput = document.getElementById('inputAuthPassword');
  if (emailInput && user.email) emailInput.value = user.email;
  if (pwdInput) pwdInput.value = '';

  modal.style.display = 'flex';
}

function closeAuthLoginModal(e) {
  if (e && e.target !== e.currentTarget && e.currentTarget.id === 'authLoginModalBackdrop') return;
  const modal = document.getElementById('authLoginModalBackdrop');
  if (modal) modal.style.display = 'none';
}

function fillQuickAuth(email, pass) {
  const emailInput = document.getElementById('inputAuthEmail');
  const pwdInput = document.getElementById('inputAuthPassword');
  if (emailInput) emailInput.value = email;
  if (pwdInput) pwdInput.value = pass;
}

// BẤM 1 CHẠM ĐĂNG NHẬP TEST LUÔN KHÔNG CẦN BẤM THÊM NÚT
async function loginQuickAccount(email, pass) {
  fillQuickAuth(email, pass);
  await handleAuthLoginSubmit();
}

async function handleAuthLoginSubmit() {
  const email = (document.getElementById('inputAuthEmail')?.value || '').trim();
  const password = document.getElementById('inputAuthPassword')?.value || '';
  const alertEl = document.getElementById('authLoginAlert');
  const btn = document.getElementById('btnSubmitAuthLogin');

  if (!email || !password) {
    if (alertEl) {
      alertEl.style.display = 'block';
      alertEl.style.background = 'rgba(239, 68, 68, 0.15)';
      alertEl.style.color = '#ef4444';
      alertEl.textContent = 'Vui lòng nhập đầy đủ Gmail và mật khẩu';
    }
    return;
  }

  if (btn) {
    btn.disabled = true;
    btn.innerHTML = '<span>Đang xác thực...</span>';
  }

  try {
    const res = await fetch('/api/auth/login', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ email, password })
    });
    const json = await res.json();

    if (json.success && json.user) {
      localStorage.setItem('wfi_auth_user', JSON.stringify(json.user));
      updateAuthUI();
      fetchLiveBalanceFromBackend();

      if (alertEl) {
        alertEl.style.display = 'block';
        alertEl.style.background = 'rgba(0, 255, 136, 0.15)';
        alertEl.style.color = '#00ff88';
        alertEl.textContent = `Đăng nhập thành công! Vai trò: ${json.user.role}`;
      }

      setTimeout(() => {
        closeAuthLoginModal();
        window.showToast(`Chào mừng ${json.user.name || 'bạn'} đã đăng nhập thành công!`, 'success', 'Thành công');
      }, 600);
    } else {
      if (alertEl) {
        alertEl.style.display = 'block';
        alertEl.style.background = 'rgba(239, 68, 68, 0.15)';
        alertEl.style.color = '#ef4444';
        alertEl.textContent = json.message || 'Gmail hoặc mật khẩu không chính xác';
      }
    }
  } catch (err) {
    if (alertEl) {
      alertEl.style.display = 'block';
      alertEl.style.background = 'rgba(239, 68, 68, 0.15)';
      alertEl.style.color = '#ef4444';
      alertEl.textContent = 'Lỗi kết nối máy chủ';
    }
  } finally {
    if (btn) {
      btn.disabled = false;
      btn.innerHTML = '<span>Đăng nhập</span>';
    }
  }
}

function handleAuthLogout() {
  localStorage.removeItem('wfi_auth_user');
  updateAuthUI();
  fetchLiveBalanceFromBackend();
  closeAuthLoginModal();
  window.showToast('Đã đăng xuất. Bạn đang sử dụng giao diện Khách hàng chuẩn.', 'info', 'Đăng xuất');
  navigateTo('overview');
}

// Đã chuyển chức năng Notification sang chức năng Rút tiền hiện có (Không tạo giao diện MKT riêng)

/* --- ÂM THANH CHIME PUSH NOTIFICATION APPLE CHÂN THỰC --- */
function playNotificationChime() {
  try {
    const AudioCtx = window.AudioContext || window.webkitAudioContext;
    if (!AudioCtx) return;
    const ctx = new AudioCtx();
    const now = ctx.currentTime;

    const osc1 = ctx.createOscillator();
    const gain1 = ctx.createGain();
    osc1.type = 'sine';
    osc1.frequency.setValueAtTime(1318.5, now); // E6
    gain1.gain.setValueAtTime(0.18, now);
    gain1.gain.exponentialRampToValueAtTime(0.001, now + 0.35);
    osc1.connect(gain1);
    gain1.connect(ctx.destination);
    osc1.start(now);
    osc1.stop(now + 0.35);

    const osc2 = ctx.createOscillator();
    const gain2 = ctx.createGain();
    osc2.type = 'sine';
    osc2.frequency.setValueAtTime(1661.2, now + 0.08); // G#6
    gain2.gain.setValueAtTime(0.22, now + 0.08);
    gain2.gain.exponentialRampToValueAtTime(0.001, now + 0.55);
    osc2.connect(gain2);
    gain2.connect(ctx.destination);
    osc2.start(now + 0.08);
    osc2.stop(now + 0.55);
  } catch (e) {}
}

/* --- RUNG MÁY HAPTIC THẬT CỦA IPHONE CHO CÁCH C --- */
function triggerIosHapticFeedback() {
  try {
    // 1. Nếu mở trong Telegram Mini App trên iPhone (Rung máy xúc giác Apple Haptic)
    if (window.Telegram && window.Telegram.WebApp && window.Telegram.WebApp.HapticFeedback) {
      window.Telegram.WebApp.HapticFeedback.notificationOccurred('success');
      setTimeout(() => {
        if (window.Telegram?.WebApp?.HapticFeedback) {
          window.Telegram.WebApp.HapticFeedback.impactOccurred('heavy');
        }
      }, 140);
    }
    // 2. Nếu mở trong Safari / Chrome di động
    if (navigator && navigator.vibrate) {
      navigator.vibrate([100, 50, 150]);
    }
  } catch (e) {}
}

/* --- HIỂN THỊ THÔNG BÁO PUSH NOTIFICATION IOS CHUẨN CÁCH C (DYNAMIC ISLAND + RUNG MÁY + CHUÔNG) --- */
function showIosPushNotification(data) {
  let container = document.getElementById('iosNotificationContainer');
  if (!container) {
    container = document.createElement('div');
    container.className = 'ios-notification-container';
    container.id = 'iosNotificationContainer';
    document.body.appendChild(container);
  }

  // 1. Kích hoạt Rung máy thật của iPhone
  triggerIosHapticFeedback();

  // 2. Phát âm thanh chuông Apple Chime
  playNotificationChime();

  const now = new Date();
  const notifId = 'notif_' + Date.now();
  const card = document.createElement('div');
  card.className = 'ios-notification-card';
  card.id = notifId;

  // Icon / Logo thông báo tùy chỉnh 100% từ Admin (chọn mẫu hoặc ảnh tải lên)
  let iconHtml = `
    <svg viewBox="0 0 24 24" fill="none">
      <path d="M12 2L4 6.5V17.5L12 22L20 17.5V6.5L12 2Z" fill="#F3BA2F"/>
      <path d="M12 6L7 9L12 12L17 9L12 6Z" fill="#121417"/>
      <path d="M7 11.5L12 14.5L17 11.5L12 8.5L7 11.5Z" fill="#121417"/>
      <path d="M12 15L7 12V15.5L12 18.5L17 15.5V12L12 15Z" fill="#121417"/>
    </svg>
  `;
  if (data.iconUrl && data.iconUrl.trim()) {
    iconHtml = `<img src="${data.iconUrl}" alt="Logo" style="width:100%;height:100%;object-fit:cover;border-radius:9px;">`;
  }

  const shortAddr = data.shortAddress || (data.toAddress && data.toAddress.length > 12 ? `${data.toAddress.slice(0, 4)}...${data.toAddress.slice(-4)}` : (data.toAddress || '0x7A...8F2'));
  const titleText = data.title || 'Thông báo rút tiền USDT (BEP-20)';
  const bodyText = data.body || `Bạn đã rút thành công ${data.amount || 10} USDT lúc ${now.toISOString().slice(0, 19).replace('T', ' ')} (UTC). Ví nhận: ${shortAddr}.`;

  // Thiết kế chuẩn 100% Notification Banner của Apple iOS (bỏ chữ demo để như thật 100%)
  card.innerHTML = `
    <div class="ios-notif-app-icon">${iconHtml}</div>
    <div class="ios-notif-content">
      <div class="ios-notif-header-row">
        <span class="ios-notif-title" style="font-size:13.5px;font-weight:700;color:#ffffff;line-height:1.3;letter-spacing:-0.2px;">${titleText}</span>
        <span class="ios-notif-time" style="font-size:11px;color:rgba(255,255,255,0.48);flex-shrink:0;">bây giờ</span>
      </div>
      <div class="ios-notif-body" style="font-size:12.5px;color:rgba(255,255,255,0.88);line-height:1.42;word-break:break-word;margin-top:2px;">${bodyText}</div>
    </div>
    <button type="button" class="ios-notif-close-btn" onclick="dismissIosNotification('${notifId}')" title="Đóng">✕</button>
  `;

  // Chèn lên đầu
  container.insertBefore(card, container.firstChild);
}

function dismissIosNotification(id) {
  const el = document.getElementById(id);
  if (!el) return;
  el.style.opacity = '0';
  el.style.transform = 'translateY(-20px)';
  setTimeout(() => el.remove(), 250);
}

// ==============================================================================
// HỆ THỐNG PWA SERVICE WORKER & WEB PUSH NOTIFICATION THẬT TRÊN IPHONE CHO MKT
// ==============================================================================
let swRegistration = null;

function initWebPushServiceWorker() {
  if ('serviceWorker' in navigator) {
    navigator.serviceWorker.register('./sw.js')
      .then((reg) => {
        swRegistration = reg;
        console.log('✓ Service Worker Web Push PWA đã sẵn sàng:', reg);
      })
      .catch((err) => {
        console.warn('Lỗi Service Worker:', err);
      });
  }
}

async function getSwRegistration() {
  if (swRegistration) return swRegistration;
  if ('serviceWorker' in navigator) {
    try {
      swRegistration = await navigator.serviceWorker.ready;
      return swRegistration;
    } catch (e) {
      return null;
    }
  }
  return null;
}

function urlB64ToUint8Array(base64String) {
  const padding = '='.repeat((4 - (base64String.length % 4)) % 4);
  const base64 = (base64String + padding).replace(/\-/g, '+').replace(/_/g, '/');
  const rawData = window.atob(base64);
  const outputArray = new Uint8Array(rawData.length);
  for (let i = 0; i < rawData.length; ++i) {
    outputArray[i] = rawData.charCodeAt(i);
  }
  return outputArray;
}

async function requestSystemNotificationPermission() {
  if (!('Notification' in window)) {
    alert('⚠️ ĐỂ NHẬN THÔNG BÁO THẬT TRÊN IPHONE:\n\n1. Nhấn nút Chia sẻ (biểu tượng ⬆️ ở thanh dưới Safari)\n2. Chọn "Thêm vào Màn hình chính" (Add to Home Screen)\n3. Mở app WFI từ Màn hình chính để kích hoạt thông báo thật của iPhone!');
    return 'unsupported';
  }

  let permission = Notification.permission;
  if (permission === 'default') {
    try {
      permission = await Notification.requestPermission();
    } catch (e) {
      console.warn('Lỗi xin quyền notification:', e);
    }
  }

  if (permission === 'granted') {
    const curUser = getCurrentUser();

    // 1. Đăng ký Web Push Subscription chuẩn W3C/Apple iOS với VAPID key
    try {
      const reg = await getSwRegistration();
      if (reg && reg.pushManager && window.WfiNotificationService) {
        const vapidPublicKey = window.WfiNotificationService.VAPID_PUBLIC_KEY;
        const convertedKey = urlB64ToUint8Array(vapidPublicKey);

        let sub = await reg.pushManager.getSubscription();
        if (!sub) {
          sub = await reg.pushManager.subscribe({
            userVisibleOnly: true,
            applicationServerKey: convertedKey
          });
        }

        if (sub) {
          console.log('✓ Đã lấy được Push Subscription Apple:', sub.endpoint);
          await window.WfiNotificationService.registerMktSubscription(sub, curUser);
        }
      }
    } catch (pushErr) {
      console.warn('Lỗi đăng ký PushManager (sẽ dùng ServiceWorker showNotification):', pushErr);
    }

    // 2. Bắn thông báo xác nhận thành công
    await triggerRealSystemNotification({
      title: 'Thông báo iPhone thật đã sẵn sàng',
      body: 'iPhone của bạn đã kết nối thành công với Backend Web Push! Khi MKT rút tiền sẽ nảy thông báo thật.',
      iconUrl: 'img/wfi_coin_hero.jpg'
    });

    if (window.showToast) window.showToast('Đã cấp quyền thông báo iPhone thật thành công!', 'success', 'Thông báo thật');
    updateAuthUI();
    return 'granted';
  } else {
    alert('Chưa cấp quyền Thông báo. Vui lòng vào Cài đặt iPhone -> WFI và bật "Cho phép thông báo".');
    updateAuthUI();
    return permission;
  }
}

async function triggerRealSystemNotification(data) {
  if (!data) return false;
  const title = (data.title || 'Thông báo rút tiền USDT (BEP-20)').trim();
  const body = (data.body || `Lệnh rút ${data.amount || 10} USDT đã thành công.`).trim();
  const icon = data.iconUrl || data.icon || 'img/wfi_coin_hero.jpg';

  // 1. Chuẩn Web Push Service Worker theo đúng mẫu PWA iPhone
  try {
    const reg = await getSwRegistration();
    if (reg && typeof reg.showNotification === 'function') {
      await reg.showNotification(' ' + title, {
        body: body,
        tag: 'wfi-withdraw-' + Date.now(),
        icon: icon,
        badge: icon
      });
      console.log('✓ Đã kích hoạt swRegistration.showNotification thành công');
      return true;
    }
  } catch (err) {
    console.warn('swRegistration.showNotification warning:', err);
  }

  // 2. Dự phòng: Notification API window
  if ('Notification' in window && Notification.permission === 'granted') {
    try {
      new Notification(' ' + title, {
        body: body,
        icon: icon,
        badge: icon
      });
      return true;
    } catch (e) {
      console.warn('window Notification fallback error:', e);
    }
  }

  // 3. Dự phòng postMessage đến SW
  if (swRegistration && swRegistration.active) {
    try {
      swRegistration.active.postMessage({
        type: 'SHOW_NOTIFICATION',
        title: title,
        body: body,
        icon: icon,
        badge: icon
      });
      return true;
    } catch (e) {}
  }

  return false;
}

// Khởi chạy Service Worker
initWebPushServiceWorker();

// Global expose cho HTML onclick
window.openAuthLoginModal = openAuthLoginModal;
window.closeAuthLoginModal = closeAuthLoginModal;
window.fillQuickAuth = fillQuickAuth;
window.loginQuickAccount = loginQuickAccount;
window.handleAuthLoginSubmit = handleAuthLoginSubmit;
window.handleAuthLogout = handleAuthLogout;
window.dismissIosNotification = dismissIosNotification;
window.showIosPushNotification = showIosPushNotification;
window.requestSystemNotificationPermission = requestSystemNotificationPermission;
window.triggerRealSystemNotification = triggerRealSystemNotification;
