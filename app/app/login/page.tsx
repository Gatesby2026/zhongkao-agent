"use client";

import { useState, useEffect, useRef } from "react";
import { useAuth } from "@/components/AuthProvider";
import Link from "next/link";

export default function LoginPage() {
  const { user, login } = useAuth();
  const [phone, setPhone] = useState("");
  const [code, setCode] = useState("");
  const [step, setStep] = useState<"phone" | "code">("phone");
  const [sending, setSending] = useState(false);
  const [verifying, setVerifying] = useState(false);
  const [countdown, setCountdown] = useState(0);
  const [error, setError] = useState("");
  const [devCode, setDevCode] = useState("");
  const codeInputRef = useRef<HTMLInputElement>(null);

  // 倒计时
  useEffect(() => {
    if (countdown <= 0) return;
    const timer = setTimeout(() => setCountdown(countdown - 1), 1000);
    return () => clearTimeout(timer);
  }, [countdown]);

  // 已登录跳转
  if (user) {
    return (
      <div className="min-h-screen bg-gray-50 flex items-center justify-center p-4">
        <div className="bg-white rounded-2xl shadow-sm border border-gray-200 p-8 w-full max-w-sm text-center">
          <div className="text-4xl mb-4">✅</div>
          <h2 className="text-xl font-bold text-gray-900 mb-2">已登录</h2>
          <p className="text-gray-500 mb-6">
            {user.nickname}，欢迎回来！
          </p>
          <Link
            href="/"
            className="inline-block px-6 py-2.5 bg-blue-600 text-white rounded-lg font-medium hover:bg-blue-700"
          >
            返回首页
          </Link>
        </div>
      </div>
    );
  }

  // 发送验证码
  const handleSendCode = async () => {
    if (!/^1[3-9]\d{9}$/.test(phone)) {
      setError("请输入正确的手机号");
      return;
    }

    setSending(true);
    setError("");
    setDevCode("");

    try {
      const res = await fetch("/api/auth/send-code", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ phone }),
      });
      const data = await res.json();

      if (data.success) {
        setStep("code");
        setCountdown(60);
        if (data.devCode) {
          setDevCode(data.devCode);
        }
        // 自动聚焦验证码输入框
        setTimeout(() => codeInputRef.current?.focus(), 100);
      } else {
        setError(data.message);
      }
    } catch {
      setError("网络错误，请稍后重试");
    } finally {
      setSending(false);
    }
  };

  // 验证登录
  const handleVerify = async () => {
    if (code.length !== 6) {
      setError("请输入 6 位验证码");
      return;
    }

    setVerifying(true);
    setError("");

    try {
      const res = await fetch("/api/auth/verify", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ phone, code }),
      });
      const data = await res.json();

      if (data.success) {
        login(data.token, data.user);
        // 登录成功后跳转首页
        window.location.href = "/";
      } else {
        setError(data.message);
      }
    } catch {
      setError("网络错误，请稍后重试");
    } finally {
      setVerifying(false);
    }
  };

  return (
    <div className="min-h-screen bg-gray-50 flex items-center justify-center p-4">
      <div className="bg-white rounded-2xl shadow-sm border border-gray-200 p-8 w-full max-w-sm">
        {/* 标题 */}
        <div className="text-center mb-8">
          <div className="text-4xl mb-3">🎯</div>
          <h1 className="text-xl font-bold text-gray-900">中考智能规划</h1>
          <p className="text-sm text-gray-500 mt-1">手机号验证码登录</p>
        </div>

        {/* 手机号输入 */}
        <div className="mb-4">
          <label className="block text-sm font-medium text-gray-700 mb-1.5">手机号</label>
          <input
            type="tel"
            maxLength={11}
            value={phone}
            onChange={(e) => {
              setPhone(e.target.value.replace(/\D/g, ""));
              setError("");
            }}
            onKeyDown={(e) => e.key === "Enter" && step === "phone" && handleSendCode()}
            placeholder="请输入手机号"
            className="w-full px-4 py-3 border border-gray-300 rounded-lg text-base focus:outline-none focus:ring-2 focus:ring-blue-500 focus:border-transparent"
            disabled={step === "code"}
          />
        </div>

        {/* 验证码输入 */}
        {step === "code" && (
          <div className="mb-4">
            <label className="block text-sm font-medium text-gray-700 mb-1.5">验证码</label>
            <div className="flex gap-3">
              <input
                ref={codeInputRef}
                type="text"
                inputMode="numeric"
                maxLength={6}
                value={code}
                onChange={(e) => {
                  setCode(e.target.value.replace(/\D/g, ""));
                  setError("");
                }}
                onKeyDown={(e) => e.key === "Enter" && handleVerify()}
                placeholder="6 位验证码"
                className="flex-1 px-4 py-3 border border-gray-300 rounded-lg text-base tracking-widest focus:outline-none focus:ring-2 focus:ring-blue-500 focus:border-transparent"
              />
              <button
                onClick={handleSendCode}
                disabled={countdown > 0 || sending}
                className="px-4 py-3 text-sm font-medium text-blue-600 border border-blue-300 rounded-lg hover:bg-blue-50 disabled:text-gray-400 disabled:border-gray-200 whitespace-nowrap"
              >
                {countdown > 0 ? `${countdown}s` : "重新发送"}
              </button>
            </div>

            {/* 开发模式验证码提示 */}
            {devCode && (
              <div className="mt-2 px-3 py-2 bg-yellow-50 border border-yellow-200 rounded-lg">
                <p className="text-xs text-yellow-700">
                  🔧 开发模式 — 验证码：<span className="font-mono font-bold text-yellow-900">{devCode}</span>
                </p>
              </div>
            )}
          </div>
        )}

        {/* 错误提示 */}
        {error && (
          <div className="mb-4 px-3 py-2 bg-red-50 border border-red-200 rounded-lg">
            <p className="text-sm text-red-600">{error}</p>
          </div>
        )}

        {/* 操作按钮 */}
        {step === "phone" ? (
          <button
            onClick={handleSendCode}
            disabled={phone.length !== 11 || sending}
            className="w-full py-3 bg-blue-600 text-white rounded-lg font-medium hover:bg-blue-700 disabled:bg-gray-300 disabled:cursor-not-allowed transition-colors"
          >
            {sending ? "发送中..." : "获取验证码"}
          </button>
        ) : (
          <button
            onClick={handleVerify}
            disabled={code.length !== 6 || verifying}
            className="w-full py-3 bg-blue-600 text-white rounded-lg font-medium hover:bg-blue-700 disabled:bg-gray-300 disabled:cursor-not-allowed transition-colors"
          >
            {verifying ? "验证中..." : "登录"}
          </button>
        )}

        {/* 修改手机号 */}
        {step === "code" && (
          <button
            onClick={() => {
              setStep("phone");
              setCode("");
              setDevCode("");
              setError("");
            }}
            className="w-full mt-3 py-2 text-sm text-gray-500 hover:text-gray-700"
          >
            &larr; 修改手机号
          </button>
        )}

        {/* 底部提示 */}
        <p className="mt-6 text-center text-xs text-gray-400">
          未注册的手机号将自动创建账号
        </p>

        {/* 返回首页 */}
        <div className="mt-4 text-center">
          <Link href="/" className="text-sm text-gray-500 hover:text-blue-600">
            返回首页
          </Link>
        </div>
      </div>
    </div>
  );
}
