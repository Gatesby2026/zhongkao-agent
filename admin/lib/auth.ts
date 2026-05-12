import jwt from "jsonwebtoken";
import { getDb } from "./db";

// JWT 密钥 — 生产环境应从环境变量读取
const JWT_SECRET = process.env.JWT_SECRET || "zkAgent_jwt_secret_2026";
const JWT_EXPIRES_IN = "30d"; // 30 天过期

export interface JwtPayload {
  userId: number;
  phone: string;
}

export interface UserInfo {
  id: number;
  phone: string;
  nickname: string;
  role: string;
  createdAt: string;
  lastLoginAt: string;
}

/**
 * 生成 6 位数字验证码
 */
export function generateCode(): string {
  return String(Math.floor(100000 + Math.random() * 900000));
}

/**
 * 发送验证码（保存到数据库 + 发短信）
 * 返回 { success, message, code? }
 * code 仅在开发模式返回
 */
export function sendVerificationCode(phone: string): { success: boolean; message: string; devCode?: string } {
  // 验证手机号格式
  if (!/^1[3-9]\d{9}$/.test(phone)) {
    return { success: false, message: "手机号格式不正确" };
  }

  const db = getDb();

  // 限流：同一手机号 60 秒内只能发一次
  const recent = db.prepare(`
    SELECT id FROM verification_codes
    WHERE phone = ? AND created_at > datetime('now', '-60 seconds')
    ORDER BY created_at DESC LIMIT 1
  `).get(phone) as any;

  if (recent) {
    return { success: false, message: "发送太频繁，请 60 秒后再试" };
  }

  // 同一手机号每天最多 10 次
  const dailyCount = db.prepare(`
    SELECT COUNT(*) as cnt FROM verification_codes
    WHERE phone = ? AND created_at > datetime('now', '-1 day')
  `).get(phone) as any;

  if (dailyCount?.cnt >= 10) {
    return { success: false, message: "今日验证码发送次数已达上限" };
  }

  const code = generateCode();
  const expiresAt = new Date(Date.now() + 5 * 60 * 1000).toISOString(); // 5 分钟过期

  db.prepare(`
    INSERT INTO verification_codes (phone, code, expires_at) VALUES (?, ?, ?)
  `).run(phone, code, expiresAt);

  // TODO: 接入阿里云短信 SDK 发送真实短信
  // 开发阶段打印到控制台
  const isDev = process.env.NODE_ENV !== "production" || !process.env.SMS_ACCESS_KEY;
  if (isDev) {
    console.log(`\n📱 [DEV] 验证码 → ${phone}: ${code}\n`);
    return { success: true, message: "验证码已发送（开发模式）", devCode: code };
  }

  // 生产环境：调用阿里云短信
  // sendAliyunSms(phone, code);  // TODO
  return { success: true, message: "验证码已发送" };
}

/**
 * 验证验证码并登录/注册
 * 返回 JWT token + 用户信息
 */
export function verifyCodeAndLogin(phone: string, code: string): {
  success: boolean;
  message: string;
  token?: string;
  user?: UserInfo;
  isNewUser?: boolean;
} {
  if (!/^1[3-9]\d{9}$/.test(phone)) {
    return { success: false, message: "手机号格式不正确" };
  }

  const db = getDb();

  // 查找有效验证码
  const record = db.prepare(`
    SELECT id FROM verification_codes
    WHERE phone = ? AND code = ? AND used = 0 AND expires_at > datetime('now')
    ORDER BY created_at DESC LIMIT 1
  `).get(phone, code) as any;

  if (!record) {
    return { success: false, message: "验证码错误或已过期" };
  }

  // 标记验证码已使用
  db.prepare(`UPDATE verification_codes SET used = 1 WHERE id = ?`).run(record.id);

  // 查找或创建用户
  let user = db.prepare(`SELECT * FROM users WHERE phone = ?`).get(phone) as any;
  let isNewUser = false;

  if (!user) {
    // 新用户注册
    const result = db.prepare(`
      INSERT INTO users (phone, nickname) VALUES (?, ?)
    `).run(phone, `用户${phone.slice(-4)}`);

    user = db.prepare(`SELECT * FROM users WHERE id = ?`).get(result.lastInsertRowid) as any;
    isNewUser = true;

    // 为新用户创建空画像
    db.prepare(`INSERT INTO profiles (user_id) VALUES (?)`).run(user.id);
  } else {
    // 更新登录时间
    db.prepare(`UPDATE users SET last_login_at = CURRENT_TIMESTAMP WHERE id = ?`).run(user.id);
  }

  // 生成 JWT
  const payload: JwtPayload = { userId: user.id, phone: user.phone };
  const token = jwt.sign(payload, JWT_SECRET, { expiresIn: JWT_EXPIRES_IN });

  return {
    success: true,
    message: isNewUser ? "注册成功" : "登录成功",
    token,
    user: {
      id: user.id,
      phone: user.phone,
      nickname: user.nickname,
      role: user.role,
      createdAt: user.created_at,
      lastLoginAt: user.last_login_at,
    },
    isNewUser,
  };
}

/**
 * 从 JWT token 解析用户信息
 */
export function verifyToken(token: string): JwtPayload | null {
  try {
    return jwt.verify(token, JWT_SECRET) as JwtPayload;
  } catch {
    return null;
  }
}

/**
 * 从 Authorization header 或 cookie 中获取当前用户
 */
export function getCurrentUser(authHeader?: string | null): UserInfo | null {
  if (!authHeader?.startsWith("Bearer ")) return null;

  const token = authHeader.slice(7);
  const payload = verifyToken(token);
  if (!payload) return null;

  const db = getDb();
  const user = db.prepare(`SELECT * FROM users WHERE id = ?`).get(payload.userId) as any;
  if (!user) return null;

  return {
    id: user.id,
    phone: user.phone,
    nickname: user.nickname,
    role: user.role,
    createdAt: user.created_at,
    lastLoginAt: user.last_login_at,
  };
}
