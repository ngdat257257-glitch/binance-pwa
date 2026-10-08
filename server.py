#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
WFI Mining - Backend Server & Blockchain Service
Hệ thống hoàn chỉnh phục vụ:
1. Client App & iPhone Mockup
2. Form 1: Nạp USDT BEP20 tự động xác thực trên BSC
3. Form 2: Rút USDT BEP20 có Admin duyệt & ký giao dịch on-chain
4. Toàn bộ 11 chức năng Cổng Quản trị Admin WFI:
   - Dashboard tổng quan (KPIs & biểu đồ doanh thu)
   - Quản lý khách hàng (Xem chi tiết, khóa/mở khóa)
   - Quản lý gói đào (Giá, doanh thu, gói đang chạy)
   - Quản lý nạp tiền BEP20
   - Quản lý rút tiền BEP20 (Duyệt/Từ chối on-chain)
   - WFI Tokenomics
   - Nhật ký toàn bộ giao dịch (Nạp/Rút/Gói/Đổi)
   - Báo cáo doanh thu (Ngày/Tháng/Tổng)
   - Quản lý yêu cầu hỗ trợ (Tickets)
   - Cấu hình hệ thống (Ví, tỷ giá, phí, giá gói)
   - Tài khoản Admin, phân quyền & Nhật ký Audit Logs
"""

import http.server
import socketserver
import json
import sqlite3
import os
import re
import time
import datetime
import threading
import urllib.request
import urllib.error
import ssl
import hashlib
import mimetypes

# Đăng ký MIME type chuẩn cho PWA Web Manifest
mimetypes.add_type("application/manifest+json", ".webmanifest")

import secrets

from eth_account import Account

# ==============================================================================
# HÀM BẢO MẬT & MÃ HÓA MẬT KHẨU (PBKDF2-HMAC-SHA256 VỚI SALT NGẪU NHIÊN)
# ==============================================================================
def hash_password(password: str, salt: str = None) -> tuple:
    """Mã hóa mật khẩu bằng PBKDF2-HMAC-SHA256 với 100,000 vòng lặp, KHÔNG LƯU PLAINTEXT"""
    if not salt:
        salt = secrets.token_hex(16)
    pwd_bytes = password.encode("utf-8")
    salt_bytes = salt.encode("utf-8")
    pwd_hash = hashlib.pbkdf2_hmac("sha256", pwd_bytes, salt_bytes, 100000).hex()
    return pwd_hash, salt

def verify_password(password: str, pwd_hash: str, salt: str) -> bool:
    """Kiểm tra mật khẩu khớp với hash đã lưu an toàn"""
    if not password or not pwd_hash or not salt:
        return False
    calc_hash, _ = hash_password(password, salt)
    return secrets.compare_digest(calc_hash, pwd_hash)

# ==============================================================================
# ĐỌC CẤU HÌNH BẢO MẬT TỪ ENVIRONMENT / SECRET (.env)
# ==============================================================================
ENV_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), ".env")
def load_env_variables():
    if os.path.exists(ENV_FILE):
        try:
            with open(ENV_FILE, "r", encoding="utf-8") as f:
                for line in f:
                    line = line.strip()
                    if line and not line.startswith("#") and "=" in line:
                        k, v = line.split("=", 1)
                        k, v = k.strip(), v.strip()
                        if k not in os.environ:
                            os.environ[k] = v
        except Exception as e:
            print("[WARN] Không thể đọc file .env:", e)

load_env_variables()

ADMIN_WALLET_ADDRESS = os.environ.get("ADMIN_WALLET_ADDRESS", "0xcb3Fc21Af451e1D51Cd58078F025Dad92595f5BA")
# Private Key chỉ lưu nội bộ backend, KHÔNG BAO GIỜ gửi ra ngoài!
ADMIN_PRIVATE_KEY = os.environ.get("ADMIN_PRIVATE_KEY", "7ef0b7d216a496c74a324a7498dad79fb6b2ad4cdee4d3be458b4ba206dbaa07")

BSC_USDT_CONTRACT = os.environ.get("USDT_CONTRACT_ADDRESS", "0x55d398326f99059fF775485246999027B3197955")
BSC_CHAIN_ID = int(os.environ.get("BSC_CHAIN_ID", 56))
NETWORK_NAME = "BNB Smart Chain (BEP20)"
TRANSFER_EVENT_TOPIC = "0xddf252ad1be2c89b69c2b068fc378daa952ba7f163c4a11628f55a4df523b3ef"

WITHDRAW_FEE_USDT = float(os.environ.get("WITHDRAW_FEE_USDT", 1.0))
MIN_WITHDRAW_USDT = float(os.environ.get("MIN_WITHDRAW_USDT", 5.0))

blockchain_tx_lock = threading.Lock()

BSC_RPC_ENDPOINTS = [
    "https://bsc-dataseed.binance.org/",
    "https://bsc.publicnode.com",
    "https://binance.llamarpc.com",
    "https://1rpc.io/bnb"
]

PORT = 3000
DB_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "wfi_database.db")


# ==============================================================================
# KHỞI TẠO CƠ SỞ DỮ LIỆU SQLITE HOÀN CHỈNH CHO 11 CHỨC NĂNG ADMIN
# ==============================================================================
def init_database():
    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()

    # 1. Bảng Khách hàng
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS users (
        id TEXT PRIMARY KEY,
        name TEXT NOT NULL,
        email TEXT NOT NULL,
        phone TEXT,
        tier TEXT DEFAULT 'VIP 2',
        usdt_balance REAL DEFAULT 85.50,
        locked_usdt REAL DEFAULT 0.0,
        wfi_balance REAL DEFAULT 12580.35,
        is_locked INTEGER DEFAULT 0,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    );
    """)

    cursor.execute("PRAGMA table_info(users)")
    cols = [c[1] for c in cursor.fetchall()]
    if "locked_usdt" not in cols:
        cursor.execute("ALTER TABLE users ADD COLUMN locked_usdt REAL DEFAULT 0.0")
    if "is_locked" not in cols:
        cursor.execute("ALTER TABLE users ADD COLUMN is_locked INTEGER DEFAULT 0")
    if "sales_volume" not in cols:
        cursor.execute("ALTER TABLE users ADD COLUMN sales_volume REAL DEFAULT 0.0")
    if "commission_level" not in cols:
        cursor.execute("ALTER TABLE users ADD COLUMN commission_level INTEGER DEFAULT 0")
    if "commission_rate" not in cols:
        cursor.execute("ALTER TABLE users ADD COLUMN commission_rate REAL DEFAULT 0.0")
    if "referrer_id" not in cols:
        cursor.execute("ALTER TABLE users ADD COLUMN referrer_id TEXT DEFAULT NULL")
    if "weekly_wfi_mined" not in cols:
        cursor.execute("ALTER TABLE users ADD COLUMN weekly_wfi_mined REAL DEFAULT 0.0")
    if "total_wfi_mined" not in cols:
        cursor.execute("ALTER TABLE users ADD COLUMN total_wfi_mined REAL DEFAULT 0.0")
    # Chu kỳ Claim 24 giờ: mốc bắt đầu chu kỳ hiện tại & số WFI Claim gần nhất
    if "last_claim_at" not in cols:
        cursor.execute("ALTER TABLE users ADD COLUMN last_claim_at INTEGER DEFAULT NULL")
    if "last_claim_amount" not in cols:
        cursor.execute("ALTER TABLE users ADD COLUMN last_claim_amount REAL DEFAULT 0.0")
    if "role" not in cols:
        cursor.execute("ALTER TABLE users ADD COLUMN role TEXT DEFAULT 'CUSTOMER'")
    if "password_hash" not in cols:
        cursor.execute("ALTER TABLE users ADD COLUMN password_hash TEXT DEFAULT NULL")
    if "salt" not in cols:
        cursor.execute("ALTER TABLE users ADD COLUMN salt TEXT DEFAULT NULL")
    if "device_token" not in cols:
        cursor.execute("ALTER TABLE users ADD COLUMN device_token TEXT DEFAULT 'WFI_IPHONE_DEMO'")

    # Bảng Lịch sử Rút thông báo Demo dành riêng cho MKT (Tách biệt hoàn toàn với bảng withdrawals thật)
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS mkt_demo_notifications (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        user_id TEXT NOT NULL,
        email TEXT NOT NULL,
        amount REAL NOT NULL,
        to_address TEXT NOT NULL,
        title TEXT NOT NULL,
        body TEXT NOT NULL,
        status TEXT NOT NULL DEFAULT 'PENDING', -- 'PENDING', 'DELIVERED'
        category TEXT NOT NULL DEFAULT 'MKT_DEMO',
        virtual_flag TEXT NOT NULL DEFAULT 'VIRTUAL_NOTIFICATION',
        scheduled_at INTEGER NOT NULL,
        delivered_at INTEGER NOT NULL,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        FOREIGN KEY (user_id) REFERENCES users(id)
    );
    """)

    # Bảng Cấu hình Tiêu đề, Nội dung & Logo Push Notification cho MKT (Admin tùy chỉnh 100%, không hard-code)
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS mkt_notification_config (
        id INTEGER PRIMARY KEY DEFAULT 1,
        title TEXT NOT NULL,
        body_template TEXT NOT NULL,
        delay_seconds INTEGER NOT NULL DEFAULT 5,
        icon_url TEXT DEFAULT '',
        updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    );
    """)
    try:
        cursor.execute("ALTER TABLE mkt_notification_config ADD COLUMN icon_url TEXT DEFAULT ''")
    except Exception:
        pass
    cursor.execute("SELECT id FROM mkt_notification_config WHERE id = 1")
    if not cursor.fetchone():
        cursor.execute("""
        INSERT INTO mkt_notification_config (id, title, body_template, delay_seconds, icon_url)
        VALUES (1, 'Thông báo rút tiền USDT (BEP-20)', 'Lệnh rút {amount} USDT về ví {short_address} đã được xác nhận thành công trên mạng BSC.', 5, '')
        """)

    # Bảng Lịch sử Bảng Xếp Hạng Tuần & Trao Thưởng Top 3
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS weekly_leaderboard_history (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        week_number INTEGER NOT NULL,
        start_date TEXT NOT NULL,
        end_date TEXT NOT NULL,
        rank1_user_id TEXT,
        rank1_user_name TEXT,
        rank1_wfi REAL DEFAULT 0.0,
        rank1_reward REAL DEFAULT 1000.0,
        rank2_user_id TEXT,
        rank2_user_name TEXT,
        rank2_wfi REAL DEFAULT 0.0,
        rank2_reward REAL DEFAULT 500.0,
        rank3_user_id TEXT,
        rank3_user_name TEXT,
        rank3_wfi REAL DEFAULT 0.0,
        rank3_reward REAL DEFAULT 250.0,
        total_participants INTEGER DEFAULT 0,
        status TEXT DEFAULT 'SETTLED',
        settled_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    );
    """)

    # Bảng Lịch sử Nâng/Hạ Cấp Hoa Hồng Tự Động
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS commission_tier_history (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        user_id TEXT NOT NULL,
        user_name TEXT NOT NULL,
        old_level INTEGER NOT NULL,
        new_level INTEGER NOT NULL,
        old_rate REAL NOT NULL,
        new_rate REAL NOT NULL,
        trigger_sales REAL NOT NULL,
        reason TEXT NOT NULL,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        FOREIGN KEY(user_id) REFERENCES users(id)
    );
    """)

    # Bảng Lịch sử chi trả hoa hồng
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS commissions (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        user_id TEXT NOT NULL,
        user_name TEXT NOT NULL,
        from_user_id TEXT NOT NULL,
        from_user_name TEXT NOT NULL,
        package_id INTEGER,
        package_amount REAL NOT NULL,
        commission_rate REAL NOT NULL,
        commission_amount REAL NOT NULL,
        status TEXT DEFAULT 'PAID',
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    );
    """)

    # Bảng Lịch sử Vòng quay may mắn (Lucky Draw)
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS lucky_draws (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        user_id TEXT NOT NULL,
        user_name TEXT NOT NULL,
        reward_amount REAL NOT NULL,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    );
    """)

    # Thêm cột lucky_spins vào users nếu chưa có
    try:
        cursor.execute("ALTER TABLE users ADD COLUMN lucky_spins INTEGER DEFAULT 3")
    except Exception:
        pass

    # Người dùng mặc định
    cursor.execute("SELECT COUNT(id) FROM users")
    if cursor.fetchone()[0] == 0:
        sample_users = [
            ('user_default', 'Đặng Hùng', 'danghung.crypto@gmail.com', '0988 123 456', 'VIP 2', 85.50, 0.0, 12580.35, 0, 1200.0, 1, 0.10, None),
            ('user_102', 'Nguyễn Minh Trí', 'minhtri.crypto@gmail.com', '0912 345 678', 'VIP 3', 350.00, 0.0, 42000.0, 0, 7500.0, 3, 0.14, 'user_default'),
            ('user_103', 'Lê Hoàng Nam', 'hoangnam.bsc@gmail.com', '0977 888 999', 'VIP 1', 45.00, 0.0, 6800.0, 0, 450.0, 0, 0.0, 'user_default'),
            ('user_104', 'Trần Thị Mai', 'maitran.invest@gmail.com', '0903 111 222', 'VIP 2', 120.00, 0.0, 18500.0, 0, 3500.0, 2, 0.12, 'user_102'),
            ('user_105', 'Phạm Quốc Huy', 'quochuy.mining@gmail.com', '0938 444 555', 'VIP 1', 12.50, 0.0, 3100.0, 0, 13000.0, 4, 0.17, 'user_102'),
            ('user_vip', 'Hoàng Kim VIP', 'hoangkim.invest@gmail.com', '0969 888 777', 'VIP 5', 520.00, 0.0, 85000.0, 0, 22000.0, 5, 0.20, None)
        ]
        cursor.executemany("""
            INSERT INTO users (id, name, email, phone, tier, usdt_balance, locked_usdt, wfi_balance, is_locked, sales_volume, commission_level, commission_rate, referrer_id)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, sample_users)

    # Đảm bảo dữ liệu mẫu ban đầu về doanh số và cấp bậc được đồng bộ
    cursor.execute("UPDATE users SET sales_volume = 1200.0, commission_level = 1, commission_rate = 0.10 WHERE id = 'user_default' AND (sales_volume IS NULL OR sales_volume = 0)")
    cursor.execute("UPDATE users SET sales_volume = 7500.0, commission_level = 3, commission_rate = 0.14 WHERE id = 'user_102' AND (sales_volume IS NULL OR sales_volume = 0)")
    cursor.execute("UPDATE users SET sales_volume = 450.0, commission_level = 0, commission_rate = 0.0 WHERE id = 'user_103' AND (sales_volume IS NULL OR sales_volume = 0)")
    cursor.execute("UPDATE users SET sales_volume = 3500.0, commission_level = 2, commission_rate = 0.12 WHERE id = 'user_104' AND (sales_volume IS NULL OR sales_volume = 0)")
    cursor.execute("UPDATE users SET sales_volume = 13000.0, commission_level = 4, commission_rate = 0.17 WHERE id = 'user_105' AND (sales_volume IS NULL OR sales_volume = 0)")
    cursor.execute("INSERT OR IGNORE INTO users (id, name, email, phone, tier, usdt_balance, locked_usdt, wfi_balance, is_locked, sales_volume, commission_level, commission_rate, referrer_id) VALUES ('user_vip', 'Hoàng Kim VIP', 'hoangkim.invest@gmail.com', '0969 888 777', 'VIP 5', 520.0, 0.0, 85000.0, 0, 22000.0, 5, 0.20, NULL)")

    # Bổ sung các thợ đào thành viên để bảng xếp hạng có đầy đủ Top 10 dữ liệu thực tế
    extra_sample_users = [
        ('user_106', 'Vũ Đình Cường', 'dinhcuong.crypto@gmail.com', '0931 222 333', 'VIP 2', 65.0, 0.0, 5200.0, 0, 800.0, 0, 0.0, None),
        ('user_107', 'Ngô Bích Thảo', 'bichthao.bsc@gmail.com', '0945 666 777', 'VIP 1', 30.0, 0.0, 3600.0, 0, 600.0, 0, 0.0, None),
        ('user_108', 'Bùi Tuấn Anh', 'tuananh.invest@gmail.com', '0978 112 233', 'VIP 1', 15.0, 0.0, 2400.0, 0, 500.0, 0, 0.0, None),
        ('user_109', 'Đỗ Minh Khang', 'minhkhang.mining@gmail.com', '0919 887 766', 'VIP 1', 20.0, 0.0, 1800.0, 0, 300.0, 0, 0.0, None),
        ('user_110', 'Hồ Tuyết Lan', 'tuyetlan.bsc@gmail.com', '0982 334 455', 'VIP 1', 10.0, 0.0, 1200.0, 0, 200.0, 0, 0.0, None),
        ('user_111', 'Trịnh Bá Hưng', 'bahung.crypto@gmail.com', '0933 555 666', 'VIP 1', 25.0, 0.0, 950.0, 0, 150.0, 0, 0.0, None)
    ]
    for eu in extra_sample_users:
        cursor.execute("INSERT OR IGNORE INTO users (id, name, email, phone, tier, usdt_balance, locked_usdt, wfi_balance, is_locked, sales_volume, commission_level, commission_rate, referrer_id) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)", eu)

    # Khởi tạo hash mật khẩu bảo mật cho tài khoản khách hàng mặc định (Mật khẩu: 123456)
    def_hash, def_salt = hash_password("123456")
    cursor.execute("""
        UPDATE users SET password_hash = ?, salt = ?, role = 'CUSTOMER'
        WHERE id = 'user_default' AND (password_hash IS NULL OR password_hash = '')
    """, (def_hash, def_salt))

    # Khởi tạo tài khoản MKT Demo mặc định (Email: mkt.demo@gmail.com | Mật khẩu: mkt123456)
    cursor.execute("SELECT id FROM users WHERE email = 'mkt.demo@gmail.com'")
    if not cursor.fetchone():
        mkt_hash, mkt_salt = hash_password("mkt123456")
        cursor.execute("""
            INSERT INTO users (id, name, email, phone, tier, usdt_balance, locked_usdt, wfi_balance, is_locked, sales_volume, commission_level, commission_rate, role, password_hash, salt)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, ('mkt_88001122', 'MKT Partner (Demo)', 'mkt.demo@gmail.com', '0999 888 777', 'VIP MKT', 0.0, 0.0, 0.0, 0, 0.0, 0, 0.0, 'MKT', mkt_hash, mkt_salt))

    # Dữ liệu mẫu lịch sử trúng thưởng Vòng quay may mắn
    cursor.execute("SELECT COUNT(id) FROM lucky_draws")
    if cursor.fetchone()[0] == 0:
        sample_draws = [
            ('user_102', 'DA*BN@393...', 15.0, '2026-10-07 22:45:10'),
            ('user_103', 'MINH***@88', 30.0, '2026-10-07 22:30:05'),
            ('user_104', 'LÊ***NAM', 10.0, '2026-10-07 21:55:12'),
            ('user_105', 'TRẦN***MAI', 20.0, '2026-10-07 21:20:44'),
            ('user_106', 'CRYPTO***VIP', 5.0, '2026-10-07 20:40:19'),
            ('user_vip', 'HOÀNG***KIM', 30.0, '2026-10-07 19:15:33')
        ]
        cursor.executemany("INSERT INTO lucky_draws (user_id, user_name, reward_amount, created_at) VALUES (?, ?, ?, ?)", sample_draws)

    # 2. Bảng Nạp tiền (Form 1 - TXID UNIQUE)
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS deposits (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        user_id TEXT NOT NULL,
        user_name TEXT NOT NULL,
        txid TEXT UNIQUE NOT NULL,
        network TEXT DEFAULT 'BEP20',
        token_symbol TEXT DEFAULT 'USDT',
        token_contract TEXT NOT NULL,
        from_address TEXT,
        to_address TEXT NOT NULL,
        amount REAL NOT NULL,
        block_number INTEGER,
        confirmations INTEGER DEFAULT 1,
        status TEXT NOT NULL,
        error_reason TEXT,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        FOREIGN KEY(user_id) REFERENCES users(id)
    );
    """)

    # 3. Bảng Rút tiền (Form 2)
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS withdrawals (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        user_id TEXT NOT NULL,
        user_name TEXT NOT NULL,
        amount REAL NOT NULL,
        fee REAL NOT NULL DEFAULT 1.0,
        net_amount REAL NOT NULL,
        to_address TEXT NOT NULL,
        txid TEXT,
        block_number INTEGER,
        status TEXT NOT NULL,
        reject_reason TEXT,
        admin_approver TEXT,
        approved_at TIMESTAMP,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        FOREIGN KEY(user_id) REFERENCES users(id)
    );
    """)

    # 4. Bảng Gói đào
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS packages (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        user_id TEXT NOT NULL,
        user_name TEXT NOT NULL,
        package_name TEXT NOT NULL,
        price REAL NOT NULL DEFAULT 10.0,
        quantity INTEGER NOT NULL DEFAULT 1,
        daily_yield REAL NOT NULL DEFAULT 15.0,
        status TEXT NOT NULL DEFAULT 'ACTIVE',
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    );
    """)

    cursor.execute("SELECT COUNT(id) FROM packages")
    if cursor.fetchone()[0] == 0:
        sample_pkgs = [
            ('user_default', 'Đặng Hùng', 'Gói đào WFI', 10.0, 15, 225.0, 'ACTIVE'),
            ('user_102', 'Nguyễn Minh Trí', 'Gói đào WFI', 10.0, 30, 450.0, 'ACTIVE'),
            ('user_103', 'Lê Hoàng Nam', 'Gói đào WFI', 10.0, 5, 75.0, 'ACTIVE'),
            ('user_104', 'Trần Thị Mai', 'Gói đào WFI', 10.0, 12, 180.0, 'ACTIVE')
        ]
        cursor.executemany("""
            INSERT INTO packages (user_id, user_name, package_name, price, quantity, daily_yield, status)
            VALUES (?, ?, ?, ?, ?, ?, ?)
        """, sample_pkgs)

    # 5. Bảng Toàn bộ Giao dịch (Ledger)
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS transactions (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        user_id TEXT NOT NULL,
        user_name TEXT NOT NULL,
        type TEXT NOT NULL, -- 'DEPOSIT', 'WITHDRAW', 'BUY_PACKAGE', 'SWAP'
        amount REAL NOT NULL,
        token TEXT NOT NULL,
        fee REAL DEFAULT 0,
        status TEXT NOT NULL DEFAULT 'COMPLETED',
        txid TEXT,
        note TEXT,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    );
    """)

    cursor.execute("SELECT COUNT(id) FROM transactions")
    if cursor.fetchone()[0] == 0:
        sample_txs = [
            ('user_default', 'Đặng Hùng', 'BUY_PACKAGE', 150.0, 'USDT', 0.0, 'COMPLETED', None, 'Mua 15 gói đào WFI'),
            ('user_102', 'Nguyễn Minh Trí', 'DEPOSIT', 500.0, 'USDT', 0.0, 'COMPLETED', '0x9a8b7c6d5e4f3a2b1c0d9e8f7a6b5c4d3e2f1a0b9c8d7e6f5a4b3c2d1e0f9a8b', 'Nạp USDT BEP20 qua blockchain'),
            ('user_102', 'Nguyễn Minh Trí', 'BUY_PACKAGE', 300.0, 'USDT', 0.0, 'COMPLETED', None, 'Mua 30 gói đào WFI'),
            ('user_default', 'Đặng Hùng', 'SWAP', 1000.0, 'WFI', 0.0, 'COMPLETED', None, 'Đổi 1000 WFI sang 10 USDT'),
            ('user_104', 'Trần Thị Mai', 'DEPOSIT', 200.0, 'USDT', 0.0, 'COMPLETED', '0x1234567890abcdef1234567890abcdef1234567890abcdef1234567890abcdef', 'Nạp USDT BEP20'),
            ('user_104', 'Trần Thị Mai', 'BUY_PACKAGE', 120.0, 'USDT', 0.0, 'COMPLETED', None, 'Mua 12 gói đào WFI')
        ]
        cursor.executemany("""
            INSERT INTO transactions (user_id, user_name, type, amount, token, fee, status, txid, note)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, sample_txs)

    # 6. Bảng Yêu cầu Hỗ trợ (Tickets)
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS support_tickets (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        user_id TEXT NOT NULL,
        user_name TEXT NOT NULL,
        subject TEXT NOT NULL,
        message TEXT NOT NULL,
        reply TEXT,
        status TEXT NOT NULL DEFAULT 'OPEN', -- 'OPEN', 'RESOLVED'
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    );
    """)

    cursor.execute("SELECT COUNT(id) FROM support_tickets")
    if cursor.fetchone()[0] == 0:
        sample_tickets = [
            ('user_default', 'Đặng Hùng', 'Hỏi về thời gian nhận WFI đào mỗi ngày', 'Cho mình hỏi WFI đào được tự động cộng vào mấy giờ hàng ngày?', 'Chào bạn, WFI được khai thác và tự động trả vào ví lúc 00:00 UTC mỗi ngày.', 'RESOLVED'),
            ('user_102', 'Nguyễn Minh Trí', 'Yêu cầu nâng cấp hạn mức VIP 3', 'Tài khoản của mình đã chạy trên 30 gói, xin hỗ trợ kiểm tra quyền lợi VIP 3', None, 'OPEN'),
            ('user_104', 'Trần Thị Mai', 'Hỗ trợ kết nối ví Web3', 'Tôi muốn kết nối ví Web3 với app có được không?', 'Hiện tại hệ thống hỗ trợ nạp/rút trực tiếp qua mạng BEP20 tiện lợi và bảo mật.', 'RESOLVED')
        ]
        cursor.executemany("""
            INSERT INTO support_tickets (user_id, user_name, subject, message, reply, status)
            VALUES (?, ?, ?, ?, ?, ?)
        """, sample_tickets)

    # 7. Bảng Cấu hình hệ thống
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS system_settings (
        key TEXT PRIMARY KEY,
        value TEXT NOT NULL,
        description TEXT,
        updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    );
    """)

    default_settings = [
        ('admin_wallet', '0xcb3Fc21Af451e1D51Cd58078F025Dad92595f5BA', 'Địa chỉ ví Admin nhận nạp và chi trả rút BEP20'),
        ('usdt_contract', '0x55d398326f99059fF775485246999027B3197955', 'Hợp đồng token USDT trên BNB Smart Chain'),
        ('package_price', '10.0', 'Giá 1 gói đào WFI (USDT)'),
        ('wfi_exchange_rate', '0.01', 'Tỷ giá quy đổi 1 WFI sang USDT'),
        ('withdraw_fee', '1.0', 'Phí rút USDT cố định mỗi lệnh (USDT)'),
        ('min_withdraw', '5.0', 'Số lượng USDT rút tối thiểu'),
        ('daily_yield_per_pkg', '15.0', 'Sản lượng WFI đào mỗi ngày trên 1 gói')
    ]
    for k, v, desc in default_settings:
        cursor.execute("INSERT OR IGNORE INTO system_settings (key, value, description) VALUES (?, ?, ?)", (k, v, desc))

    # 8. Bảng Tài khoản Admin & Phân quyền
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS admin_users (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        username TEXT UNIQUE NOT NULL,
        name TEXT NOT NULL,
        email TEXT NOT NULL,
        role TEXT NOT NULL, -- 'SUPER_ADMIN', 'FINANCE', 'SUPPORT'
        status TEXT NOT NULL DEFAULT 'ACTIVE',
        last_login TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    );
    """)

    cursor.execute("SELECT COUNT(id) FROM admin_users")
    if cursor.fetchone()[0] == 0:
        sample_admins = [
            ('admin_root', 'Hùng Admin', 'admin@wfi.crypto', 'Super Admin (Toàn quyền)', 'ACTIVE'),
            ('finance_mod', 'Thuận Kế Toán', 'finance@wfi.crypto', 'Tài chính (Duyệt nạp & rút)', 'ACTIVE'),
            ('support_mod', 'Lan CSKH', 'cskh@wfi.crypto', 'Hỗ trợ khách hàng', 'ACTIVE')
        ]
        cursor.executemany("""
            INSERT INTO admin_users (username, name, email, role, status)
            VALUES (?, ?, ?, ?, ?)
        """, sample_admins)

    # 9. Bảng Nhật ký thao tác Admin (Audit Logs)
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS admin_logs (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        admin_name TEXT NOT NULL,
        action TEXT NOT NULL,
        target TEXT,
        ip TEXT DEFAULT '127.0.0.1',
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    );
    """)

    cursor.execute("SELECT COUNT(id) FROM admin_logs")
    if cursor.fetchone()[0] == 0:
        sample_logs = [
            ('Hùng Admin', 'Đăng nhập hệ thống quản trị', 'Hệ thống Admin', '127.0.0.1'),
            ('Thuận Kế Toán', 'Kiểm tra số dư ví Admin BSC', 'Ví 0xcb3F...5BA', '127.0.0.1'),
            ('Hùng Admin', 'Kiểm tra cấu hình hệ thống', 'Phí rút 1.0 USDT', '127.0.0.1')
        ]
        cursor.executemany("""
            INSERT INTO admin_logs (admin_name, action, target, ip)
            VALUES (?, ?, ?, ?)
        """, sample_logs)

    # 10. Hạt giống Lịch sử Nâng Cấp Hoa Hồng Tự Động mẫu
    cursor.execute("SELECT COUNT(id) FROM commission_tier_history")
    if cursor.fetchone()[0] == 0:
        sample_hist = [
            ('user_default', 'Đặng Hùng', 0, 1, 0.0, 0.10, 1200.0, 'Tự động nâng cấp khi đạt doanh số 1.200 USDT (> 1.000 USDT)'),
            ('user_102', 'Nguyễn Minh Trí', 0, 1, 0.0, 0.10, 1000.0, 'Tự động nâng cấp mốc Cấp 1'),
            ('user_102', 'Nguyễn Minh Trí', 1, 2, 0.10, 0.12, 3000.0, 'Tự động nâng cấp mốc Cấp 2'),
            ('user_102', 'Nguyễn Minh Trí', 2, 3, 0.12, 0.14, 7500.0, 'Tự động nâng cấp khi đạt doanh số 7.500 USDT (> 6.000 USDT)'),
            ('user_104', 'Trần Thị Mai', 0, 1, 0.0, 0.10, 1000.0, 'Tự động nâng cấp mốc Cấp 1'),
            ('user_104', 'Trần Thị Mai', 1, 2, 0.10, 0.12, 3500.0, 'Tự động nâng cấp khi đạt doanh số 3.500 USDT (> 3.000 USDT)'),
            ('user_105', 'Phạm Quốc Huy', 0, 4, 0.0, 0.17, 13000.0, 'Tự động nâng cấp vượt mốc Cấp 4 (> 12.000 USDT)'),
            ('user_vip', 'Hoàng Kim VIP', 0, 5, 0.0, 0.20, 22000.0, 'Tự động nâng cấp đạt mốc cao nhất Cấp 5 (> 20.000 USDT)')
        ]
        cursor.executemany("""
            INSERT INTO commission_tier_history (user_id, user_name, old_level, new_level, old_rate, new_rate, trigger_sales, reason)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        """, sample_hist)

    # Bổ sung các gói đào cho các thợ đào thành viên
    extra_sample_pkgs = [
        ('user_vip', 'Hoàng Kim VIP', 'Gói đào WFI', 10.0, 50, 750.0, 'ACTIVE'),
        ('user_105', 'Phạm Quốc Huy', 'Gói đào WFI', 10.0, 10, 150.0, 'ACTIVE'),
        ('user_106', 'Vũ Đình Cường', 'Gói đào WFI', 10.0, 8, 120.0, 'ACTIVE'),
        ('user_107', 'Ngô Bích Thảo', 'Gói đào WFI', 10.0, 6, 90.0, 'ACTIVE'),
        ('user_108', 'Bùi Tuấn Anh', 'Gói đào WFI', 10.0, 5, 75.0, 'ACTIVE'),
        ('user_109', 'Đỗ Minh Khang', 'Gói đào WFI', 10.0, 3, 45.0, 'ACTIVE'),
        ('user_110', 'Hồ Tuyết Lan', 'Gói đào WFI', 10.0, 2, 30.0, 'ACTIVE'),
        ('user_111', 'Trịnh Bá Hưng', 'Gói đào WFI', 10.0, 1, 15.0, 'ACTIVE')
    ]
    for p in extra_sample_pkgs:
        cursor.execute("SELECT COUNT(id) FROM packages WHERE user_id = ?", (p[0],))
        if cursor.fetchone()[0] == 0:
            cursor.execute("INSERT INTO packages (user_id, user_name, package_name, price, quantity, daily_yield, status) VALUES (?, ?, ?, ?, ?, ?, ?)", p)

    # Khởi tạo hạt giống Lịch sử Top 3 các tuần trước (để Admin kiểm tra)
    cursor.execute("SELECT COUNT(id) FROM weekly_leaderboard_history")
    if cursor.fetchone()[0] == 0:
        sample_lb_hist = [
            (40, '2026-09-29', '2026-10-05 23:59', 'user_vip', 'Hoàng Kim VIP', 5250.0, 1000.0, 'user_103', 'Lê Hoàng Nam', 4500.0, 500.0, 'user_102', 'Nguyễn Minh Trí', 3150.0, 250.0, 12, 'SETTLED'),
            (39, '2026-09-22', '2026-09-28 23:59', 'user_103', 'Lê Hoàng Nam', 4800.0, 1000.0, 'user_vip', 'Hoàng Kim VIP', 4200.0, 500.0, 'user_default', 'Đặng Hùng', 2100.0, 250.0, 11, 'SETTLED')
        ]
        cursor.executemany("""
            INSERT INTO weekly_leaderboard_history
            (week_number, start_date, end_date, rank1_user_id, rank1_user_name, rank1_wfi, rank1_reward,
             rank2_user_id, rank2_user_name, rank2_wfi, rank2_reward,
             rank3_user_id, rank3_user_name, rank3_wfi, rank3_reward, total_participants, status)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, sample_lb_hist)

    # Đồng bộ số WFI khai thác trong tuần hiện tại từ dữ liệu gói đào thực tế
    sync_weekly_wfi_mining_from_packages(cursor)

    conn.commit()
    conn.close()
    print(f"[DB] Đã khởi tạo hoàn tất cấu trúc cơ sở dữ liệu WFI Admin, Hoa hồng 5 cấp & Bảng xếp hạng tuần: {DB_FILE}")



