#!/usr/bin/env python3
"""简称 → 正名 解析器(给 build_full_district 用)。

目标:把各区历史 yaml / T3 录取线里用的「简称」(人大附中)安全映射到
统招计划 codes 里的「正名」(中国人民大学附属中学),从而把 录取线/坐标/专业
join 到同一所学校。

安全原则(第一原则:绝不错配):
  exact → 大学前缀展开+数字归一后唯一子串 → 人工 override → 否则**未命中不猜**。
未命中的学校 build 时会被标记(unresolved),宁可缺数据,绝不挂错校。
"""
import re

# 大学/机构 简称前缀 → 正名前缀(用于把"人大附中"展开成含"中国人民大学"的形式再做子串)
UNIV = {
    "人大": "中国人民大学", "清华": "清华大学", "北大": "北京大学",
    "北师大": "北京师范大学", "首师大": "首都师范大学", "首师附": "首都师范大学附属",
    "北航": "北京航空航天大学", "北理工": "北京理工大学", "理工": "北京理工大学",
    "交大": "北京交通大学", "农大": "中国农业大学", "北外": "北京外国语大学",
    "地大": "中国地质大学", "科大": "中国科学院", "邮电": "北京邮电大学",
    "工大": "北京工业大学", "二外": "北京第二外国语学院",
}

# 中文数字 → 阿拉伯(用于 101/十一/一〇一 等编号校归一)
CN_DIGIT = {"〇": "0", "零": "0", "一": "1", "二": "2", "三": "3", "四": "4",
            "五": "5", "六": "6", "七": "7", "八": "8", "九": "9"}


def _arabicize(s: str) -> str:
    """把校名里的中文数字段转成阿拉伯,处理 十/十X/X十X(限两位,够中学编号用)。
    例:第一〇一 → 第101;第十三 → 第13;第二十 → 第20;第三十一 → 第31。"""
    def conv(m):
        seg = m.group(0)
        if "十" in seg:
            a, _, b = seg.partition("十")
            tens = CN_DIGIT.get(a, "1") if a else "1"
            ones = CN_DIGIT.get(b, "0") if b else "0"
            return str(int(tens) * 10 + int(ones))
        return "".join(CN_DIGIT.get(c, c) for c in seg)
    return re.sub(r"[〇零一二三四五六七八九十]+", conv, s)


_DROP = "北京中学校分院部第市区立完全日制普通高级初级实验·•・()（）  　"


def _norm(s: str) -> str:
    s = _arabicize(s or "")
    return re.sub(f"[{re.escape(_DROP)}]", "", s)


def _expand(s: str) -> str:
    """简称里的大学前缀展开为全称(就长度最长的前缀匹配一次)。"""
    for k in sorted(UNIV, key=len, reverse=True):
        if s.startswith(k):
            return UNIV[k] + s[len(k):]
        if k in s:
            return s.replace(k, UNIV[k], 1)
    return s


def build_resolver(zheng_names, overrides=None, snm=None):
    """zheng_names: 该区正名列表。返回 resolve(简称)->正名|None。
    snm: {简称:正名} 来自 score_name_mapping conf>=1.0(可选)。
    overrides: {简称:正名} 人工兜底(优先级最高之一,但仍校验正名∈zheng)。"""
    overrides = overrides or {}
    snm = snm or {}
    zset = set(zheng_names)
    znorm = {}
    for z in zheng_names:
        znorm.setdefault(_norm(z), z)
        znorm.setdefault(_norm(_expand(z)), z)

    def resolve(short):
        if not short:
            return None
        if short in zset:
            return short
        if short in overrides and overrides[short] in zset:
            return overrides[short]
        if short in snm and snm[short] in zset:
            return snm[short]
        for cand in (short, _expand(short)):
            nc = _norm(cand)
            if nc in znorm:
                return znorm[nc]
        # 不做模糊子串(会错配,如多个"X附中"撞到同一正名);未命中交 override 或标记
        return None

    return resolve
