// 志愿页默认填充值（新用户的中性缺省）。
// 个人信息（区排名/住址/初中）不再硬编码：登录后由该用户已存 profile 回填，
// 没有 profile 的新用户则留空自填。这里只保留与个人无关的 UX 缺省。
export const USER_DEFAULTS = {
  rank: '' as number | string,         // 区排名（一模/二模）— 留空自填
  home: '',                            // 家庭住址 — 留空自填
  mode: 'bicycling',                   // 通勤方式（UX 缺省）
  max_km: 8 as number | string,        // 通勤上限 km（UX 缺省）
  boarding: true,                      // 是否接受住宿（UX 缺省；通勤上限仍生效）
  identity: 'jjyj' as 'jjyj' | 'feijing' | 'wangjie', // 考生身份缺省：京籍应届
  chuzhong: '',                        // 初中校 — 留空自填（校额到校查名额用）
}