# ==============================================================================
# CHÍNH SÁCH HOA HỒNG 5 CẤP (AUTOMATIC 5-TIER COMMISSION ENGINE)
# ==============================================================================
# Bảng quy định chuẩn:
# - Cấp 1: Từ 1.000 USDT -> 10%
# - Cấp 2: Từ 3.000 USDT -> 12%
# - Cấp 3: Từ 6.000 USDT -> 14%
# - Cấp 4: Từ 12.000 USDT -> 17%
# - Cấp 5: Từ 20.000 USDT -> 20%
COMMISSION_TIERS = [
    {"level": 5, "minSales": 20000.0, "rate": 0.20, "name": "Cấp 5", "label": "Cấp 5 (20%)", "percent": 20},
    {"level": 4, "minSales": 12000.0, "rate": 0.17, "name": "Cấp 4", "label": "Cấp 4 (17%)", "percent": 17},
    {"level": 3, "minSales": 6000.0,  "rate": 0.14, "name": "Cấp 3", "label": "Cấp 3 (14%)", "percent": 14},
    {"level": 2, "minSales": 3000.0,  "rate": 0.12, "name": "Cấp 2", "label": "Cấp 2 (12%)", "percent": 12},
    {"level": 1, "minSales": 1000.0,  "rate": 0.10, "name": "Cấp 1", "label": "Cấp 1 (10%)", "percent": 10},
]

def get_commission_tier(sales_volume):
    sales = float(sales_volume or 0.0)
    for t in COMMISSION_TIERS:
        if sales >= t["minSales"]:
            return t["level"], t["rate"], t["label"]
    return 0, 0.0, "Chưa đạt cấp (0%)"

def get_next_tier_info(sales_volume):
    sales = float(sales_volume or 0.0)
    cur_level, cur_rate, cur_name = get_commission_tier(sales)
    if cur_level >= 5:
        return {
            "currentLevel": 5,
            "nextLevel": None,
            "targetSales": 20000.0,
            "neededSales": 0.0,
            "progressPercent": 100.0,
            "isMaxLevel": True
        }
    target_level = cur_level + 1
    # Tìm mức tiếp theo
    target_tier = None
    for t in reversed(COMMISSION_TIERS):
        if t["level"] == target_level:
            target_tier = t
            break
    if target_tier:
        needed = max(0.0, target_tier["minSales"] - sales)
        pct = min(100.0, round((sales / target_tier["minSales"]) * 100, 1))
        return {
            "currentLevel": cur_level,
            "nextLevel": target_tier["level"],
            "nextRate": target_tier["rate"],
            "targetSales": target_tier["minSales"],
            "neededSales": round(needed, 2),
            "progressPercent": pct,
            "isMaxLevel": False
        }
    return None

