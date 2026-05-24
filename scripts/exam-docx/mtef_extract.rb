#!/usr/bin/env ruby
# 批量 MTEF → MathML
# 用法: ruby mtef_extract.rb <oleObject*.bin glob> > mathml.json
# 输出 JSON 数组 [{file, mathml | error}, ...]
require 'mathtype_to_mathml'
require 'json'

results = []
ARGV.each do |f|
  begin
    mml = MathTypeToMathML::Converter.new(f).convert.to_s
    results << { 'file' => File.basename(f), 'mathml' => mml }
  rescue => e
    results << { 'file' => File.basename(f), 'error' => e.message[0..100] }
  end
end
STDOUT.puts JSON.generate(results)
