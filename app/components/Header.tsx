"use client";

import Link from "next/link";
import { useAuth } from "./AuthProvider";
import { useState } from "react";

export function Header() {
  const { user, logout, loading } = useAuth();
  const [showMenu, setShowMenu] = useState(false);

  return (
    <header className="bg-white border-b border-gray-200 sticky top-0 z-50">
      <div className="max-w-2xl mx-auto px-4 h-12 flex items-center justify-between">
        {/* Logo */}
        <Link href="/" className="flex items-center gap-2 text-lg font-bold text-gray-900">
          <span>🎯</span>
          <span className="text-sm">中考智能规划</span>
        </Link>

        {/* 右侧：登录状态 */}
        <div className="relative">
          {loading ? (
            <div className="w-8 h-8 rounded-full bg-gray-100 animate-pulse" />
          ) : user ? (
            <>
              <button
                onClick={() => setShowMenu(!showMenu)}
                className="flex items-center gap-2 px-3 py-1.5 rounded-full bg-blue-50 hover:bg-blue-100 transition-colors"
              >
                <div className="w-6 h-6 rounded-full bg-blue-500 text-white text-xs flex items-center justify-center font-medium">
                  {user.nickname.slice(-1)}
                </div>
                <span className="text-sm text-gray-700 max-w-[80px] truncate">{user.nickname}</span>
              </button>

              {showMenu && (
                <>
                  <div className="fixed inset-0" onClick={() => setShowMenu(false)} />
                  <div className="absolute right-0 top-full mt-1 w-48 bg-white rounded-lg shadow-lg border border-gray-200 py-1 z-50">
                    <div className="px-4 py-2 border-b border-gray-100">
                      <p className="text-sm font-medium text-gray-900">{user.nickname}</p>
                      <p className="text-xs text-gray-500">{user.phone.replace(/(\d{3})\d{4}(\d{4})/, "$1****$2")}</p>
                    </div>
                    <Link
                      href="/profile"
                      className="block px-4 py-2 text-sm text-gray-700 hover:bg-gray-50"
                      onClick={() => setShowMenu(false)}
                    >
                      📊 我的画像
                    </Link>
                    <button
                      onClick={() => {
                        logout();
                        setShowMenu(false);
                      }}
                      className="w-full text-left px-4 py-2 text-sm text-red-600 hover:bg-red-50"
                    >
                      退出登录
                    </button>
                  </div>
                </>
              )}
            </>
          ) : (
            <Link
              href="/login"
              className="px-4 py-1.5 text-sm font-medium text-white bg-blue-600 rounded-full hover:bg-blue-700 transition-colors"
            >
              登录
            </Link>
          )}
        </div>
      </div>
    </header>
  );
}
