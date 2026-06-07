// 志愿页默认填充值（缺省数据）
// ⚠️ 当前为开发/自用阶段的真实数据；正式对外上线前请替换为脱敏占位值（或留空）。
export const USER_DEFAULTS = {
  rank: 4500,                          // 区排名（一模/二模）
  home: '朝阳区大屯路金泉花园小区',     // 家庭住址
  mode: 'bicycling',                   // 通勤方式
  max_km: 8 as number | string,        // 通勤上限 km
  boarding: true,                      // 是否接受住宿（缺省勾选；通勤上限仍生效）
  identity: 'jjyj' as 'jjyj' | 'feijing' | 'wangjie', // 考生身份：京籍应届
  chuzhong: '北京市朝阳外国语学校',     // 初中校缺省（校额到校查名额用）
}