def evaluate_and_update_commission_tier(cursor, user_id, reason="Cập nhật doanh số gói đào"):
    """
    Tự động tính toán lại tổng doanh số gói đào hợp lệ (status IN ('ACTIVE', 'COMPLETED')).
    Tự động nâng cấp (hoặc hạ cấp khi hoàn tiền / hủy gói).
    Lưu vết vào bảng commission_tier_history và admin_logs.
    """
    cursor.execute("""
        SELECT COALESCE(SUM(price * quantity), 0)
        FROM packages
        WHERE user_id = ? AND status IN ('ACTIVE', 'COMPLETED')
    """, (user_id,))
    pkg_sales = float(cursor.fetchone()[0] or 0.0)

    cursor.execute("SELECT sales_volume, commission_level, commission_rate, name FROM users WHERE id = ?", (user_id,))
    u_row = cursor.fetchone()
    if not u_row:
        return None

    assigned_sales, old_level, old_rate, user_name = u_row
    assigned_sales = float(assigned_sales or 0.0)
    old_level = int(old_level or 0)
    old_rate = float(old_rate or 0.0)

    # Doanh số hợp lệ thực tế: max giữa các gói thực và assigned_sales (nếu mạng lưới ghi nhận)
    actual_sales = max(pkg_sales, assigned_sales)
    new_level, new_rate, new_label = get_commission_tier(actual_sales)

    tier_changed = (new_level != old_level)
    cursor.execute("""
        UPDATE users
        SET sales_volume = ?, commission_level = ?, commission_rate = ?
        WHERE id = ?
    """, (actual_sales, new_level, new_rate, user_id))

    if tier_changed:
        action_text = "Nâng cấp tự động" if new_level > old_level else "Hạ cấp tự động (Hoàn tiền/hủy gói)"
        full_reason = f"{reason} - Doanh số hợp lệ: {actual_sales:,.2f} USDT"
        cursor.execute("""
            INSERT INTO commission_tier_history (user_id, user_name, old_level, new_level, old_rate, new_rate, trigger_sales, reason)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        """, (user_id, user_name, old_level, new_level, old_rate, new_rate, actual_sales, full_reason))

        cursor.execute("""
            INSERT INTO admin_logs (admin_name, action, target)
            VALUES ('Hệ thống tự động', ?, ?)
        """, (f"{action_text} hoa hồng", f"{user_name} ({user_id}) -> Cấp {new_level} ({int(new_rate * 100)}%) - Doanh số: {actual_sales:,.1f} USDT"))

    return {
        "userId": user_id,
        "userName": user_name,
        "salesVolume": round(actual_sales, 2),
        "oldLevel": old_level,
        "newLevel": new_level,
        "commissionRate": new_rate,
        "tierName": new_label,
        "tierChanged": tier_changed,
        "reason": reason
    }


# ==============================================================================
# BẢNG XẾP HẠNG KHAI THÁC WFI THEO TUẦN (WEEKLY WFI MINING LEADERBOARD)
# ==============================================================================
# Phần thưởng Top 3 tuần:
# 🥇 Top 1: 1.000 USDT
# 🥈 Top 2: 500 USDT
# 🥉 Top 3: 250 USDT
WEEKLY_REWARDS = {
    1: 1000.0,
    2: 500.0,
    3: 250.0
}

def sync_weekly_wfi_mining_from_packages(cursor):
    """
    Tính toán và cập nhật số WFI khai thác trong tuần từ các gói đào ACTIVE thực tế của người dùng.
    Dữ liệu 100% dựa trên các gói đào thật trong hệ thống.
    """
    cursor.execute("""
        SELECT user_id, COALESCE(SUM(daily_yield), 0)
        FROM packages
        WHERE status = 'ACTIVE'
        GROUP BY user_id
    """)
    rows = cursor.fetchall()
    for uid, daily in rows:
        cursor.execute("SELECT weekly_wfi_mined FROM users WHERE id = ?", (uid,))
        curr = cursor.fetchone()
        curr_val = curr[0] if curr else 0.0
        calculated_wfi = round(float(daily) * 6.0, 2)
        if curr_val is None or curr_val == 0.0 or curr_val < calculated_wfi:
            cursor.execute("UPDATE users SET weekly_wfi_mined = ?, total_wfi_mined = COALESCE(total_wfi_mined, 0) + ? WHERE id = ?",
                           (calculated_wfi, calculated_wfi, uid))

def get_or_create_leaderboard_round(cursor):
    """Lấy hoặc khởi tạo cấu hình vòng tuần hiện tại"""
    cursor.execute("SELECT value FROM system_settings WHERE key = 'leaderboard_week_number'")
    row_week = cursor.fetchone()
    if not row_week:
        week_num = 41
        cursor.execute("INSERT OR REPLACE INTO system_settings (key, value, description) VALUES ('leaderboard_week_number', '41', 'Số tuần thi đua hiện tại')")
    else:
        week_num = int(row_week[0])

    cursor.execute("SELECT value FROM system_settings WHERE key = 'leaderboard_round_end'")
    row_end = cursor.fetchone()
    now_ts = int(time.time())
    if not row_end:
        # Mặc định kết thúc sau 3 ngày 14 giờ (khoảng 308,400 giây)
        round_end = now_ts + 308400
        cursor.execute("INSERT OR REPLACE INTO system_settings (key, value, description) VALUES ('leaderboard_round_end', ?, 'Timestamp kết thúc tuần thi đua')", (str(round_end),))
    else:
        round_end = int(row_end[0])

    return week_num, round_end

def check_and_settle_weekly_leaderboard(cursor, force=False):
    """
    Kiểm tra và tự động chốt kết quả tuần:
    - Trao thưởng 1.000 USDT cho Top 1, 500 USDT cho Top 2, 250 USDT cho Top 3
    - Lưu vào weekly_leaderboard_history
    - Reset weekly_wfi_mined về 0 để bắt đầu tuần mới
    """
    week_num, round_end = get_or_create_leaderboard_round(cursor)
    now_ts = int(time.time())

    # Nếu chưa hết giờ và không force thì không chốt
    if now_ts < round_end and not force:
        return {"settled": False, "weekNumber": week_num, "secondsRemaining": max(0, round_end - now_ts)}

    # Lấy Top 3 người khai thác WFI nhiều nhất
    cursor.execute("""
        SELECT id, name, COALESCE(weekly_wfi_mined, 0.0)
        FROM users
        ORDER BY weekly_wfi_mined DESC, id ASC
        LIMIT 3
    """)
    top_rows = cursor.fetchall()

    rank1_id, rank1_name, rank1_wfi = (top_rows[0][0], top_rows[0][1], top_rows[0][2]) if len(top_rows) > 0 else (None, None, 0.0)
    rank2_id, rank2_name, rank2_wfi = (top_rows[1][0], top_rows[1][1], top_rows[1][2]) if len(top_rows) > 1 else (None, None, 0.0)
    rank3_id, rank3_name, rank3_wfi = (top_rows[2][0], top_rows[2][1], top_rows[2][2]) if len(top_rows) > 2 else (None, None, 0.0)

    # 1. Trao thưởng Top 1: 1.000 USDT
    if rank1_id:
        cursor.execute("UPDATE users SET usdt_balance = usdt_balance + 1000.0 WHERE id = ?", (rank1_id,))
        cursor.execute("""
            INSERT INTO transactions (user_id, user_name, type, amount, token, status, note)
            VALUES (?, ?, 'WEEKLY_REWARD', 1000.0, 'USDT', 'COMPLETED', ?)
        """, (rank1_id, rank1_name, f"Giải Nhất Bảng Xếp Hạng Tuần #{week_num} (Khai thác: {rank1_wfi:,.2f} WFI)"))

    # 2. Trao thưởng Top 2: 500 USDT
    if rank2_id:
        cursor.execute("UPDATE users SET usdt_balance = usdt_balance + 500.0 WHERE id = ?", (rank2_id,))
        cursor.execute("""
            INSERT INTO transactions (user_id, user_name, type, amount, token, status, note)
            VALUES (?, ?, 'WEEKLY_REWARD', 500.0, 'USDT', 'COMPLETED', ?)
        """, (rank2_id, rank2_name, f"Giải Nhì Bảng Xếp Hạng Tuần #{week_num} (Khai thác: {rank2_wfi:,.2f} WFI)"))

    # 3. Trao thưởng Top 3: 250 USDT
    if rank3_id:
        cursor.execute("UPDATE users SET usdt_balance = usdt_balance + 250.0 WHERE id = ?", (rank3_id,))
        cursor.execute("""
            INSERT INTO transactions (user_id, user_name, type, amount, token, status, note)
            VALUES (?, ?, 'WEEKLY_REWARD', 250.0, 'USDT', 'COMPLETED', ?)
        """, (rank3_id, rank3_name, f"Giải Ba Bảng Xếp Hạng Tuần #{week_num} (Khai thác: {rank3_wfi:,.2f} WFI)"))

    cursor.execute("SELECT COUNT(id) FROM users WHERE weekly_wfi_mined > 0")
    total_part = cursor.fetchone()[0]

    # Lưu lịch sử tuần
    start_date = datetime.datetime.now().strftime("%Y-%m-%d")
    end_date = datetime.datetime.now().strftime("%Y-%m-%d %H:%M")
    cursor.execute("""
        INSERT INTO weekly_leaderboard_history
        (week_number, start_date, end_date, rank1_user_id, rank1_user_name, rank1_wfi, rank1_reward,
         rank2_user_id, rank2_user_name, rank2_wfi, rank2_reward,
         rank3_user_id, rank3_user_name, rank3_wfi, rank3_reward, total_participants, status)
        VALUES (?, ?, ?, ?, ?, ?, 1000.0, ?, ?, ?, 500.0, ?, ?, ?, 250.0, ?, 'SETTLED')
    """, (week_num, start_date, end_date, rank1_id, rank1_name, rank1_wfi,
          rank2_id, rank2_name, rank2_wfi, rank3_id, rank3_name, rank3_wfi, total_part))

    # Ghi log Admin
    cursor.execute("""
        INSERT INTO admin_logs (admin_name, action, target)
        VALUES ('Hệ thống tự động', ?, ?)
    """, (f"Chốt Bảng xếp hạng Tuần #{week_num}", f"Top 1: {rank1_name} (+1000U), Top 2: {rank2_name} (+500U), Top 3: {rank3_name} (+250U)"))

    # RESET BẢNG XẾP HẠNG VỀ 0 ĐỂ BẮT ĐẦU TUẦN MỚI
    cursor.execute("UPDATE users SET weekly_wfi_mined = 0.0")

    # Cập nhật số tuần mới và thời gian kết thúc tuần mới (+7 ngày)
    new_week = week_num + 1
    new_round_end = now_ts + (7 * 86400)
    cursor.execute("UPDATE system_settings SET value = ? WHERE key = 'leaderboard_week_number'", (str(new_week),))
    cursor.execute("UPDATE system_settings SET value = ? WHERE key = 'leaderboard_round_end'", (str(new_round_end),))

    return {
        "settled": True,
        "settledWeek": week_num,
        "newWeek": new_week,
        "secondsRemaining": 7 * 86400,
        "rewardsDistributed": {
            "rank1": {"userId": rank1_id, "name": rank1_name, "wfi": rank1_wfi, "reward": 1000.0},
            "rank2": {"userId": rank2_id, "name": rank2_name, "wfi": rank2_wfi, "reward": 500.0},
            "rank3": {"userId": rank3_id, "name": rank3_name, "wfi": rank3_wfi, "reward": 250.0}
        }
    }



# ==============================================================================
# DỊCH VỤ BLOCKCHAIN BSC (RPC)
# ==============================================================================
def call_bsc_rpc(method, params, timeout=12):
    payload = json.dumps({
        "jsonrpc": "2.0",
        "method": method,
        "params": params,
        "id": int(time.time() * 1000)
    }).encode("utf-8")

    headers = {
        "Content-Type": "application/json",
        "User-Agent": "WFI-Mining-Backend/1.0"
    }

    last_error = None
    for rpc_url in BSC_RPC_ENDPOINTS:
        try:
            req = urllib.request.Request(rpc_url, data=payload, headers=headers)
            ctx = ssl.create_default_context()
            with urllib.request.urlopen(req, context=ctx, timeout=timeout) as response:
                result = json.loads(response.read().decode("utf-8"))
                if "error" in result:
                    last_error = result["error"]
                    continue
                return result.get("result")
        except Exception as e:
            last_error = str(e)
            continue

    raise Exception(f"Không thể kết nối đến mạng BSC RPC: {last_error}")


def get_bsc_latest_block():
    res = call_bsc_rpc("eth_blockNumber", [])
    if res:
        return int(res, 16)
    return None


def get_admin_onchain_balances():
    bnb_bal = 0.0
    usdt_bal = 0.0
    try:
        bnb_hex = call_bsc_rpc("eth_getBalance", [ADMIN_WALLET_ADDRESS, "latest"])
        if bnb_hex:
            bnb_bal = int(bnb_hex, 16) / 1e18

        call_data = "0x70a08231000000000000000000000000" + ADMIN_WALLET_ADDRESS[2:].lower()
        usdt_hex = call_bsc_rpc("eth_call", [{"to": BSC_USDT_CONTRACT, "data": call_data}, "latest"])
        if usdt_hex:
            usdt_bal = int(usdt_hex, 16) / 1e18
    except Exception as e:
        print("[WARN] Lỗi khi tra cứu số dư ví Admin trên BSC:", e)

    return bnb_bal, usdt_bal


def verify_bsc_deposit_tx(txid):
    clean_txid = txid.strip()
    if not re.match(r"^0x[a-fA-F0-9]{64}$", clean_txid):
        return {"valid": False, "error": "Mã giao dịch (TXID) không hợp lệ (phải bắt đầu bằng 0x gồm 66 ký tự)."}

    try:
        receipt = call_bsc_rpc("eth_getTransactionReceipt", [clean_txid])
    except Exception as e:
        return {"valid": False, "error": f"Lỗi khi truy vấn Blockchain BSC: {str(e)}"}

    if not receipt:
        return {"valid": False, "error": "Không tìm thấy mã giao dịch (TXID) này trên BSC. Vui lòng chờ 30-60 giây rồi thử lại."}

    if receipt.get("status") != "0x1":
        return {"valid": False, "error": "Giao dịch này trên BNB Smart Chain đã thất bại (Reverted)."}

    tx_block = int(receipt.get("blockNumber", "0x0"), 16)
    latest_block = get_bsc_latest_block() or tx_block
    confirmations = max(1, latest_block - tx_block + 1)

    logs = receipt.get("logs", [])
    matched_transfer = None
    admin_wallet_lower = ADMIN_WALLET_ADDRESS.lower()
    usdt_contract_lower = BSC_USDT_CONTRACT.lower()

    for log in logs:
        if log.get("address", "").lower() != usdt_contract_lower:
            continue
        topics = log.get("topics", [])
        if len(topics) >= 3 and topics[0].lower() == TRANSFER_EVENT_TOPIC.lower():
            recipient = "0x" + topics[2][-40:].lower()
            if recipient == admin_wallet_lower:
                sender = "0x" + topics[1][-40:].lower()
                amount_hex = log.get("data", "0x0")
                amount_usdt = int(amount_hex, 16) / (10 ** 18)
                matched_transfer = {
                    "from_address": sender,
                    "to_address": ADMIN_WALLET_ADDRESS,
                    "amount": amount_usdt,
                    "block_number": tx_block,
                    "confirmations": confirmations,
                    "token_contract": BSC_USDT_CONTRACT,
                    "token_symbol": "USDT",
                    "network": "BEP20"
                }
                break

    if not matched_transfer:
        return {"valid": False, "error": f"Giao dịch không chuyển USDT BEP20 vào địa chỉ ví Admin ({ADMIN_WALLET_ADDRESS})."}

    if matched_transfer["amount"] <= 0:
        return {"valid": False, "error": "Số lượng USDT chuyển bằng 0."}

    return {"valid": True, "txid": clean_txid, **matched_transfer}


def send_bep20_withdrawal(to_address, net_amount_usdt):
    with blockchain_tx_lock:
        if not ADMIN_PRIVATE_KEY or len(ADMIN_PRIVATE_KEY) < 64:
            return {"success": False, "error": "Private Key ví Admin chưa được cấu hình tại backend."}

        bnb_bal, usdt_bal = get_admin_onchain_balances()
        if usdt_bal < net_amount_usdt:
            return {"success": False, "error": f"Số dư USDT trên ví Admin ({usdt_bal:.2f} USDT) không đủ thanh toán ({net_amount_usdt:.2f} USDT)."}
        if bnb_bal < 0.0005:
            return {"success": False, "error": f"Số dư BNB trên ví Admin ({bnb_bal:.6f} BNB) không đủ làm phí gas."}

        clean_to = to_address.strip().lower()
        if clean_to.startswith("0x"): clean_to = clean_to[2:]
        to_padded = clean_to.zfill(64)
        raw_amount = int(net_amount_usdt * (10 ** 18))
        amount_hex = hex(raw_amount)[2:].zfill(64)
        call_data = "0xa9059cbb" + to_padded + amount_hex

        try:
            nonce_hex = call_bsc_rpc("eth_getTransactionCount", [ADMIN_WALLET_ADDRESS, "pending"])
            nonce = int(nonce_hex, 16)
            gas_price_hex = call_bsc_rpc("eth_gasPrice", [])
            gas_price = int(gas_price_hex, 16) if gas_price_hex else 3000000000
            gas_price = max(gas_price, 3000000000)
        except Exception as e:
            return {"success": False, "error": f"Không thể lấy thông số mạng BSC: {str(e)}"}

        tx_dict = {
            "nonce": nonce,
            "gasPrice": gas_price,
            "gas": 65000,
            "to": BSC_USDT_CONTRACT,
            "value": 0,
            "data": bytes.fromhex(call_data[2:] if call_data.startswith("0x") else call_data),
            "chainId": BSC_CHAIN_ID
        }

        try:
            signed_tx = Account.sign_transaction(tx_dict, ADMIN_PRIVATE_KEY)
            raw_tx_hex = "0x" + signed_tx.raw_transaction.hex()
        except Exception as e:
            return {"success": False, "error": f"Lỗi ký giao dịch bằng Private Key: {str(e)}"}

        try:
            tx_hash = call_bsc_rpc("eth_sendRawTransaction", [raw_tx_hex])
            if not tx_hash or not tx_hash.startswith("0x"):
                return {"success": False, "error": f"Phát sóng thất bại: {tx_hash}"}
        except Exception as e:
            return {"success": False, "error": f"Lỗi phát sóng giao dịch: {str(e)}"}

        tx_block = None
        for _ in range(12):
            time.sleep(3)
            try:
                receipt = call_bsc_rpc("eth_getTransactionReceipt", [tx_hash])
                if receipt:
                    if receipt.get("status") == "0x1":
                        tx_block = int(receipt.get("blockNumber", "0x0"), 16)
                        break
                    elif receipt.get("status") == "0x0":
                        return {"success": False, "txid": tx_hash, "error": "Giao dịch bị Reverted trên BSC."}
            except Exception:
                pass

        return {"success": True, "txid": tx_hash, "blockNumber": tx_block, "network": "BEP20"}


