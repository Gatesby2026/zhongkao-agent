/**
 * 北京各区高中录取参考分数线（总分 510 制）
 * 数据来源：2024-2025 年各校录取数据，仅供参考
 */

export interface School {
  name: string;
  tier: "顶尖" | "重点" | "普通" | "保底";
  /** 录取参考线（总分 510 制） */
  refScore: number;
}

export const DISTRICTS = ["朝阳区", "海淀区", "西城区", "东城区"] as const;
export type District = (typeof DISTRICTS)[number];

export const SCHOOLS_BY_DISTRICT: Record<District, School[]> = {
  朝阳区: [
    { name: "八十中（创新班）", tier: "顶尖", refScore: 490 },
    { name: "北京中学", tier: "顶尖", refScore: 480 },
    { name: "八十中（普通班）", tier: "顶尖", refScore: 465 },
    { name: "人大附中朝阳学校", tier: "重点", refScore: 455 },
    { name: "清华附中朝阳学校", tier: "重点", refScore: 450 },
    { name: "陈经纶中学", tier: "重点", refScore: 445 },
    { name: "朝阳外国语学校", tier: "重点", refScore: 440 },
    { name: "工大附中", tier: "普通", refScore: 405 },
    { name: "日坛中学", tier: "普通", refScore: 390 },
    { name: "和平街一中", tier: "普通", refScore: 380 },
    { name: "三里屯一中", tier: "保底", refScore: 340 },
  ],
  海淀区: [
    { name: "十一学校（科实班）", tier: "顶尖", refScore: 498 },
    { name: "人大附中", tier: "顶尖", refScore: 490 },
    { name: "101中学", tier: "顶尖", refScore: 480 },
    { name: "清华附中", tier: "顶尖", refScore: 475 },
    { name: "首师大附中", tier: "顶尖", refScore: 475 },
    { name: "北大附中", tier: "重点", refScore: 465 },
    { name: "十一学校（普通班）", tier: "重点", refScore: 460 },
    { name: "育英学校", tier: "重点", refScore: 440 },
    { name: "五十七中", tier: "普通", refScore: 405 },
  ],
  西城区: [
    { name: "北师大实验中学", tier: "顶尖", refScore: 490 },
    { name: "北京四中", tier: "顶尖", refScore: 480 },
    { name: "北京八中", tier: "顶尖", refScore: 475 },
    { name: "北师大附中", tier: "重点", refScore: 465 },
    { name: "北师大二附中", tier: "重点", refScore: 460 },
    { name: "161中学", tier: "重点", refScore: 440 },
    { name: "三十五中", tier: "普通", refScore: 420 },
    { name: "十三中", tier: "普通", refScore: 415 },
  ],
  东城区: [
    { name: "北京二中", tier: "顶尖", refScore: 480 },
    { name: "171中学", tier: "顶尖", refScore: 465 },
    { name: "北京五中", tier: "重点", refScore: 455 },
    { name: "汇文中学", tier: "重点", refScore: 445 },
    { name: "广渠门中学", tier: "重点", refScore: 440 },
    { name: "东直门中学", tier: "重点", refScore: 425 },
    { name: "景山学校", tier: "普通", refScore: 410 },
    { name: "166中学", tier: "普通", refScore: 400 },
  ],
};

export const TIER_LABELS: Record<School["tier"], string> = {
  顶尖: "顶尖名校",
  重点: "区重点",
  普通: "普通高中",
  保底: "保底校",
};

/** 6 科满分 */
export const SUBJECT_MAX: Record<string, number> = {
  语文: 100,
  数学: 100,
  英语: 100,
  物理: 80,
  道法: 80,
  体育: 50,
};

export const TOTAL_MAX = 510;

/** 计算中考倒计时天数 */
export function daysUntilZhongkao(): number {
  const examDate = new Date("2026-06-24");
  const today = new Date();
  return Math.max(
    1,
    Math.ceil((examDate.getTime() - today.getTime()) / (1000 * 60 * 60 * 24))
  );
}

export interface SchoolMatch extends School {
  category: "冲刺" | "稳妥" | "保底";
  gap: number; // 正数=需要提分，负数=已超过
}

/** 根据总分匹配学校 */
export function matchSchools(district: string, totalScore: number): SchoolMatch[] {
  const schools = SCHOOLS_BY_DISTRICT[district as District] || [];
  return schools
    .map((s) => {
      const gap = s.refScore - totalScore;
      let category: SchoolMatch["category"];
      if (gap > 30) category = "冲刺";
      else if (gap > 0) category = "稳妥";
      else category = "保底";
      return { ...s, category, gap };
    })
    .sort((a, b) => b.refScore - a.refScore);
}
