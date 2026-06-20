// 项目级统一鉴权 — 前端客户端(同域,Cookie 自动携带)。
// 后端 /api/auth/* 由 server/auth 提供,学情与志愿共用一套登录态。

export interface AuthUser { id: number; phone?: string | null; email?: string | null; nickname?: string | null }

async function call(path: string, opts: RequestInit = {}): Promise<any> {
  const r = await fetch(path, {
    credentials: 'same-origin',
    headers: { 'Content-Type': 'application/json' },
    ...opts,
  })
  const body = await r.json().catch(() => ({}))
  if (!r.ok) throw Object.assign(new Error(body.detail || `HTTP ${r.status}`), { status: r.status })
  return body
}

// 当前登录态;未登录返回 null(不抛错)
export async function fetchMe(app = 'zhiyuan'): Promise<{ user: AuthUser; profile: any } | null> {
  try {
    return await call(`/api/auth/me?app=${app}`)
  } catch (e: any) {
    if (e.status === 401) return null
    throw e
  }
}

// account = 手机号 或 邮箱(后端自动识别,短信/邮件分别下发)
export const sendCode = (account: string): Promise<{ ok: boolean; cooldown: number; channel: string }> =>
  call('/api/auth/code/send', { method: 'POST', body: JSON.stringify({ account }) })

export const verifyCode = (account: string, code: string): Promise<{ user: AuthUser }> =>
  call('/api/auth/code/verify', { method: 'POST', body: JSON.stringify({ account, code }) })

export const logout = () => call('/api/auth/logout', { method: 'POST' })

export const getProfile = (app = 'zhiyuan') => call(`/api/auth/profile?app=${app}`)

export const putProfile = (data: any, app = 'zhiyuan') =>
  call(`/api/auth/profile?app=${app}`, { method: 'PUT', body: JSON.stringify(data) })