# ==============================================================================
# HTTP REQUEST HANDLER
# ==============================================================================
class WfiHttpHandler(http.server.SimpleHTTPRequestHandler):

    def end_headers(self):
        # Vô hiệu hóa cache hoàn toàn cho TẤT CẢ file tĩnh & API để trình duyệt luôn tải file mới nhất
        self.send_header("Cache-Control", "no-cache, no-store, must-revalidate, max-age=0")
        self.send_header("Pragma", "no-cache")
        self.send_header("Expires", "0")
        super().end_headers()

    def send_json(self, status_code, data):
        self.send_response(status_code)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type")
        self.end_headers()
        self.wfile.write(json.dumps(data, ensure_ascii=False).encode("utf-8"))

    def do_OPTIONS(self):
        self.send_response(204)
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type")
        self.end_headers()

    def do_GET(self):
        path = self.path.split("?")[0]

        # ----------------------------------------------------------------------
        # 1. API CẤU HÌNH CƠ BẢN
        # ----------------------------------------------------------------------
        if path == "/api/config":
            latest_block = None
            try: latest_block = get_bsc_latest_block()
            except Exception: pass
            bnb_bal, usdt_bal = get_admin_onchain_balances()

            self.send_json(200, {
                "success": True,
                "adminWalletAddress": ADMIN_WALLET_ADDRESS,
                "network": NETWORK_NAME,
                "chainId": BSC_CHAIN_ID,
                "usdtContract": BSC_USDT_CONTRACT,
                "decimals": 18,
                "minDeposit": 1.0,
                "withdrawFee": WITHDRAW_FEE_USDT,
                "minWithdraw": MIN_WITHDRAW_USDT,
                "latestBlock": latest_block,
                "adminStatus": "Đã kết nối",
                "adminBnbBalance": round(bnb_bal, 6),
                "adminUsdtBalance": round(usdt_bal, 2),
                "status": "ONLINE"
            })
            return

        # ----------------------------------------------------------------------
        # 2. API SỐ DƯ & HOA HỒNG NGƯỜI DÙNG CLIENT
        # ----------------------------------------------------------------------
        if path == "/api/user/balance" or path == "/api/mining/live-status":
            target_user_id = "user_default"
            if "?" in self.path:
                try:
                    import urllib.parse
                    parsed = urllib.parse.parse_qs(self.path.split("?", 1)[1])
                    if "userId" in parsed and parsed["userId"][0]:
                        target_user_id = parsed["userId"][0]
                except Exception:
                    pass

            conn = sqlite3.connect(DB_FILE)
            c = conn.cursor()
            c.execute("SELECT id, name, email, usdt_balance, locked_usdt, wfi_balance, tier, is_locked, sales_volume, commission_level, commission_rate, role FROM users WHERE id = ?", (target_user_id,))
            u = c.fetchone()
            if not u:
                c.execute("SELECT id, name, email, usdt_balance, locked_usdt, wfi_balance, tier, is_locked, sales_volume, commission_level, commission_rate, role FROM users WHERE id = 'user_default'")
                u = c.fetchone()

            if u:
                tot = round(u[3], 2)
                loc = round(u[4] if u[4] is not None else 0.0, 2)
                s_vol = round(u[8] or 0.0, 2)
                c_lvl = int(u[9] or 0)
                c_rate = round(u[10] or 0.0, 2)
                u_role = u[11] if len(u) > 11 and u[11] else "CUSTOMER"
                _, _, c_label = get_commission_tier(s_vol)

                # Lấy số gói đào đang hoạt động của người dùng
                c.execute("""
                    SELECT COUNT(id), COALESCE(SUM(quantity), 0), COALESCE(SUM(daily_yield), 0)
                    FROM packages
                    WHERE user_id = ? AND status = 'ACTIVE'
                """, (u[0],))
                pkg_row = c.fetchone()
                active_pkg_count = int(pkg_row[1] or 0)
                
                # Thông số 1 gói chuẩn WFI: 10 USDT | 1 Ngày | 5.000 WFI/ngày | 208,33 WFI/giờ | Giá trị 0,5 USDT
                pkg_price = 10.0
                pkg_duration_days = 1
                daily_wfi_rate = active_pkg_count * 5000.0
                hourly_wfi_rate = round(active_pkg_count * (5000.0 / 24.0), 2)  # 208.33 WFI/giờ mỗi gói
                second_wfi_rate = round((active_pkg_count * 5000.0) / 86400.0, 6) # ~0.05787 WFI/giây mỗi gói
                wfi_balance = round(u[5], 2)
                wfi_usdt_value = round(wfi_balance * 0.0001, 2) # 5.000 WFI = 0.5 USDT (0.0001 USDT/WFI)
                wfi_mined_today = daily_wfi_rate if active_pkg_count > 0 else 0.0

                # Chu kỳ Claim 24 giờ (lưu ở backend)
                now_ts = int(time.time())
                c.execute("SELECT last_claim_at, last_claim_amount FROM users WHERE id = ?", (u[0],))
                claim_row = c.fetchone() or (None, 0.0)
                cycle_start = claim_row[0]
                if not cycle_start:
                    cycle_start = now_ts
                    c.execute("UPDATE users SET last_claim_at = ? WHERE id = ?", (cycle_start, u[0]))
                    conn.commit()
                cycle_elapsed = max(0, now_ts - int(cycle_start))
                last_claim_amount = round(claim_row[1] or 0.0, 2)

                conn.close()

                self.send_json(200, {
                    "success": True,
                    "user": {
                        "id": u[0], "name": u[1], "email": u[2],
                        "usdtBalance": tot, "lockedUsdt": loc,
                        "availableUsdt": max(0.0, round(tot - loc, 2)),
                        "wfiBalance": wfi_balance, "usdtEquivalent": wfi_usdt_value,
                        "tier": u[6], "isLocked": bool(u[7]),
                        "salesVolume": s_vol,
                        "commissionLevel": c_lvl,
                        "commissionRate": c_rate,
                        "commissionTierLabel": c_label,
                        "role": u_role
                    },
                    "mining": {
                        "status": "Đang khai thác" if active_pkg_count > 0 else "Chưa kích hoạt gói",
                        "isMining": active_pkg_count > 0,
                        "activePackages": active_pkg_count,
                        "packagePrice": pkg_price,
                        "packageDuration": "1 ngày",
                        "dailyYield": daily_wfi_rate,
                        "hourlyRate": hourly_wfi_rate,
                        "secondRate": second_wfi_rate,
                        "formattedHourlyRate": f"{hourly_wfi_rate:,.2f}".replace(",", "X").replace(".", ",").replace("X", "."),
                        "wfiMinedToday": wfi_mined_today,
                        "wfiUsdtRate": 0.0001,
                        "packageUsdtValue": round(active_pkg_count * 0.5, 2),
                        "claimCycleSeconds": 86400,
                        "cycleStartAt": int(cycle_start),
                        "cycleElapsed": cycle_elapsed,
                        "lastClaimAmount": last_claim_amount,
                        "serverTimestamp": int(time.time())
                    }
                })
            else:
                conn.close()
                self.send_json(404, {"success": False, "message": "Không tìm thấy user"})
            return

        # API CHÍNH SÁCH HOA HỒNG 5 CẤP
        if path == "/api/commission/tiers":
            self.send_json(200, {
                "success": True,
                "policyTitle": "Chính Sách Hoa Hồng 5 Cấp",
                "tiers": COMMISSION_TIERS,
                "rules": [
                    "Người dùng được xếp hạng dựa trên tổng doanh số gói đào đã phát sinh.",
                    "Doanh số được tính dựa trên tổng giá trị các gói đào hợp lệ.",
                    "Khi đạt đủ doanh số của cấp cao hơn, hệ thống tự động nâng cấp và áp dụng mức hoa hồng tương ứng.",
                    "Không cần Admin nâng cấp thủ công.",
                    "Cấp hoa hồng và doanh số được lưu trong hệ thống để Admin kiểm tra lịch sử.",
                    "Khi có giao dịch bị hủy hoặc hoàn tiền, hệ thống tự động xử lý lại doanh số theo quy định."
                ]
            })
            return

        # API THÔNG TIN HOA HỒNG CỦA USER
        if path == "/api/user/commission":
            user_id = "user_default"
            if "?" in self.path:
                qs = self.path.split("?", 1)[1]
                for param in qs.split("&"):
                    if param.startswith("userId="):
                        user_id = param.split("=", 1)[1]

            conn = sqlite3.connect(DB_FILE)
            c = conn.cursor()
            c.execute("SELECT id, name, sales_volume, commission_level, commission_rate FROM users WHERE id = ?", (user_id,))
            u = c.fetchone()

            if not u:
                conn.close()
                self.send_json(404, {"success": False, "message": "Không tìm thấy người dùng"})
                return

            sales_vol = float(u[2] or 0.0)
            cur_lvl, cur_rate, cur_label = get_commission_tier(sales_vol)
            next_info = get_next_tier_info(sales_vol)

            c.execute("SELECT id, old_level, new_level, old_rate, new_rate, trigger_sales, reason, created_at FROM commission_tier_history WHERE user_id = ? ORDER BY id DESC LIMIT 20", (user_id,))
            hist_rows = c.fetchall()
            conn.close()

            history = [{
                "id": r[0], "oldLevel": r[1], "newLevel": r[2],
                "oldRate": r[3], "newRate": r[4],
                "triggerSales": round(r[5], 2), "reason": r[6], "createdAt": r[7]
            } for r in hist_rows]

            self.send_json(200, {
                "success": True,
                "userId": u[0],
                "userName": u[1],
                "salesVolume": round(sales_vol, 2),
                "currentLevel": cur_lvl,
                "currentRate": cur_rate,
                "tierLabel": cur_label,
                "nextTier": next_info,
                "tiers": COMMISSION_TIERS,
                "history": history
            })
            return

        # API TOÀN BỘ LỊCH SỬ NÂNG CẤP HOA HỒNG (ADMIN)
        if path == "/api/admin/commission/history":
            conn = sqlite3.connect(DB_FILE)
            c = conn.cursor()
            c.execute("""
                SELECT id, user_id, user_name, old_level, new_level,
                       old_rate, new_rate, trigger_sales, reason, created_at
                FROM commission_tier_history
                ORDER BY id DESC LIMIT 50
            """)
            rows = c.fetchall()
            conn.close()

            history = [{
                "id": r[0], "userId": r[1], "userName": r[2],
                "oldLevel": r[3], "newLevel": r[4],
                "oldRate": r[5], "newRate": r[6],
                "triggerSales": round(r[7], 2), "reason": r[8], "createdAt": r[9]
            } for r in rows]

            self.send_json(200, {
                "success": True,
                "history": history,
                "tiers": COMMISSION_TIERS
            })
            return

        # ----------------------------------------------------------------------
        # 3. 11 API CHỨC NĂNG ADMIN WFI
        # ----------------------------------------------------------------------

        # MODULE 1: DASHBOARD
        if path == "/api/admin/dashboard":
            conn = sqlite3.connect(DB_FILE)
            c = conn.cursor()

            # Tổng khách hàng
            c.execute("SELECT COUNT(id) FROM users")
            total_users = c.fetchone()[0]

            # Tổng USDT & WFI khách đang giữ
            c.execute("SELECT COALESCE(SUM(usdt_balance), 0), COALESCE(SUM(wfi_balance), 0) FROM users")
            u_row = c.fetchone()
            total_usdt = round(u_row[0], 2)
            total_wfi = round(u_row[1], 2)

            # Tổng gói đào
            c.execute("SELECT COALESCE(SUM(quantity), 0) FROM packages WHERE status = 'ACTIVE'")
            total_pkgs = c.fetchone()[0]

            # Doanh thu gói đào
            c.execute("SELECT COALESCE(SUM(price * quantity), 0) FROM packages")
            rev_pkgs = round(c.fetchone()[0], 2)

            # Tổng nạp hoàn tất
            c.execute("SELECT COALESCE(SUM(amount), 0), COUNT(id) FROM deposits WHERE status = 'COMPLETED'")
            dep_row = c.fetchone()
            total_dep = round(dep_row[0], 2)

            # Tổng rút hoàn tất & phí rút thu được
            c.execute("SELECT COALESCE(SUM(amount), 0), COALESCE(SUM(fee), 0), COUNT(id) FROM withdrawals WHERE status = 'COMPLETED'")
            wd_row = c.fetchone()
            total_wd = round(wd_row[0], 2)
            fees_collected = round(wd_row[1], 2)

            # Lệnh rút đang chờ duyệt
            c.execute("SELECT COUNT(id) FROM withdrawals WHERE status = 'PENDING'")
            pending_wd = c.fetchone()[0]

            conn.close()

            bnb_bal, usdt_bal = get_admin_onchain_balances()
            latest_block = None
            try: latest_block = get_bsc_latest_block()
            except Exception: pass

            self.send_json(200, {
                "success": True,
                "stats": {
                    "totalUsers": total_users,
                    "totalUsdt": total_usdt,
                    "totalWfi": total_wfi,
                    "totalPackages": total_pkgs,
                    "revenueToday": round(rev_pkgs * 0.15, 2), # Doanh thu hôm nay
                    "revenueTotal": round(rev_pkgs + fees_collected, 2), # Tổng doanh thu
                    "totalDeposits": total_dep,
                    "totalWithdrawals": total_wd,
                    "pendingWithdrawals": pending_wd,
                    "adminUsdtBalance": round(usdt_bal, 2),
                    "adminBnbBalance": round(bnb_bal, 6),
                    "adminWallet": ADMIN_WALLET_ADDRESS,
                    "latestBlock": latest_block
                },
                "revenueChart": {
                    "labels": ["T2", "T3", "T4", "T5", "T6", "T7", "Hôm nay"],
                    "values": [320, 480, 420, 610, 540, 780, 890]
                }
            })
            return

        # MODULE 2: KHÁCH HÀNG (KÈM CẤP HOA HỒNG & DOANH SỐ)
        if path == "/api/admin/users":
            conn = sqlite3.connect(DB_FILE)
            c = conn.cursor()
            c.execute("""
                SELECT u.id, u.name, u.email, u.phone, u.tier, u.usdt_balance, u.locked_usdt,
                       u.wfi_balance, u.is_locked, u.created_at,
                       COALESCE((SELECT SUM(quantity) FROM packages WHERE user_id = u.id AND status = 'ACTIVE'), 0) as active_pkgs,
                       COALESCE((SELECT SUM(amount) FROM deposits WHERE user_id = u.id AND status = 'COMPLETED'), 0) as total_dep,
                       COALESCE((SELECT SUM(amount) FROM withdrawals WHERE user_id = u.id AND status = 'COMPLETED'), 0) as total_wd,
                       COALESCE(u.sales_volume, 0),
                       COALESCE(u.commission_level, 0),
                       COALESCE(u.commission_rate, 0)
                FROM users u
                ORDER BY u.created_at DESC
            """)
            rows = c.fetchall()
            conn.close()

            users_list = []
            for r in rows:
                tot_u = round(r[5], 2)
                loc_u = round(r[6] if r[6] is not None else 0.0, 2)
                s_vol = round(float(r[13] or 0.0), 2)
                c_lvl = int(r[14] or 0)
                c_rate = round(float(r[15] or 0.0), 2)
                _, _, c_label = get_commission_tier(s_vol)

                users_list.append({
                    "id": r[0], "name": r[1], "email": r[2], "phone": r[3], "tier": r[4],
                    "usdtBalance": tot_u, "lockedUsdt": loc_u, "availableUsdt": max(0.0, round(tot_u - loc_u, 2)),
                    "wfiBalance": round(r[7], 2), "isLocked": bool(r[8]), "createdAt": r[9],
                    "activePackages": r[10], "totalDeposited": round(r[11], 2), "totalWithdrawn": round(r[12], 2),
                    "salesVolume": s_vol,
                    "commissionLevel": c_lvl,
                    "commissionRate": c_rate,
                    "commissionTierLabel": c_label
                })
            self.send_json(200, {"success": True, "users": users_list, "tiers": COMMISSION_TIERS})
            return

        # MODULE 3: GÓI ĐÀO
        if path == "/api/admin/packages":
            conn = sqlite3.connect(DB_FILE)
            c = conn.cursor()
            c.execute("SELECT id, user_id, user_name, package_name, price, quantity, daily_yield, status, created_at FROM packages ORDER BY id DESC")
            rows = c.fetchall()

            c.execute("SELECT COALESCE(SUM(quantity), 0), COALESCE(SUM(price * quantity), 0) FROM packages")
            stats = c.fetchone()
            conn.close()

            pkgs = [{
                "id": r[0], "userId": r[1], "userName": r[2], "packageName": r[3],
                "price": round(r[4], 2), "quantity": r[5], "dailyYield": round(r[6], 2),
                "status": r[7], "createdAt": r[8]
            } for r in rows]

            self.send_json(200, {
                "success": True,
                "currentPackagePrice": 10.0,
                "totalPackagesSold": stats[0],
                "totalPackageRevenue": round(stats[1], 2),
                "packages": pkgs
            })
            return

        # MODULE 4: NẠP TIỀN
        if path == "/api/admin/deposits":
            conn = sqlite3.connect(DB_FILE)
            c = conn.cursor()
            c.execute("""
                SELECT id, user_id, user_name, txid, network, token_symbol,
                       from_address, to_address, amount, block_number,
                       confirmations, status, error_reason, created_at
                FROM deposits
                ORDER BY id DESC
            """)
            rows = c.fetchall()
            c.execute("SELECT COALESCE(SUM(amount), 0), COUNT(id) FROM deposits WHERE status = 'COMPLETED'")
            stats = c.fetchone()
            conn.close()

            deposits_list = [{
                "id": r[0], "userId": r[1], "userName": r[2], "txid": r[3],
                "network": r[4], "tokenSymbol": r[5], "fromAddress": r[6], "toAddress": r[7],
                "amount": round(r[8], 4), "blockNumber": r[9], "confirmations": r[10],
                "status": r[11], "errorReason": r[12], "createdAt": r[13]
            } for r in rows]

            self.send_json(200, {
                "success": True,
                "stats": {"totalUsdt": round(stats[0], 2), "completedCount": stats[1], "adminWallet": ADMIN_WALLET_ADDRESS},
                "deposits": deposits_list
            })
            return

        # MODULE 5: RÚT TIỀN
        if path == "/api/admin/withdrawals":
            conn = sqlite3.connect(DB_FILE)
            c = conn.cursor()
            c.execute("""
                SELECT id, user_id, user_name, amount, fee, net_amount,
                       to_address, txid, block_number, status, reject_reason,
                       admin_approver, approved_at, created_at
                FROM withdrawals
                ORDER BY id DESC
            """)
            rows = c.fetchall()

            c.execute("SELECT COUNT(id) FROM withdrawals WHERE status = 'PENDING'")
            pending_count = c.fetchone()[0]
            c.execute("SELECT COALESCE(SUM(amount), 0), COUNT(id) FROM withdrawals WHERE status = 'COMPLETED'")
            completed_stats = c.fetchone()
            conn.close()

            withdrawals_list = [{
                "id": r[0], "userId": r[1], "userName": r[2],
                "amount": round(r[3], 2), "fee": round(r[4], 2), "netAmount": round(r[5], 2),
                "toAddress": r[6], "txid": r[7], "blockNumber": r[8],
                "status": r[9], "rejectReason": r[10],
                "adminApprover": r[11], "approvedAt": r[12], "createdAt": r[13]
            } for r in rows]

            bnb_bal, usdt_bal = get_admin_onchain_balances()
            self.send_json(200, {
                "success": True,
                "stats": {
                    "pendingCount": pending_count,
                    "completedCount": completed_stats[1],
                    "totalWithdrawn": round(completed_stats[0], 2),
                    "adminBnbBalance": round(bnb_bal, 6),
                    "adminUsdtBalance": round(usdt_bal, 2),
                    "adminWallet": ADMIN_WALLET_ADDRESS
                },
                "withdrawals": withdrawals_list
            })
            return

        # MODULE 6: WFI TOKENOMICS
        if path == "/api/admin/wfi":
            conn = sqlite3.connect(DB_FILE)
            c = conn.cursor()
            c.execute("SELECT COALESCE(SUM(wfi_balance), 0) FROM users")
            users_wfi = round(c.fetchone()[0], 2)

            c.execute("SELECT COALESCE(SUM(amount), 0) FROM transactions WHERE type = 'SWAP'")
            swapped_wfi = round(c.fetchone()[0], 2)

            c.execute("SELECT COALESCE(SUM(daily_yield), 0) FROM packages WHERE status = 'ACTIVE'")
            daily_mined = round(c.fetchone()[0], 2)
            conn.close()

            total_supply = 100000000.0 # 100 triệu WFI
            total_mined = users_wfi + swapped_wfi

            self.send_json(200, {
                "success": True,
                "tokenomics": {
                    "tokenName": "WFI Network Token",
                    "symbol": "WFI",
                    "totalSupply": total_supply,
                    "circulatingSupply": total_mined,
                    "usersHoldingWfi": users_wfi,
                    "wfiMinedAllTime": total_mined,
                    "wfiMinedDaily": daily_mined,
                    "wfiSwappedToUsdt": swapped_wfi,
                    "exchangeRate": 0.01
                }
            })
            return

        # MODULE 7: TOÀN BỘ GIAO DỊCH (LEDGER)
        if path == "/api/admin/transactions":
            conn = sqlite3.connect(DB_FILE)
            c = conn.cursor()
            c.execute("SELECT id, user_id, user_name, type, amount, token, fee, status, txid, note, created_at FROM transactions ORDER BY id DESC")
            rows = c.fetchall()
            conn.close()

            txs = [{
                "id": r[0], "userId": r[1], "userName": r[2], "type": r[3],
                "amount": round(r[4], 2), "token": r[5], "fee": round(r[6] or 0.0, 2),
                "status": r[7], "txid": r[8], "note": r[9], "createdAt": r[10]
            } for r in rows]
            self.send_json(200, {"success": True, "transactions": txs})
            return

        # MODULE 8: DOANH THU
        if path == "/api/admin/revenue":
            conn = sqlite3.connect(DB_FILE)
            c = conn.cursor()
            c.execute("SELECT COALESCE(SUM(price * quantity), 0) FROM packages")
            pkg_rev = round(c.fetchone()[0], 2)

            c.execute("SELECT COALESCE(SUM(fee), 0) FROM withdrawals WHERE status = 'COMPLETED'")
            fee_rev = round(c.fetchone()[0], 2)
            conn.close()

            total_rev = pkg_rev + fee_rev
            self.send_json(200, {
                "success": True,
                "revenue": {
                    "totalRevenue": total_rev,
                    "todayRevenue": round(total_rev * 0.12, 2),
                    "monthRevenue": round(total_rev * 0.75, 2),
                    "packageRevenue": pkg_rev,
                    "transactionFeeRevenue": fee_rev
                }
            })
            return

        # MODULE 9: HỖ TRỢ (TICKETS)
        if path == "/api/admin/tickets":
            conn = sqlite3.connect(DB_FILE)
            c = conn.cursor()
            c.execute("SELECT id, user_id, user_name, subject, message, reply, status, created_at FROM support_tickets ORDER BY id DESC")
            rows = c.fetchall()
            conn.close()

            tickets = [{
                "id": r[0], "userId": r[1], "userName": r[2], "subject": r[3],
                "message": r[4], "reply": r[5], "status": r[6], "createdAt": r[7]
            } for r in rows]
            self.send_json(200, {"success": True, "tickets": tickets})
            return

        # MODULE 10: CẤU HÌNH HỆ THỐNG
        if path == "/api/admin/settings":
            conn = sqlite3.connect(DB_FILE)
            c = conn.cursor()
            c.execute("SELECT key, value, description, updated_at FROM system_settings")
            rows = c.fetchall()
            conn.close()

            settings = {r[0]: {"value": r[1], "description": r[2], "updatedAt": r[3]} for r in rows}
            bnb_bal, usdt_bal = get_admin_onchain_balances()

            self.send_json(200, {
                "success": True,
                "settings": settings,
                "onchain": {
                    "adminWallet": ADMIN_WALLET_ADDRESS,
                    "usdtContract": BSC_USDT_CONTRACT,
                    "bnbBalance": round(bnb_bal, 6),
                    "usdtBalance": round(usdt_bal, 2)
                }
            })
            return

        # MODULE 11: ADMIN & PHÂN QUYỀN + NHẬT KÝ
        if path == "/api/admin/admins":
            conn = sqlite3.connect(DB_FILE)
            c = conn.cursor()
            c.execute("SELECT id, username, name, email, role, status, last_login FROM admin_users ORDER BY id ASC")
            rows = c.fetchall()
            c.execute("SELECT id, admin_name, action, target, ip, created_at FROM admin_logs ORDER BY id DESC LIMIT 50")
            log_rows = c.fetchall()
            conn.close()

            admins = [{
                "id": r[0], "username": r[1], "name": r[2], "email": r[3],
                "role": r[4], "status": r[5], "lastLogin": r[6]
            } for r in rows]

            logs = [{
                "id": r[0], "adminName": r[1], "action": r[2], "target": r[3],
                "ip": r[4], "createdAt": r[5]
            } for r in log_rows]

            self.send_json(200, {"success": True, "admins": admins, "logs": logs})
            return

        # Client histories
        if path == "/api/user/deposits":
            conn = sqlite3.connect(DB_FILE)
            c = conn.cursor()
            c.execute("SELECT id, txid, amount, from_address, block_number, status, created_at FROM deposits WHERE user_id = 'user_default' ORDER BY id DESC LIMIT 10")
            rows = c.fetchall()
            conn.close()
            history = [{"id": r[0], "txid": r[1], "amount": round(r[2], 2), "fromAddress": r[3], "blockNumber": r[4], "status": r[5], "createdAt": r[6]} for r in rows]
            self.send_json(200, {"success": True, "deposits": history})
            return

        if path == "/api/user/withdrawals":
            conn = sqlite3.connect(DB_FILE)
            c = conn.cursor()
            c.execute("SELECT id, amount, fee, net_amount, to_address, txid, block_number, status, reject_reason, created_at FROM withdrawals WHERE user_id = 'user_default' ORDER BY id DESC LIMIT 10")
            rows = c.fetchall()
            conn.close()
            history = [{"id": r[0], "amount": round(r[1], 2), "fee": round(r[2], 2), "netAmount": round(r[3], 2), "toAddress": r[4], "txid": r[5], "blockNumber": r[6], "status": r[7], "rejectReason": r[8], "createdAt": r[9]} for r in rows]
            self.send_json(200, {"success": True, "withdrawals": history})
            return

        # API TOÀN BỘ LỊCH SỬ GIAO DỊCH CỦA KHÁCH HÀNG
        if path == "/api/user/transactions":
            conn = sqlite3.connect(DB_FILE)
            c = conn.cursor()
            c.execute("""
                SELECT id, type, amount, token, fee, status, txid, note, created_at
                FROM transactions
                WHERE user_id = 'user_default'
                ORDER BY id DESC LIMIT 50
            """)
            rows = c.fetchall()
            conn.close()
            tx_list = [{
                "id": r[0],
                "type": r[1].lower(),
                "amount": f"{r[2]:,.2f}".replace(",", "X").replace(".", ",").replace("X", "."),
                "token": r[3],
                "fee": r[4],
                "status": r[5],
                "txid": r[6],
                "note": r[7],
                "time": r[8],
                "created_at": r[8]
            } for r in rows]
            self.send_json(200, {"success": True, "transactions": tx_list})
            return

        # ======================================================================
        # TRANG BẢNG XẾP HẠNG (WEEKLY WFI MINING LEADERBOARD)
        # ======================================================================
        if path == "/api/leaderboard":
            conn = sqlite3.connect(DB_FILE)
            c = conn.cursor()

            # Tự động đồng bộ số WFI đào từ các gói đào thực tế
            sync_weekly_wfi_mining_from_packages(c)

            # Tự động kiểm tra và chốt tuần nếu đã hết giờ
            settle_res = check_and_settle_weekly_leaderboard(c, force=False)
            conn.commit()

            week_num, round_end = get_or_create_leaderboard_round(c)
            now_ts = int(time.time())
            seconds_remaining = max(0, round_end - now_ts)

            # Lấy Top 100 người khai thác WFI nhiều nhất tuần này (từ dữ liệu thực tế)
            c.execute("""
                SELECT u.id, u.name, COALESCE(u.weekly_wfi_mined, 0.0),
                       (SELECT COUNT(p.id) FROM packages p WHERE p.user_id = u.id AND p.status = 'ACTIVE') as active_pkgs
                FROM users u
                ORDER BY u.weekly_wfi_mined DESC, u.id ASC
                LIMIT 100
            """)
            top100_rows = c.fetchall()

            top100 = []
            TEAM_NAMES = [
                "Đội Alpha WFI", "Đội Node Sài Gòn", "Đội Hà Nội Miners",
                "Đội Crypto VIP", "Đội Phoenix", "Đội Dragon Node",
                "Đội Binance BSC", "Đội Cyber Mining", "Đội Apex Star", "Đội Golden Hash"
            ]
            for rank_idx, r in enumerate(top100_rows, 1):
                reward_amt = WEEKLY_REWARDS.get(rank_idx, 0.0)
                assigned_team = TEAM_NAMES[(hash(r[0]) % len(TEAM_NAMES)) if r[0] else (rank_idx % len(TEAM_NAMES))]
                top100.append({
                    "rank": rank_idx,
                    "userId": r[0],
                    "userName": r[1],
                    "team": assigned_team,
                    "weeklyWfiMined": round(r[2], 2),
                    "reward": reward_amt,
                    "activePackages": r[3]
                })

            top10 = top100[:10]

            # Lấy vị trí thứ hạng của user_default
            c.execute("""
                SELECT COUNT(id) + 1
                FROM users
                WHERE weekly_wfi_mined > (SELECT COALESCE(weekly_wfi_mined, 0.0) FROM users WHERE id = 'user_default')
            """)
            curr_user_rank = c.fetchone()[0]

            c.execute("SELECT weekly_wfi_mined FROM users WHERE id = 'user_default'")
            curr_user_wfi = c.fetchone()[0] or 0.0

            # Lấy lịch sử Top 3 các tuần trước
            c.execute("""
                SELECT id, week_number, start_date, end_date,
                       rank1_user_name, rank1_wfi, rank1_reward,
                       rank2_user_name, rank2_wfi, rank2_reward,
                       rank3_user_name, rank3_wfi, rank3_reward,
                       settled_at
                FROM weekly_leaderboard_history
                ORDER BY week_number DESC
                LIMIT 8
            """)
            hist_rows = c.fetchall()
            history = [{
                "id": hr[0],
                "weekNumber": hr[1],
                "startDate": hr[2],
                "endDate": hr[3],
                "rank1": {"name": hr[4], "wfi": hr[5], "reward": hr[6]},
                "rank2": {"name": hr[7], "wfi": hr[8], "reward": hr[9]},
                "rank3": {"name": hr[10], "wfi": hr[11], "reward": hr[12]},
                "settledAt": hr[13]
            } for hr in hist_rows]

            conn.close()

            self.send_json(200, {
                "success": True,
                "weekNumber": week_num,
                "roundEndTime": round_end,
                "secondsRemaining": seconds_remaining,
                "rewards": {
                    "top1": 1000.0,
                    "top2": 500.0,
                    "top3": 250.0
                },
                "top100": top100,
                "top10": top10,
                "currentUser": {
                    "userId": "user_default",
                    "userName": "Đặng Hùng",
                    "rank": curr_user_rank,
                    "weeklyWfiMined": round(curr_user_wfi, 2)
                },
                "history": history
            })
            return

        if path == "/api/admin/leaderboard/history":
            conn = sqlite3.connect(DB_FILE)
            c = conn.cursor()
            c.execute("""
                SELECT id, week_number, start_date, end_date,
                       rank1_user_id, rank1_user_name, rank1_wfi, rank1_reward,
                       rank2_user_id, rank2_user_name, rank2_wfi, rank2_reward,
                       rank3_user_id, rank3_user_name, rank3_wfi, rank3_reward,
                       total_participants, settled_at
                FROM weekly_leaderboard_history
                ORDER BY week_number DESC
            """)
            rows = c.fetchall()
            conn.close()

            history = [{
                "id": r[0], "weekNumber": r[1], "startDate": r[2], "endDate": r[3],
                "rank1": {"userId": r[4], "name": r[5], "wfi": r[6], "reward": r[7]},
                "rank2": {"userId": r[8], "name": r[9], "wfi": r[10], "reward": r[11]},
                "rank3": {"userId": r[12], "name": r[13], "wfi": r[14], "reward": r[15]},
                "totalParticipants": r[16], "settledAt": r[17]
            } for r in rows]

            self.send_json(200, {"success": True, "history": history})
            return

        # ----------------------------------------------------------------------
        # TRANG VÒNG QUAY MAY MẮN (LUCKY DRAW) - STATUS
        # ----------------------------------------------------------------------
        if path == "/api/wheel/status":
            user_id = query_params.get("userId", ["user_default"])[0] if "query_params" in locals() else "user_default"
            # Parse query params if needed
            if "?" in self.path:
                try:
                    import urllib.parse
                    parsed = urllib.parse.parse_qs(self.path.split("?", 1)[1])
                    user_id = parsed.get("userId", ["user_default"])[0]
                except Exception:
                    pass

            conn = sqlite3.connect(DB_FILE)
            c = conn.cursor()
            c.execute("SELECT lucky_spins, wfi_balance, usdt_balance FROM users WHERE id = ?", (user_id,))
            u_row = c.fetchone()
            spins = int(u_row[0] or 0) if u_row else 3
            wfi_bal = float(u_row[1] or 0.0) if u_row else 0.0
            usdt_bal = float(u_row[2] or 0.0) if u_row else 0.0

            # Lấy danh sách trúng gần nhất
            c.execute("SELECT user_name, reward_amount, created_at FROM lucky_draws ORDER BY id DESC LIMIT 15")
            rec_rows = c.fetchall()
            recent_winners = [{"user": r[0], "amount": r[1], "time": r[2]} for r in rec_rows]

            # Lịch sử riêng của người dùng
            c.execute("SELECT reward_amount, created_at FROM lucky_draws WHERE user_id = ? ORDER BY id DESC LIMIT 20", (user_id,))
            my_rows = c.fetchall()
            my_history = [{"amount": r[0], "time": r[1]} for r in my_rows]
            conn.close()

            self.send_json(200, {
                "success": True,
                "spins": spins,
                "wfiBalance": round(wfi_bal, 2),
                "usdtBalance": round(usdt_bal, 2),
                "costPerSpinUsdt": 0.5,
                "rewards": [30.0, 0.0, 5.0, 10.0, 15.0, 20.0],
                "recentWinners": recent_winners,
                "userHistory": my_history
            })
            return

        # ----------------------------------------------------------------------
        # MKT DEMO: LẤY LỊCH SỬ THÔNG BÁO DEMO CỦA TÀI KHOẢN MKT (RBAC BACKEND)
        # ----------------------------------------------------------------------
        if path == "/api/mkt/history":
            import urllib.parse
            user_id = "user_default"
            if "?" in self.path:
                try:
                    parsed = urllib.parse.parse_qs(self.path.split("?", 1)[1])
                    user_id = parsed.get("userId", ["user_default"])[0]
                except Exception:
                    pass

            conn = sqlite3.connect(DB_FILE)
            c = conn.cursor()
            c.execute("SELECT role, is_locked FROM users WHERE id = ?", (user_id,))
            u = c.fetchone()
            if not u or u[0] != "MKT":
                conn.close()
                self.send_json(403, {"success": False, "message": "Truy cập bị từ chối: Chỉ tài khoản MKT mới có quyền truy cập chức năng này."})
                return

            c.execute("""
                SELECT id, amount, to_address, title, body, status, category, virtual_flag, scheduled_at, delivered_at, created_at
                FROM mkt_demo_notifications
                WHERE user_id = ?
                ORDER BY id DESC
                LIMIT 50
            """, (user_id,))
            rows = c.fetchall()
            conn.close()

            history = [{
                "id": r[0],
                "amount": r[1],
                "toAddress": r[2],
                "title": r[3],
                "body": r[4],
                "status": r[5],
                "category": r[6],
                "virtualFlag": r[7],
                "scheduledAt": r[8],
                "deliveredAt": r[9],
                "createdAt": r[10]
            } for r in rows]

            self.send_json(200, {"success": True, "history": history})
            return

        # ----------------------------------------------------------------------
        # MKT DEMO: POLLING THÔNG BÁO TỚI HẠN (~5 GIÂY) ĐỂ KÍCH HOẠT PUSH BANNER
        # ----------------------------------------------------------------------
        if path == "/api/mkt/poll-notifications":
            import urllib.parse
            user_id = "user_default"
            if "?" in self.path:
                try:
                    parsed = urllib.parse.parse_qs(self.path.split("?", 1)[1])
                    user_id = parsed.get("userId", ["user_default"])[0]
                except Exception:
                    pass

            conn = sqlite3.connect(DB_FILE, timeout=10)
            c = conn.cursor()
            c.execute("SELECT role, is_locked FROM users WHERE id = ?", (user_id,))
            u = c.fetchone()
            if not u or u[0] != "MKT":
                conn.close()
                self.send_json(403, {"success": False, "message": "Truy cập bị từ chối: Chỉ tài khoản MKT mới có quyền."})
                return

            now_ts = int(time.time())
            c.execute("""
                SELECT id, amount, to_address, title, body, scheduled_at, delivered_at, status
                FROM mkt_demo_notifications
                WHERE user_id = ? AND delivered_at <= ? AND status = 'PENDING'
                ORDER BY id ASC
            """, (user_id, now_ts))
            rows = c.fetchall()

            ready_notifications = []
            if rows:
                ids_to_update = [r[0] for r in rows]
                for r in rows:
                    ready_notifications.append({
                        "id": r[0],
                        "amount": r[1],
                        "toAddress": r[2],
                        "title": r[3],
                        "body": r[4],
                        "scheduledAt": r[5],
                        "deliveredAt": r[6],
                        "status": "DELIVERED",
                        "category": "MKT_DEMO"
                    })
                # Đánh dấu đã gửi
                q_marks = ",".join("?" for _ in ids_to_update)
                c.execute(f"UPDATE mkt_demo_notifications SET status = 'DELIVERED' WHERE id IN ({q_marks})", ids_to_update)
                conn.commit()

            conn.close()
            self.send_json(200, {"success": True, "notifications": ready_notifications, "serverTime": now_ts})
            return

        # ----------------------------------------------------------------------
        # ADMIN: DANH SÁCH TÀI KHOẢN MKT (TÁCH BIỆT CRM)
        # ----------------------------------------------------------------------
        if path == "/api/admin/mkt/list":
            conn = sqlite3.connect(DB_FILE)
            c = conn.cursor()
            c.execute("""
                SELECT id, name, email, phone, tier, is_locked, created_at
                FROM users
                WHERE role = 'MKT'
                ORDER BY created_at DESC
            """)
            rows = c.fetchall()
            conn.close()

            mkt_users = [{
                "id": r[0],
                "name": r[1],
                "email": r[2],
                "phone": r[3],
                "tier": r[4],
                "isLocked": bool(r[5]),
                "createdAt": r[6]
            } for r in rows]

            self.send_json(200, {"success": True, "mktUsers": mkt_users})
            return

        # ----------------------------------------------------------------------
        # ADMIN: XEM TOÀN BỘ LỊCH SỬ THÔNG BÁO DEMO (TÁCH BIỆT VỚI WITHDRAWALS THẬT)
        # ----------------------------------------------------------------------
        if path == "/api/admin/mkt/demo-history":
            conn = sqlite3.connect(DB_FILE)
            c = conn.cursor()
            c.execute("""
                SELECT id, user_id, email, amount, to_address, title, body, status, category, virtual_flag, scheduled_at, delivered_at, created_at
                FROM mkt_demo_notifications
                ORDER BY id DESC
                LIMIT 100
            """)
            rows = c.fetchall()
            conn.close()

            history = [{
                "id": r[0],
                "userId": r[1],
                "email": r[2],
                "amount": r[3],
                "toAddress": r[4],
                "title": r[5],
                "body": r[6],
                "status": r[7],
                "category": r[8],
                "virtualFlag": r[9],
                "scheduledAt": r[10],
                "deliveredAt": r[11],
                "createdAt": r[12]
            } for r in rows]

            self.send_json(200, {"success": True, "history": history})
            return

        # ----------------------------------------------------------------------
        # ADMIN: LẤY CẤU HÌNH TIÊU ĐỀ, NỘI DUNG, LOGO NOTIFICATION MKT
        # ----------------------------------------------------------------------
        if path == "/api/admin/mkt/config":
            conn = sqlite3.connect(DB_FILE)
            c = conn.cursor()
            c.execute("SELECT title, body_template, delay_seconds, icon_url, updated_at FROM mkt_notification_config WHERE id = 1")
            row = c.fetchone()
            conn.close()
            if row:
                self.send_json(200, {
                    "success": True,
                    "config": {
                        "title": row[0],
                        "bodyTemplate": row[1],
                        "delaySeconds": row[2],
                        "iconUrl": row[3] or "",
                        "updatedAt": row[4]
                    }
                })
            else:
                self.send_json(200, {
                    "success": True,
                    "config": {
                        "title": "Thông báo rút tiền USDT (BEP-20)",
                        "bodyTemplate": "Lệnh rút {amount} USDT về ví {short_address} đã được xác nhận thành công trên mạng BSC.",
                        "delaySeconds": 5,
                        "iconUrl": "",
                        "updatedAt": None
                    }
                })
            return

        return super().do_GET()

    def do_POST(self):
        path = self.path.split("?")[0]
        content_length = int(self.headers.get("Content-Length", 0))
        body_bytes = self.rfile.read(content_length)

        try:
            data = json.loads(body_bytes.decode("utf-8")) if body_bytes else {}
        except Exception:
            self.send_json(400, {"success": False, "message": "Dữ liệu JSON không hợp lệ"})
            return

        # ----------------------------------------------------------------------
        # TRANG VÒNG QUAY MAY MẮN (LUCKY DRAW) - QUAY THƯỞNG
        # ----------------------------------------------------------------------
        if path == "/api/wheel/spin":
            user_id = data.get("userId") or "user_default"
            conn = sqlite3.connect(DB_FILE, timeout=10)
            c = conn.cursor()
            c.execute("SELECT name, lucky_spins, wfi_balance FROM users WHERE id = ?", (user_id,))
            user = c.fetchone()
            if not user:
                conn.close()
                self.send_json(404, {"success": False, "message": "Không tìm thấy người dùng"})
                return

            u_name, spins, wfi_bal = user
            spins = int(spins or 0)
            if spins <= 0:
                conn.close()
                self.send_json(400, {"success": False, "message": "Bạn đã hết lượt quay. Hãy mua thêm lượt!"})
                return

            # Xác suất trúng thưởng (6 ô tương ứng ảnh 1: 30, 0, 5, 10, 15, 20)
            # Index 0: 30 (3%), Index 1: 0 (12%), Index 2: 5 (40%), Index 3: 10 (25%), Index 4: 15 (12%), Index 5: 20 (8%)
            import random
            rewards_list = [30.0, 0.0, 5.0, 10.0, 15.0, 20.0]
            weights = [3, 12, 40, 25, 12, 8]
            chosen_idx = random.choices(range(len(rewards_list)), weights=weights, k=1)[0]
            reward_amt = rewards_list[chosen_idx]

            new_spins = spins - 1
            new_wfi = round(float(wfi_bal or 0.0) + reward_amt, 2)

            c.execute("UPDATE users SET lucky_spins = ?, wfi_balance = ? WHERE id = ?", (new_spins, new_wfi, user_id))
            c.execute("INSERT INTO lucky_draws (user_id, user_name, reward_amount) VALUES (?, ?, ?)", (user_id, u_name, reward_amt))
            if reward_amt > 0:
                c.execute("""
                    INSERT INTO transactions (user_id, user_name, type, amount, token, status, note)
                    VALUES (?, ?, 'LUCKY_DRAW', ?, 'WFI', 'COMPLETED', ?)
                """, (user_id, u_name, reward_amt, f"Trúng thưởng Vòng quay may mắn (+{reward_amt} WFI)"))

            conn.commit()
            conn.close()

            self.send_json(200, {
                "success": True,
                "rewardIndex": chosen_idx,
                "rewardAmount": reward_amt,
                "remainingSpins": new_spins,
                "newWfiBalance": new_wfi,
                "message": f"Chúc mừng bạn trúng +{reward_amt:.2f} WFI!" if reward_amt > 0 else "Chúc bạn may mắn lần sau!"
            })
            return

        # ----------------------------------------------------------------------
        # TRANG VÒNG QUAY MAY MẮN (LUCKY DRAW) - MUA LƯỢT QUAY BẰNG USDT
        # ----------------------------------------------------------------------
        if path == "/api/wheel/buy":
            user_id = data.get("userId") or "user_default"
            package_spins = int(data.get("spins") or 3) # Mặc định gói 3 lượt = 1.0 USDT
            cost_usdt = round(float(data.get("cost") or 1.0), 2)

            conn = sqlite3.connect(DB_FILE, timeout=10)
            c = conn.cursor()
            c.execute("SELECT name, usdt_balance, lucky_spins FROM users WHERE id = ?", (user_id,))
            user = c.fetchone()
            if not user:
                conn.close()
                self.send_json(404, {"success": False, "message": "Không tìm thấy người dùng"})
                return

            u_name, usdt_bal, cur_spins = user
            usdt_bal = float(usdt_bal or 0.0)
            cur_spins = int(cur_spins or 0)

            if usdt_bal < cost_usdt:
                conn.close()
                self.send_json(400, {"success": False, "message": f"Số dư USDT không đủ ({usdt_bal:.2f} USDT). Cần {cost_usdt:.2f} USDT để mua {package_spins} lượt."})
                return

            new_usdt = round(usdt_bal - cost_usdt, 2)
            new_spins = cur_spins + package_spins

            c.execute("UPDATE users SET usdt_balance = ?, lucky_spins = ? WHERE id = ?", (new_usdt, new_spins, user_id))
            c.execute("""
                INSERT INTO transactions (user_id, user_name, type, amount, token, status, note)
                VALUES (?, ?, 'BUY_SPINS', ?, 'USDT', 'COMPLETED', ?)
            """, (user_id, u_name, cost_usdt, f"Mua {package_spins} lượt quay Vòng quay may mắn"))
            conn.commit()
            conn.close()

            self.send_json(200, {
                "success": True,
                "remainingSpins": new_spins,
                "newUsdtBalance": new_usdt,
                "message": f"Mua thành công {package_spins} lượt quay may mắn!"
            })
            return

        # ----------------------------------------------------------------------
        # 0. CLAIM WFI THEO CHU KỲ 24 GIỜ
        # ----------------------------------------------------------------------
        if path == "/api/mining/claim":
            user_id = "user_default"
            CYCLE = 86400
            conn = sqlite3.connect(DB_FILE)
            c = conn.cursor()
            c.execute("SELECT name, last_claim_at FROM users WHERE id = ?", (user_id,))
            u = c.fetchone()
            if not u:
                conn.close()
                self.send_json(404, {"success": False, "message": "Không tìm thấy user"})
                return
            now_ts = int(time.time())
            cycle_start = int(u[1] or now_ts)
            elapsed = now_ts - cycle_start
            if elapsed < CYCLE:
                conn.close()
                self.send_json(400, {
                    "success": False,
                    "message": "Chưa đủ chu kỳ 24 giờ để Claim",
                    "secondsRemaining": CYCLE - elapsed
                })
                return
            c.execute("SELECT COALESCE(SUM(quantity), 0) FROM packages WHERE user_id = ? AND status = 'ACTIVE'", (user_id,))
            active_qty = int(c.fetchone()[0] or 0)
            amount = round(active_qty * 5000.0, 2)  # Sản lượng đủ 1 chu kỳ 24h
            c.execute("""
                UPDATE users SET
                    wfi_balance = wfi_balance + ?,
                    weekly_wfi_mined = COALESCE(weekly_wfi_mined, 0) + ?,
                    total_wfi_mined = COALESCE(total_wfi_mined, 0) + ?,
                    last_claim_at = ?,
                    last_claim_amount = ?
                WHERE id = ?
            """, (amount, amount, amount, now_ts, amount, user_id))
            if amount > 0:
                c.execute("""
                    INSERT INTO transactions (user_id, user_name, type, amount, token, status, note)
                    VALUES (?, ?, 'CLAIM', ?, 'WFI', 'COMPLETED', 'Claim WFI chu kỳ 24 giờ')
                """, (user_id, u[0], amount))
            conn.commit()
            c.execute("SELECT wfi_balance FROM users WHERE id = ?", (user_id,))
            new_bal = round(c.fetchone()[0], 2)
            conn.close()
            self.send_json(200, {
                "success": True,
                "claimedAmount": amount,
                "wfiBalance": new_bal,
                "cycleStartAt": now_ts,
                "claimCycleSeconds": CYCLE
            })
            return

        # ----------------------------------------------------------------------
        # A. KHÁCH KIỂM TRA NẠP TIỀN
        # ----------------------------------------------------------------------
        if path == "/api/deposit/verify":
            txid = (data.get("txid") or "").strip().lower()
            user_id = data.get("userId") or "user_default"
            if not txid:
                self.send_json(400, {"success": False, "message": "Vui lòng nhập mã giao dịch (TXID)"})
                return

            conn = sqlite3.connect(DB_FILE, timeout=10)
            c = conn.cursor()
            c.execute("SELECT id, status, amount FROM deposits WHERE LOWER(txid) = ?", (txid,))
            existing = c.fetchone()
            existing_id = None
            if existing:
                existing_id = existing[0]
                if existing[1] == "COMPLETED":
                    conn.close()
                    self.send_json(400, {"success": False, "code": "ALREADY_PROCESSED", "message": f"Mã giao dịch (TXID) này đã được xử lý trước đó (+{existing[2]:.2f} USDT)."})
                    return

            c.execute("SELECT name FROM users WHERE id = ?", (user_id,))
            u_row = c.fetchone()
            user_name = u_row[0] if u_row else "Khách hàng"

            verification = verify_bsc_deposit_tx(txid)
            if not verification.get("valid"):
                err_msg = verification.get("error", "Giao dịch không hợp lệ")
                try:
                    if existing_id:
                        c.execute("UPDATE deposits SET error_reason = ?, created_at = CURRENT_TIMESTAMP WHERE id = ?", (err_msg, existing_id))
                    else:
                        c.execute("INSERT INTO deposits (user_id, user_name, txid, token_contract, to_address, amount, status, error_reason) VALUES (?, ?, ?, ?, ?, 0, 'FAILED', ?)",
                                  (user_id, user_name, txid, BSC_USDT_CONTRACT, ADMIN_WALLET_ADDRESS, err_msg))
                    conn.commit()
                except Exception: pass
                conn.close()
                self.send_json(400, {"success": False, "code": "BLOCKCHAIN_VERIFICATION_FAILED", "message": err_msg})
                return

            amount = verification["amount"]
            from_address = verification["from_address"]
            to_address = verification["to_address"]
            block_number = verification["block_number"]
            confirmations = verification["confirmations"]

            try:
                if existing_id:
                    c.execute("""
                        UPDATE deposits SET network='BEP20', token_symbol='USDT', token_contract=?,
                               from_address=?, to_address=?, amount=?, block_number=?, confirmations=?,
                               status='COMPLETED', error_reason=NULL, created_at=CURRENT_TIMESTAMP
                        WHERE id = ?
                    """, (BSC_USDT_CONTRACT, from_address, to_address, amount, block_number, confirmations, existing_id))
                else:
                    c.execute("""
                        INSERT INTO deposits (user_id, user_name, txid, network, token_symbol, token_contract, from_address, to_address, amount, block_number, confirmations, status)
                        VALUES (?, ?, ?, 'BEP20', 'USDT', ?, ?, ?, ?, ?, ?, 'COMPLETED')
                    """, (user_id, user_name, txid, BSC_USDT_CONTRACT, from_address, to_address, amount, block_number, confirmations))

                c.execute("UPDATE users SET usdt_balance = usdt_balance + ? WHERE id = ?", (amount, user_id))
                c.execute("INSERT INTO transactions (user_id, user_name, type, amount, token, status, txid, note) VALUES (?, ?, 'DEPOSIT', ?, 'USDT', 'COMPLETED', ?, 'Nạp USDT BEP20 tự động')",
                          (user_id, user_name, amount, txid))
                c.execute("SELECT usdt_balance FROM users WHERE id = ?", (user_id,))
                new_bal = c.fetchone()[0]
                conn.commit()
            except Exception as e:
                conn.rollback()
                conn.close()
                self.send_json(500, {"success": False, "message": f"Lỗi hệ thống: {str(e)}"})
                return

            conn.close()
            self.send_json(200, {
                "success": True,
                "message": f"Nạp thành công! Đã tự động cộng {amount:.2f} USDT vào ví của bạn.",
                "data": {"txid": txid, "amount": amount, "fromAddress": from_address, "toAddress": to_address, "blockNumber": block_number, "newUsdtBalance": round(new_bal, 2)}
            })
            return

        # ----------------------------------------------------------------------
        # B. KHÁCH TẠO LỆNH RÚT TIỀN
        # ----------------------------------------------------------------------
        if path == "/api/withdraw/request":
            user_id = data.get("userId") or "user_default"
            to_address = (data.get("toAddress") or "").strip()
            amount = float(data.get("amount") or 0.0)

            if not re.match(r"^0x[a-fA-F0-9]{40}$", to_address):
                self.send_json(400, {"success": False, "message": "Địa chỉ ví nhận BEP20 không hợp lệ (phải bắt đầu bằng 0x gồm 42 ký tự)."})
                return

            if to_address.lower() == ADMIN_WALLET_ADDRESS.lower():
                self.send_json(400, {"success": False, "message": "Không thể rút về chính ví Admin."})
                return

            if amount < MIN_WITHDRAW_USDT:
                self.send_json(400, {"success": False, "message": f"Số lượng rút tối thiểu là {MIN_WITHDRAW_USDT:.2f} USDT."})
                return

            fee = WITHDRAW_FEE_USDT
            net_amount = amount - fee
            if net_amount <= 0:
                self.send_json(400, {"success": False, "message": "Số tiền rút phải lớn hơn phí mạng."})
                return

            conn = sqlite3.connect(DB_FILE, timeout=10)
            c = conn.cursor()
            try:
                c.execute("SELECT name, usdt_balance, locked_usdt, is_locked, role, email FROM users WHERE id = ?", (user_id,))
                user = c.fetchone()
                if not user:
                    conn.close()
                    self.send_json(404, {"success": False, "message": "Không tìm thấy user."})
                    return
                if user[3]:
                    conn.close()
                    self.send_json(403, {"success": False, "message": "Tài khoản của bạn đã bị tạm khóa. Vui lòng liên hệ hỗ trợ."})
                    return

                u_name, tot_bal, loc_bal = user[0], user[1], user[2] or 0.0
                u_role = user[4] or "CUSTOMER"
                u_email = user[5] or "mkt@gmail.com"
                is_mkt_user = (u_role == "MKT")

                avail = tot_bal - loc_bal
                # Nếu là tài khoản MKT test và số dư không đủ, tự động cấp thêm số dư test để không làm gián đoạn
                if is_mkt_user and avail < amount:
                    needed = amount - avail + 500.0
                    c.execute("UPDATE users SET usdt_balance = usdt_balance + ? WHERE id = ?", (needed, user_id))
                    tot_bal += needed
                    avail += needed

                if avail < amount:
                    conn.close()
                    self.send_json(400, {"success": False, "message": f"Số dư khả dụng ({avail:.2f} USDT) không đủ để rút {amount:.2f} USDT."})
                    return

                c.execute("UPDATE users SET locked_usdt = locked_usdt + ? WHERE id = ? AND (usdt_balance - locked_usdt) >= ?", (amount, user_id, amount))
                if c.rowcount == 0:
                    conn.rollback()
                    conn.close()
                    self.send_json(400, {"success": False, "message": "Số dư khả dụng vừa thay đổi."})
                    return

                # Giữ nguyên toàn bộ chức năng rút tiền hiện tại
                c.execute("INSERT INTO withdrawals (user_id, user_name, amount, fee, net_amount, to_address, status) VALUES (?, ?, ?, ?, ?, ?, 'PENDING')",
                          (user_id, u_name, amount, fee, net_amount, to_address))
                wid = c.lastrowid

                # NẾU LÀ TÀI KHOẢN MKT: HỆ THỐNG CÓ THÊM PHẦN GỬI NOTIFICATION THEO CẤU HÌNH ADMIN (KHÔNG HARD-CODE)
                notif_info = None
                if is_mkt_user:
                    c.execute("SELECT title, body_template, delay_seconds, icon_url FROM mkt_notification_config WHERE id = 1")
                    cfg_row = c.fetchone()
                    cfg_title = cfg_row[0] if cfg_row else "Thông báo rút tiền USDT (BEP-20)"
                    cfg_template = cfg_row[1] if cfg_row else "Lệnh rút {amount} USDT về ví {short_address} đã được xác nhận thành công trên mạng BSC."
                    delay_sec = int(cfg_row[2]) if cfg_row else 5
                    cfg_icon = (cfg_row[3] or "") if cfg_row else ""

                    # Định dạng các biến thay thế động
                    short_addr = to_address[:6] + "..." + to_address[-4:] if len(to_address) > 10 else to_address
                    time_str = datetime.datetime.now().strftime("%H:%M:%S")
                    amount_vn = f"{amount:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")
                    net_vn = f"{net_amount:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")

                    final_title = cfg_title.replace("{amount}", amount_vn).replace("{short_address}", short_addr).replace("{address}", to_address).replace("{time}", time_str)
                    final_body = cfg_template.replace("{amount}", amount_vn).replace("{net_amount}", net_vn).replace("{short_address}", short_addr).replace("{address}", to_address).replace("{time}", time_str)

                    now_ts = int(time.time())
                    scheduled_ts = now_ts + delay_sec

                    # Lưu vào bảng demo notification để lưu vết CRM và đồng bộ
                    c.execute("""
                        INSERT INTO mkt_demo_notifications (user_id, email, amount, to_address, title, body, status, category, virtual_flag, scheduled_at, delivered_at)
                        VALUES (?, ?, ?, ?, ?, ?, 'DELIVERED', 'MKT_WITHDRAW_NOTIF', 'VIRTUAL_NOTIFICATION', ?, ?)
                    """, (user_id, u_email, amount, to_address, final_title, final_body, scheduled_ts, scheduled_ts))

                    notif_info = {
                        "delaySeconds": delay_sec,
                        "title": final_title,
                        "body": final_body,
                        "iconUrl": cfg_icon,
                        "amount": amount,
                        "toAddress": to_address,
                        "shortAddress": short_addr
                    }

                conn.commit()

                c.execute("SELECT usdt_balance, locked_usdt FROM users WHERE id = ?", (user_id,))
                up_row = c.fetchone()
                conn.close()

                resp_payload = {
                    "success": True,
                    "message": f"Tạo lệnh rút {amount:.2f} USDT thành công. Lệnh đang chờ Admin phê duyệt.",
                    "data": {
                        "orderId": wid, "amount": amount, "fee": fee, "netAmount": net_amount, "toAddress": to_address, "status": "PENDING",
                        "availableBalance": round(up_row[0] - (up_row[1] or 0.0), 2), "lockedBalance": round(up_row[1] or 0.0, 2)
                    },
                    "isMkt": is_mkt_user
                }
                if notif_info:
                    resp_payload["mktNotification"] = notif_info

                self.send_json(200, resp_payload)
                return
            except Exception as e:
                conn.rollback()
                conn.close()
                self.send_json(500, {"success": False, "message": f"Lỗi: {str(e)}"})
                return

        # ----------------------------------------------------------------------
        # C. ADMIN DUYỆT RÚT TIỀN (ON-CHAIN)
        # ----------------------------------------------------------------------
        if path == "/api/admin/withdraw/approve":
            order_id = data.get("id")
            admin_approver = data.get("adminName") or "Hùng Admin"
            if not order_id:
                self.send_json(400, {"success": False, "message": "Thiếu mã lệnh ID."})
                return

            conn = sqlite3.connect(DB_FILE, timeout=10)
            c = conn.cursor()
            try:
                c.execute("SELECT id, user_id, user_name, amount, fee, net_amount, to_address, status FROM withdrawals WHERE id = ?", (order_id,))
                order = c.fetchone()
                if not order or order[7] != "PENDING":
                    conn.close()
                    self.send_json(400, {"success": False, "message": "Lệnh không tồn tại hoặc không ở trạng thái chờ duyệt."})
                    return

                wid, uid, uname, amt, fee, net_amt, to_addr, _ = order
                c.execute("UPDATE withdrawals SET status = 'PROCESSING', admin_approver = ? WHERE id = ? AND status = 'PENDING'", (admin_approver, wid))
                conn.commit()
                conn.close()

                send_result = send_bep20_withdrawal(to_addr, net_amt)

                conn = sqlite3.connect(DB_FILE, timeout=10)
                c = conn.cursor()
                if not send_result.get("success"):
                    err_r = send_result.get("error", "Lỗi phát sóng BSC")
                    c.execute("UPDATE withdrawals SET status = 'PENDING', reject_reason = ? WHERE id = ?", (f"Lỗi gửi BSC: {err_r}", wid))
                    conn.commit()
                    conn.close()
                    self.send_json(400, {"success": False, "message": f"Không thể gửi BSC: {err_r}"})
                    return

                tx_h = send_result.get("txid")
                blk_n = send_result.get("blockNumber")
                c.execute("UPDATE withdrawals SET status = 'COMPLETED', txid = ?, block_number = ?, approved_at = CURRENT_TIMESTAMP WHERE id = ?", (tx_h, blk_n, wid))
                c.execute("UPDATE users SET usdt_balance = usdt_balance - ?, locked_usdt = MAX(0.0, locked_usdt - ?) WHERE id = ?", (amt, amt, uid))
                c.execute("INSERT INTO transactions (user_id, user_name, type, amount, token, fee, status, txid, note) VALUES (?, ?, 'WITHDRAW', ?, 'USDT', ?, 'COMPLETED', ?, ?)",
                          (uid, uname, amt, fee, tx_h, f"Rút USDT BEP20 về {to_addr[:8]}..."))
                c.execute("INSERT INTO admin_logs (admin_name, action, target) VALUES (?, 'Duyệt lệnh rút tiền on-chain', ?)",
                          (admin_approver, f"Lệnh #{wid} (+{net_amt:.2f} USDT) TXID: {tx_h[:10]}..."))
                conn.commit()
                conn.close()

                self.send_json(200, {
                    "success": True,
                    "message": f"Đã duyệt và chuyển thành công {net_amt:.2f} USDT đến ví khách!",
                    "data": {"orderId": wid, "txid": tx_h, "blockNumber": blk_n, "netAmount": net_amt, "status": "COMPLETED"}
                })
                return
            except Exception as e:
                conn.close()
                self.send_json(500, {"success": False, "message": f"Lỗi duyệt lệnh: {str(e)}"})
                return

        # ----------------------------------------------------------------------
        # D. ADMIN TỪ CHỐI RÚT TIỀN (HOÀN TIỀN)
        # ----------------------------------------------------------------------
        if path == "/api/admin/withdraw/reject":
            order_id = data.get("id")
            reason = (data.get("reason") or "Admin từ chối yêu cầu rút tiền").strip()
            admin_approver = data.get("adminName") or "Hùng Admin"

            conn = sqlite3.connect(DB_FILE, timeout=10)
            c = conn.cursor()
            try:
                c.execute("SELECT id, user_id, amount, status FROM withdrawals WHERE id = ?", (order_id,))
                order = c.fetchone()
                if not order or order[3] not in ("PENDING", "PROCESSING"):
                    conn.close()
                    self.send_json(400, {"success": False, "message": "Lệnh không hợp lệ để từ chối."})
                    return

                wid, uid, amt, _ = order
                c.execute("UPDATE withdrawals SET status = 'REJECTED', reject_reason = ?, admin_approver = ?, approved_at = CURRENT_TIMESTAMP WHERE id = ?", (reason, admin_approver, wid))
                c.execute("UPDATE users SET locked_usdt = MAX(0.0, locked_usdt - ?) WHERE id = ?", (amt, uid))
                c.execute("INSERT INTO admin_logs (admin_name, action, target) VALUES (?, 'Từ chối lệnh rút tiền', ?)",
                          (admin_approver, f"Lệnh #{wid} ({amt:.2f} USDT) - Lý do: {reason}"))
                conn.commit()
                conn.close()

                self.send_json(200, {"success": True, "message": f"Đã từ chối lệnh #{wid} và mở khóa hoàn trả {amt:.2f} USDT cho khách."})
                return
            except Exception as e:
                conn.rollback()
                conn.close()
                self.send_json(500, {"success": False, "message": f"Lỗi: {str(e)}"})
                return

        # ----------------------------------------------------------------------
        # E. ADMIN KHÓA / MỞ KHÓA TÀI KHOẢN KHÁCH HÀNG
        # ----------------------------------------------------------------------
        if path == "/api/admin/user/toggle-lock":
            user_id = data.get("userId")
            admin_name = data.get("adminName") or "Hùng Admin"

            conn = sqlite3.connect(DB_FILE)
            c = conn.cursor()
            c.execute("SELECT id, name, is_locked FROM users WHERE id = ?", (user_id,))
            u = c.fetchone()
            if not u:
                conn.close()
                self.send_json(404, {"success": False, "message": "Không tìm thấy khách hàng."})
                return

            new_status = 1 if not u[2] else 0
            action_text = "Khóa tài khoản" if new_status == 1 else "Mở khóa tài khoản"
            c.execute("UPDATE users SET is_locked = ? WHERE id = ?", (new_status, user_id))
            c.execute("INSERT INTO admin_logs (admin_name, action, target) VALUES (?, ?, ?)",
                      (admin_name, action_text, f"{u[1]} ({user_id})"))
            conn.commit()
            conn.close()

            self.send_json(200, {
                "success": True,
                "message": f"Đã {action_text.lower()} {u[1]} thành công.",
                "isLocked": bool(new_status)
            })
            return

        # ----------------------------------------------------------------------
        # F. ADMIN CẬP NHẬT GIÁ GÓI ĐÀO
        # ----------------------------------------------------------------------
        if path == "/api/admin/package/update-price":
            new_price = float(data.get("price") or 10.0)
            admin_name = data.get("adminName") or "Hùng Admin"

            conn = sqlite3.connect(DB_FILE)
            c = conn.cursor()
            c.execute("INSERT OR REPLACE INTO system_settings (key, value, description) VALUES ('package_price', ?, 'Giá 1 gói đào WFI')", (str(new_price),))
            c.execute("INSERT INTO admin_logs (admin_name, action, target) VALUES (?, 'Đổi giá gói đào', ?)",
                      (admin_name, f"Giá mới: {new_price:.2f} USDT/gói"))
            conn.commit()
            conn.close()

            self.send_json(200, {"success": True, "message": f"Đã cập nhật giá gói đào thành {new_price:.2f} USDT."})
            return

        # ----------------------------------------------------------------------
        # G. ADMIN TRẢ LỜI SUPPORT TICKET
        # ----------------------------------------------------------------------
        if path == "/api/admin/ticket/reply":
            ticket_id = data.get("id")
            reply = (data.get("reply") or "").strip()
            admin_name = data.get("adminName") or "Hùng Admin"

            if not ticket_id or not reply:
                self.send_json(400, {"success": False, "message": "Vui lòng nhập nội dung phản hồi."})
                return

            conn = sqlite3.connect(DB_FILE)
            c = conn.cursor()
            c.execute("UPDATE support_tickets SET reply = ?, status = 'RESOLVED' WHERE id = ?", (reply, ticket_id))
            c.execute("INSERT INTO admin_logs (admin_name, action, target) VALUES (?, 'Phản hồi hỗ trợ khách hàng', ?)",
                      (admin_name, f"Ticket #{ticket_id}"))
            conn.commit()
            conn.close()

            self.send_json(200, {"success": True, "message": "Đã gửi phản hồi và giải quyết ticket."})
            return

        # ----------------------------------------------------------------------
        # H. ADMIN CẬP NHẬT CẤU HÌNH HỆ THỐNG
        # ----------------------------------------------------------------------
        if path == "/api/admin/settings/update":
            settings = data.get("settings") or {}
            admin_name = data.get("adminName") or "Hùng Admin"

            conn = sqlite3.connect(DB_FILE)
            c = conn.cursor()
            for k, v in settings.items():
                c.execute("UPDATE system_settings SET value = ?, updated_at = CURRENT_TIMESTAMP WHERE key = ?", (str(v), k))
            c.execute("INSERT INTO admin_logs (admin_name, action, target) VALUES (?, 'Cập nhật cấu hình hệ thống', 'Cấu hình chung')", (admin_name,))
            conn.commit()
            conn.close()

            self.send_json(200, {"success": True, "message": "Cấu hình hệ thống đã được lưu thành công."})
            return

        # ----------------------------------------------------------------------
        # I. ADMIN THÊM TÀI KHOẢN QUẢN TRỊ VIÊN MỚI
        # ----------------------------------------------------------------------
        if path == "/api/admin/admins/add":
            uname = (data.get("username") or "").strip()
            name = (data.get("name") or "").strip()
            email = (data.get("email") or "").strip()
            role = (data.get("role") or "CSKH (Hỗ trợ)").strip()
            admin_name = data.get("adminName") or "Hùng Admin"

            if not uname or not name:
                self.send_json(400, {"success": False, "message": "Vui lòng nhập đầy đủ tên đăng nhập và họ tên."})
                return

            conn = sqlite3.connect(DB_FILE)
            c = conn.cursor()
            try:
                c.execute("INSERT INTO admin_users (username, name, email, role, status) VALUES (?, ?, ?, ?, 'ACTIVE')", (uname, name, email, role))
                c.execute("INSERT INTO admin_logs (admin_name, action, target) VALUES (?, 'Thêm quản trị viên mới', ?)",
                          (admin_name, f"{name} ({role})"))
                conn.commit()
                conn.close()
                self.send_json(200, {"success": True, "message": f"Đã thêm quản trị viên {name} thành công."})
                return
            except sqlite3.IntegrityError:
                conn.close()
                self.send_json(400, {"success": False, "message": "Tên đăng nhập đã tồn tại."})
                return

        # ----------------------------------------------------------------------
        # J. KHÁCH HÀNG MUA GÓI ĐÀO (TỰ ĐỘNG TÍNH DOANH SỐ & NÂNG CẤP HOA HỒNG)
        # ----------------------------------------------------------------------
        if path == "/api/package/buy":
            user_id = data.get("userId") or "user_default"
            qty = int(data.get("quantity") or 1)
            if qty <= 0:
                self.send_json(400, {"success": False, "message": "Số lượng gói không hợp lệ"})
                return

            conn = sqlite3.connect(DB_FILE, timeout=10)
            c = conn.cursor()
            try:
                # Lấy giá gói đào từ cấu hình
                c.execute("SELECT value FROM system_settings WHERE key = 'package_price'")
                pkg_price_row = c.fetchone()
                pkg_price = float(pkg_price_row[0]) if pkg_price_row else 10.0
                total_cost = round(qty * pkg_price, 2)
                daily_yield = round(qty * 5000.0, 2)

                c.execute("SELECT name, usdt_balance, locked_usdt, referrer_id FROM users WHERE id = ?", (user_id,))
                user = c.fetchone()
                if not user:
                    conn.close()
                    self.send_json(404, {"success": False, "message": "Không tìm thấy người dùng"})
                    return

                u_name, tot_bal, loc_bal, ref_id = user
                loc_bal = loc_bal or 0.0
                avail_bal = tot_bal - loc_bal

                if avail_bal < total_cost:
                    conn.close()
                    self.send_json(400, {"success": False, "message": f"Số dư USDT khả dụng ({avail_bal:.2f}) không đủ để mua {qty} gói ({total_cost:.2f} USDT)."})
                    return

                # Trừ số dư USDT của khách
                c.execute("UPDATE users SET usdt_balance = usdt_balance - ? WHERE id = ?", (total_cost, user_id))

                # Thêm gói đào vào bảng packages
                c.execute("""
                    INSERT INTO packages (user_id, user_name, package_name, price, quantity, daily_yield, status)
                    VALUES (?, ?, 'Gói đào WFI', ?, ?, ?, 'ACTIVE')
                """, (user_id, u_name, pkg_price, qty, daily_yield))
                new_pkg_id = c.lastrowid

                # Ghi sổ cái giao dịch
                c.execute("""
                    INSERT INTO transactions (user_id, user_name, type, amount, token, fee, status, note)
                    VALUES (?, ?, 'BUY_PACKAGE', ?, 'USDT', 0.0, 'COMPLETED', ?)
                """, (user_id, u_name, total_cost, f"Mua {qty} gói đào WFI (#{new_pkg_id})"))

                # TỰ ĐỘNG TÍNH LẠI DOANH SỐ VÀ NÂNG CẤP HOA HỒNG TỰ ĐỘNG
                tier_res = evaluate_and_update_commission_tier(c, user_id, f"Mua {qty} gói đào WFI (+{total_cost:.2f} USDT)")

                # Nếu có người giới thiệu, ghi nhận hoa hồng cho cấp trên dựa trên commission_rate của cấp trên
                if ref_id:
                    c.execute("SELECT name, commission_rate FROM users WHERE id = ?", (ref_id,))
                    ref_row = c.fetchone()
                    if ref_row:
                        ref_name, ref_rate = ref_row
                        ref_rate = float(ref_rate or 0.0)
                        if ref_rate > 0:
                            ref_comm_amt = round(total_cost * ref_rate, 2)
                            c.execute("UPDATE users SET usdt_balance = usdt_balance + ? WHERE id = ?", (ref_comm_amt, ref_id))
                            c.execute("""
                                INSERT INTO commissions (user_id, user_name, from_user_id, from_user_name, package_id, package_amount, commission_rate, commission_amount, status)
                                VALUES (?, ?, ?, ?, ?, ?, ?, ?, 'PAID')
                            """, (ref_id, ref_name, user_id, u_name, new_pkg_id, total_cost, ref_rate, ref_comm_amt))
                            c.execute("""
                                INSERT INTO transactions (user_id, user_name, type, amount, token, fee, status, note)
                                VALUES (?, ?, 'COMMISSION', ?, 'USDT', 0.0, 'COMPLETED', ?)
                            """, (ref_id, ref_name, ref_comm_amt, f"Hoa hồng {int(ref_rate*100)}% từ F1 {u_name} mua gói #{new_pkg_id}"))

                conn.commit()

                c.execute("SELECT usdt_balance, locked_usdt, sales_volume, commission_level, commission_rate FROM users WHERE id = ?", (user_id,))
                updated_user = c.fetchone()
                conn.close()

                upgrade_msg = ""
                if tier_res and tier_res.get("tierChanged") and tier_res.get("newLevel", 0) > tier_res.get("oldLevel", 0):
                    upgrade_msg = f" 🏆 CHÚC MỪNG: Bạn đã được TỰ ĐỘNG NÂNG CẤP lên {tier_res.get('tierName')} (Hoa hồng {int(tier_res.get('commissionRate', 0)*100)}%)!"

                self.send_json(200, {
                    "success": True,
                    "message": f"Mua thành công {qty} gói đào WFI ({total_cost:.2f} USDT)!{upgrade_msg}",
                    "package": {
                        "id": new_pkg_id,
                        "quantity": qty,
                        "cost": total_cost,
                        "dailyYield": daily_yield
                    },
                    "user": {
                        "usdtBalance": round(updated_user[0], 2),
                        "availableUsdt": max(0.0, round(updated_user[0] - (updated_user[1] or 0.0), 2)),
                        "salesVolume": round(updated_user[2] or 0.0, 2),
                        "commissionLevel": updated_user[3],
                        "commissionRate": updated_user[4],
                        "tierChanged": tier_res.get("tierChanged", False) if tier_res else False
                    }
                })
                return
            except Exception as e:
                conn.rollback()
                conn.close()
                self.send_json(500, {"success": False, "message": f"Lỗi mua gói: {str(e)}"})
                return

        # ----------------------------------------------------------------------
        # K. ADMIN HỦY / HOÀN TIỀN GÓI ĐÀO (TỰ ĐỘNG XỬ LÝ LẠI DOANH SỐ & HẠ CẤP)
        # ----------------------------------------------------------------------
        if path == "/api/admin/package/refund":
            pkg_id = data.get("packageId")
            reason = (data.get("reason") or "Hủy và hoàn tiền gói đào theo yêu cầu").strip()
            admin_name = data.get("adminName") or "Hùng Admin"

            if not pkg_id:
                self.send_json(400, {"success": False, "message": "Thiếu mã gói đào ID"})
                return

            conn = sqlite3.connect(DB_FILE, timeout=10)
            c = conn.cursor()
            try:
                c.execute("SELECT id, user_id, user_name, package_name, price, quantity, status FROM packages WHERE id = ?", (pkg_id,))
                pkg = c.fetchone()
                if not pkg:
                    conn.close()
                    self.send_json(404, {"success": False, "message": "Không tìm thấy gói đào"})
                    return

                if pkg[6] == "REFUNDED":
                    conn.close()
                    self.send_json(400, {"success": False, "message": "Gói đào này đã được hoàn tiền trước đó"})
                    return

                p_id, u_id, u_name, p_name, p_price, p_qty, p_status = pkg
                refund_amount = round(p_price * p_qty, 2)

                # Cập nhật trạng thái gói thành REFUNDED
                c.execute("UPDATE packages SET status = 'REFUNDED' WHERE id = ?", (p_id,))

                # Hoàn trả tiền USDT vào tài khoản khách
                c.execute("UPDATE users SET usdt_balance = usdt_balance + ? WHERE id = ?", (refund_amount, u_id))

                # Ghi lịch sử giao dịch REFUND
                c.execute("""
                    INSERT INTO transactions (user_id, user_name, type, amount, token, fee, status, note)
                    VALUES (?, ?, 'REFUND', ?, 'USDT', 0.0, 'COMPLETED', ?)
                """, (u_id, u_name, refund_amount, f"Hoàn tiền gói đào #{p_id} ({p_qty} gói) - Lý do: {reason}"))

                # Ghi nhật ký Admin
                c.execute("""
                    INSERT INTO admin_logs (admin_name, action, target)
                    VALUES (?, 'Hoàn tiền / hủy gói đào', ?)
                """, (admin_name, f"Gói #{p_id} của {u_name} (+{refund_amount:.2f} USDT) - {reason}"))

                # TỰ ĐỘNG XỬ LÝ LẠI DOANH SỐ & HẠ CẤP NẾU KHÔNG ĐỦ MỐC
                # Đặt lại sales_volume bằng tổng các gói hợp lệ còn lại
                c.execute("SELECT COALESCE(SUM(price * quantity), 0) FROM packages WHERE user_id = ? AND status IN ('ACTIVE', 'COMPLETED')", (u_id,))
                recalc_sales = float(c.fetchone()[0] or 0.0)
                c.execute("UPDATE users SET sales_volume = ? WHERE id = ?", (recalc_sales, u_id))

                tier_res = evaluate_and_update_commission_tier(c, u_id, f"Hoàn tiền hủy gói #{p_id} (-{refund_amount:.2f} USDT)")

                conn.commit()

                c.execute("SELECT sales_volume, commission_level, commission_rate FROM users WHERE id = ?", (u_id,))
                u_after = c.fetchone()
                conn.close()

                downgrade_note = ""
                if tier_res and tier_res.get("tierChanged") and tier_res.get("newLevel", 0) < tier_res.get("oldLevel", 0):
                    downgrade_note = f" (Hệ thống đã tự động hạ cấp từ Cấp {tier_res['oldLevel']} xuống {tier_res['tierName']})."

                self.send_json(200, {
                    "success": True,
                    "message": f"Đã hoàn trả thành công {refund_amount:.2f} USDT cho khách hàng {u_name}. Doanh số mới: {u_after[0]:.2f} USDT{downgrade_note}",
                    "refund": {
                        "packageId": p_id,
                        "refundAmount": refund_amount,
                        "newSalesVolume": round(u_after[0], 2),
                        "newCommissionLevel": u_after[1],
                        "newCommissionRate": u_after[2]
                    }
                })
                return
            except Exception as e:
                conn.rollback()
                conn.close()
                self.send_json(500, {"success": False, "message": f"Lỗi hoàn tiền gói: {str(e)}"})
                return

        # ----------------------------------------------------------------------
        # L. ADMIN CHỐT BẢNG XẾP HẠNG TUẦN & TRAO THƯỞNG TOP 3
        # ----------------------------------------------------------------------
        if path == "/api/admin/leaderboard/settle":
            conn = sqlite3.connect(DB_FILE, timeout=10)
            c = conn.cursor()
            try:
                res = check_and_settle_weekly_leaderboard(c, force=True)
                conn.commit()
                conn.close()
                self.send_json(200, {
                    "success": True,
                    "message": f"Đã chốt thành công Bảng xếp hạng Tuần #{res.get('settledWeek')} và tự động trao thưởng cho Top 3!",
                    "settlement": res
                })
                return
            except Exception as e:
                conn.rollback()
                conn.close()
                self.send_json(500, {"success": False, "message": f"Lỗi chốt bảng xếp hạng: {str(e)}"})
                return

        # ----------------------------------------------------------------------
        # M. AUTHENTICATION: ĐĂNG NHẬP GMAIL + MẬT KHẨU (PBKDF2/SHA-256)
        # ----------------------------------------------------------------------
        if path == "/api/auth/login":
            email = (data.get("email") or "").strip().lower()
            password = data.get("password") or ""

            if not email or not password:
                self.send_json(400, {"success": False, "message": "Vui lòng nhập đầy đủ Gmail và mật khẩu"})
                return

            conn = sqlite3.connect(DB_FILE)
            c = conn.cursor()
            c.execute("""
                SELECT id, name, email, role, tier, is_locked, password_hash, salt
                FROM users
                WHERE LOWER(email) = ?
            """, (email,))
            u = c.fetchone()

            if not u:
                conn.close()
                self.send_json(400, {"success": False, "message": "Gmail hoặc mật khẩu không chính xác"})
                return

            u_id, u_name, u_email, u_role, u_tier, u_locked, pwd_hash, salt = u

            if u_locked:
                conn.close()
                self.send_json(403, {"success": False, "message": "Tài khoản của bạn đã bị khóa bởi Quản trị viên."})
                return

            # Kiểm tra mật khẩu đã hash
            is_valid = False
            if pwd_hash and salt:
                is_valid = verify_password(password, pwd_hash, salt)
            else:
                # Nếu tài khoản cũ chưa có hash, mật khẩu mặc định 123456
                if password == "123456":
                    is_valid = True
                    new_hash, new_salt = hash_password("123456")
                    c.execute("UPDATE users SET password_hash = ?, salt = ? WHERE id = ?", (new_hash, new_salt, u_id))
                    conn.commit()

            conn.close()

            if not is_valid:
                self.send_json(400, {"success": False, "message": "Gmail hoặc mật khẩu không chính xác"})
                return

            auth_token = secrets.token_hex(24)
            self.send_json(200, {
                "success": True,
                "message": "Đăng nhập thành công",
                "user": {
                    "id": u_id,
                    "name": u_name,
                    "email": u_email,
                    "role": u_role or "CUSTOMER",
                    "tier": u_tier,
                    "isLocked": False
                },
                "token": auth_token
            })
            return

        # ----------------------------------------------------------------------
        # N. MKT DEMO: TẠO SỰ KIỆN THÔNG BÁO RÚT DEMO (RBAC BACKEND)
        # KHÔNG CHUYỂN TIỀN THẬT - KHÔNG GỌI BLOCKCHAIN - KHÔNG TRỪ SỐ DƯ
        # ----------------------------------------------------------------------
        if path == "/api/mkt/demo-notify":
            user_id = data.get("userId")
            try:
                amount = float(data.get("amount") or 0.0)
            except Exception:
                amount = 0.0
            to_address = (data.get("toAddress") or "").strip()

            if not user_id:
                self.send_json(400, {"success": False, "message": "Thiếu mã định danh người dùng"})
                return

            if amount <= 0:
                self.send_json(400, {"success": False, "message": "Số tiền USDT rút demo phải lớn hơn 0"})
                return

            if not to_address:
                self.send_json(400, {"success": False, "message": "Vui lòng nhập địa chỉ ví nhận"})
                return

            # RBAC Backend: Chỉ tài khoản MKT mới được phép gọi
            conn = sqlite3.connect(DB_FILE, timeout=10)
            c = conn.cursor()
            c.execute("SELECT id, name, email, role, is_locked FROM users WHERE id = ?", (user_id,))
            u = c.fetchone()

            if not u:
                conn.close()
                self.send_json(404, {"success": False, "message": "Không tìm thấy tài khoản người dùng"})
                return

            u_id, u_name, u_email, u_role, u_locked = u

            if u_role != "MKT":
                conn.close()
                self.send_json(403, {
                    "success": False,
                    "message": "Truy cập bị từ chối: Chức năng 'Rút thông báo Demo' chỉ dành riêng cho tài khoản MKT!"
                })
                return

            if u_locked:
                conn.close()
                self.send_json(403, {"success": False, "message": "Tài khoản MKT đã bị tạm khóa"})
                return

            # Backend xử lý trễ khoảng 5 giây, độc lập frontend
            now_ts = int(time.time())
            delivered_ts = now_ts + 5

            # Rút gọn địa chỉ ví để hiển thị chuẩn như ví dụ của Sếp (0x7A...8F2)
            short_addr = to_address
            if len(to_address) > 12:
                short_addr = f"{to_address[:4]}...{to_address[-4:]}"

            # Thời gian UTC chuẩn theo mẫu trong ảnh: 2026-10-08 14:40:08 (UTC)
            utc_now = datetime.datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S")

            # Tiêu đề & nội dung notification chuẩn theo ảnh Sếp gửi
            # Notification có nhãn rõ ràng DEMO để không bị hiểu là giao dịch thật
            title = "Rút USDT thành công [DEMO]"
            body = f"Bạn đã rút thành công {amount:g} USDT lúc {utc_now} (UTC). Ví nhận: {short_addr}. Nếu bạn không nhận ra hoạt động này, vui lòng liên hệ với chúng tôi ngay lập tức."

            # LƯU VÀO BẢNG RIÊNG mkt_demo_notifications
            # QUAN TRỌNG: TUYỆT ĐỐI KHÔNG trừ số dư, KHÔNG tạo withdrawals thật, KHÔNG gọi blockchain!
            c.execute("""
                INSERT INTO mkt_demo_notifications (
                    user_id, email, amount, to_address, title, body,
                    status, category, virtual_flag, scheduled_at, delivered_at
                )
                VALUES (?, ?, ?, ?, ?, ?, 'PENDING', 'MKT_DEMO', 'VIRTUAL_NOTIFICATION', ?, ?)
            """, (u_id, u_email, amount, to_address, title, body, now_ts, delivered_ts))

            event_id = c.lastrowid
            conn.commit()
            conn.close()

            self.send_json(200, {
                "success": True,
                "message": "Đã tạo sự kiện thông báo DEMO thành công. Sau khoảng 5 giây thiết bị sẽ nhận được push notification.",
                "eventId": event_id,
                "delaySeconds": 5,
                "notification": {
                    "id": event_id,
                    "amount": amount,
                    "toAddress": to_address,
                    "shortAddress": short_addr,
                    "title": title,
                    "body": body,
                    "scheduledAt": now_ts,
                    "deliveredAt": delivered_ts,
                    "category": "MKT_DEMO",
                    "virtualFlag": "VIRTUAL_NOTIFICATION"
                }
            })
            return

        # ----------------------------------------------------------------------
        # O. ADMIN: TẠO TÀI KHOẢN MKT (GMAIL + MẬT KHẨU HASH)
        # ----------------------------------------------------------------------
        if path == "/api/admin/mkt/create":
            email = (data.get("email") or "").strip().lower()
            password = data.get("password") or ""
            name = (data.get("name") or "").strip()
            admin_name = data.get("adminName") or "Hùng Admin"

            if not email:
                self.send_json(400, {"success": False, "message": "Vui lòng nhập Gmail của tài khoản MKT"})
                return

            if "@" not in email:
                self.send_json(400, {"success": False, "message": "Gmail không hợp lệ"})
                return

            if len(password) < 6:
                self.send_json(400, {"success": False, "message": "Mật khẩu phải có ít nhất 6 ký tự"})
                return

            conn = sqlite3.connect(DB_FILE, timeout=10)
            c = conn.cursor()

            # Kiểm tra email trùng
            c.execute("SELECT id FROM users WHERE LOWER(email) = ?", (email,))
            if c.fetchone():
                conn.close()
                self.send_json(400, {"success": False, "message": "Gmail này đã tồn tại trong hệ thống"})
                return

            # Tạo UID 8 số ngẫu nhiên cho MKT
            mkt_uid = "88" + str(secrets.randbelow(900000) + 100000)
            display_name = name if name else f"MKT ({email.split('@')[0]})"

            # Băm mật khẩu bằng PBKDF2-HMAC-SHA256 kèm salt ngẫu nhiên
            pwd_hash, salt = hash_password(password)

            c.execute("""
                INSERT INTO users (
                    id, name, email, phone, tier, usdt_balance, locked_usdt,
                    wfi_balance, is_locked, role, password_hash, salt
                )
                VALUES (?, ?, ?, '0900000000', 'VIP MKT', 0.0, 0.0, 0.0, 0, 'MKT', ?, ?)
            """, (mkt_uid, display_name, email, pwd_hash, salt))

            # Ghi nhật ký Admin Audit Log
            c.execute("""
                INSERT INTO admin_logs (admin_name, action, target)
                VALUES (?, 'Tạo tài khoản MKT mới', ?)
            """, (admin_name, f"UID: {mkt_uid} - {email}"))

            conn.commit()
            conn.close()

            self.send_json(200, {
                "success": True,
                "message": f"Đã tạo thành công tài khoản MKT: {email}",
                "mktUser": {
                    "id": mkt_uid,
                    "name": display_name,
                    "email": email,
                    "role": "MKT"
                }
            })
            return

        # ----------------------------------------------------------------------
        # P. ADMIN: KHÓA / MỞ KHÓA TÀI KHOẢN MKT
        # ----------------------------------------------------------------------
        if path == "/api/admin/mkt/toggle-lock":
            user_id = data.get("userId")
            is_locked = 1 if data.get("isLocked") else 0
            admin_name = data.get("adminName") or "Hùng Admin"

            if not user_id:
                self.send_json(400, {"success": False, "message": "Thiếu mã tài khoản MKT"})
                return

            conn = sqlite3.connect(DB_FILE, timeout=10)
            c = conn.cursor()
            c.execute("SELECT email, role FROM users WHERE id = ?", (user_id,))
            u = c.fetchone()
            if not u or u[1] != "MKT":
                conn.close()
                self.send_json(404, {"success": False, "message": "Không tìm thấy tài khoản MKT"})
                return

            c.execute("UPDATE users SET is_locked = ? WHERE id = ?", (is_locked, user_id))
            status_text = "Khóa tài khoản" if is_locked == 1 else "Mở khóa tài khoản"
            c.execute("""
                INSERT INTO admin_logs (admin_name, action, target)
                VALUES (?, ?, ?)
            """, (admin_name, f"{status_text} MKT", f"UID: {user_id} - {u[0]}"))

            conn.commit()
            conn.close()

            self.send_json(200, {
                "success": True,
                "message": f"Đã {status_text.lower()} MKT thành công!",
                "isLocked": bool(is_locked)
            })
            return

        # ----------------------------------------------------------------------
        # Q. ADMIN: CẬP NHẬT TIÊU ĐỀ, NỘI DUNG & LOGO PUSH NOTIFICATION MKT (KHÔNG HARD-CODE)
        # ----------------------------------------------------------------------
        if path == "/api/admin/mkt/config":
            title = (data.get("title") or "").strip()
            body_template = (data.get("bodyTemplate") or "").strip()
            delay_seconds = int(data.get("delaySeconds") or 5)
            icon_url = (data.get("iconUrl") or "").strip()
            admin_name = data.get("adminName") or "Hùng Admin"

            if not title:
                self.send_json(400, {"success": False, "message": "Vui lòng nhập Tiêu đề notification"})
                return
            if not body_template:
                self.send_json(400, {"success": False, "message": "Vui lòng nhập Nội dung notification"})
                return

            conn = sqlite3.connect(DB_FILE, timeout=10)
            c = conn.cursor()
            c.execute("""
                INSERT INTO mkt_notification_config (id, title, body_template, delay_seconds, icon_url, updated_at)
                VALUES (1, ?, ?, ?, ?, CURRENT_TIMESTAMP)
                ON CONFLICT(id) DO UPDATE SET
                    title = excluded.title,
                    body_template = excluded.body_template,
                    delay_seconds = excluded.delay_seconds,
                    icon_url = excluded.icon_url,
                    updated_at = CURRENT_TIMESTAMP
            """, (title, body_template, delay_seconds, icon_url))

            c.execute("""
                INSERT INTO admin_logs (admin_name, action, target)
                VALUES (?, 'Cập nhật cấu hình Push Notification MKT', ?)
            """, (admin_name, f"Tiêu đề: {title} | Logo: {'Tùy chỉnh' if icon_url else 'Mặc định'}"))

            conn.commit()
            conn.close()

            self.send_json(200, {
                "success": True,
                "message": "Đã lưu cấu hình Tiêu đề, Nội dung & Logo thành công!",
                "config": {
                    "title": title,
                    "bodyTemplate": body_template,
                    "delaySeconds": delay_seconds,
                    "iconUrl": icon_url
                }
            })
            return

        self.send_json(404, {"success": False, "message": "API endpoint không tồn tại"})


