#!/usr/bin/env ruby
# 批量 MTEF → MathML
# 用法: ruby mtef_extract.rb <oleObject*.bin glob> > mathml.json
# 输出 JSON 数组 [{file, mathml | error}, ...]
require 'mathtype_to_mathml'
require 'json'

# ─── mathtype gem v0.0.8 patch: MTEF FUTURE records ≥100 ───────────────────
# Gem 源码注释明确写了 spec：record_type ≥100 都是 FUTURE 格式（uint8 length
# + skip 这么多字节）。但 gem 只硬编码了 record_future 100，碰到 MathType 6+
# 新版输出的 101/102/... 直接抛 "selection 'N' does not exist" 异常。
#
# 试过 reopen Mathtype::Payload 加 :default，但 BinData 把 choices 表 sanitize
# 进了 SanitizedChoices 缓存（NamedRecord 类定义时锁定），reopen 加 :default
# 不进缓存。改在 BinData::Choice 的解析器层兜底：未识别 selection → 当
# RecordFuture 处理（spec 兼容路径）。
require 'bindata'
module BinData
  class Choice
    private
    alias_method :_orig_instantiate_choice, :instantiate_choice
    def instantiate_choice(selection)
      proto = get_parameter(:choices)[selection]
      if proto.nil?
        # MTEF FUTURE 兜底：未识别 record_type ≥100 全部按 RecordFuture 跳过
        proto = get_parameter(:choices)[100]
      end
      if proto.nil?
        return _orig_instantiate_choice(selection)  # 让原 IndexError 抛
      end
      proto.instantiate(nil, self)
    end
  end
end

results = []
# 文件列表：优先 ARGV；若空（或第一个是 "-"）从 STDIN 一行一个读，绕开
# OS argv 上限（>1000 OLE 时 ARGV 会 E2BIG 失败，比如 mentougou 1196 个）。
files = if ARGV.empty? || ARGV.first == '-'
  STDIN.each_line.map(&:chomp).reject(&:empty?)
else
  ARGV
end
files.each do |f|
  begin
    mml = MathTypeToMathML::Converter.new(f).convert.to_s
    results << { 'file' => File.basename(f), 'mathml' => mml }
  rescue => e
    results << { 'file' => File.basename(f), 'error' => e.message[0..100] }
  end
end
STDOUT.puts JSON.generate(results)