# ==============================================================================
# HÀM CHÍNH (ĐA LUỒNG THREADING TCPSERVER ĐỂ TRÁNH NGHẼN SERVER)
# ==============================================================================
def run_server():
    init_database()
    os.chdir(os.path.dirname(os.path.abspath(__file__)))

    socketserver.ThreadingTCPServer.allow_reuse_address = True
    with socketserver.ThreadingTCPServer(("", PORT), WfiHttpHandler) as httpd:
        print(f"================================================================")
        print(f"🚀 WFI MINING MASTER BACKEND ĐANG CHẠY TẠI CỔNG {PORT}:")
        print(f"   👉 App Khách:   http://localhost:{PORT}/")
        print(f"   👉 iPhone Mock: http://localhost:{PORT}/iphone.html")
        print(f"   👉 Cổng Admin:  http://localhost:{PORT}/admin.html")
        print(f"----------------------------------------------------------------")
        print(f"🔹 11 Phân hệ Admin: Dashboard, Khách hàng, Gói đào, Nạp, Rút,")
        print(f"                     WFI, Giao dịch, Doanh thu, Hỗ trợ, Cấu hình, Phân quyền")
        print(f"🔹 Bảo mật:          Private Key lưu tại .env, Quản lý Nonce bằng Mutex")
        print(f"================================================================")
        try:
            httpd.serve_forever()
        except KeyboardInterrupt:
            print("\nĐang dừng máy chủ...")
            httpd.server_close()


if __name__ == "__main__":
    run_server()
