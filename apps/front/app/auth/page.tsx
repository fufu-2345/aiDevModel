"use client";

import React, { useState } from "react";

export default function AuthPage() {
  const [isLogin, setIsLogin] = useState(true);
  const [isLoading, setIsLoading] = useState(false);

  const [formData, setFormData] = useState({
    email: "",
    password: "",
    confirmPassword: "",
  });

  const handleInputChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    const { name, value } = e.target;
    setFormData((prev) => ({
      ...prev,
      [name]: value,
    }));
  };

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setIsLoading(true);

    if (!isLogin && formData.password !== formData.confirmPassword) {
      alert("Passwords do not match!");
      setIsLoading(false);
      return;
    }

    try {
      const response = await fetch("/api/auth", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          action: isLogin ? "login" : "signup",
          ...formData,
        }),
      });

      const data = await response.json();

      if (data.success) {
        alert(data.message);
      } else {
        alert(data.message || "Something went wrong");
      }
    } catch (error) {
      console.error("Error:", error);
      alert(
        `[Demo Mode] Request Sent:\nAction: ${isLogin ? "Login" : "Sign Up"}\nEmail: ${formData.email}\nPassword: ${formData.password}`,
      );
    } finally {
      setIsLoading(false);
    }
  };

  const toggleForm = () => {
    setIsLogin(!isLogin);
    setFormData((prev) => ({ ...prev, password: "", confirmPassword: "" }));
  };

  return (
    <div className="relative w-full h-screen overflow-hidden font-sans text-white">
      <div
        className="absolute inset-0 z-0 bg-cover bg-center bg-no-repeat"
        style={{
          backgroundImage: "url('/pic/bg.png')",
        }}
      >
        <div className="absolute inset-0 bg-black/20"></div>
      </div>
      <div
        className={`
        relative z-10 h-full w-full md:w-[500px] 
        bg-slate-900/40 backdrop-blur-xl
        border-r border-white/10 shadow-2xl
        flex flex-col pt-32 px-12 sm:px-20
        transition-all duration-500 ease-in-out
        ${isLogin ? "rounded-r-[4rem]" : "rounded-r-[4rem]"}
      `}
      >
        <div className="mb-12">
          <h1 className="text-6xl font-bold tracking-wide drop-shadow-[0_0_15px_rgba(244,114,182,0.6)] text-transparent bg-clip-text bg-gradient-to-br from-pink-200 via-pink-300 to-pink-400 py-2 leading-tight">
            {isLogin ? "Welcome" : "Sign Up"}
          </h1>
        </div>

        <form className="space-y-10" onSubmit={handleSubmit}>
          <div className="relative group animate-fade-in-left">
            <input
              type="email"
              name="email"
              value={formData.email}
              onChange={handleInputChange}
              placeholder="Email Address"
              className="w-full bg-transparent border-b border-gray-400 py-2 pr-8 text-white placeholder-gray-400 focus:outline-none focus:border-pink-300 transition-colors duration-300"
              required
            />

            <svg
              xmlns="http://www.w3.org/2000/svg"
              viewBox="0 0 24 24"
              fill="none"
              stroke="currentColor"
              strokeWidth="2"
              strokeLinecap="round"
              strokeLinejoin="round"
              className="absolute right-0 top-2 text-gray-400 w-5 h-5 group-focus-within:text-pink-300 transition-colors"
            >
              <rect width="20" height="16" x="2" y="4" rx="2" />
              <path d="m22 7-8.97 5.7a1.94 1.94 0 0 1-2.06 0L2 7" />
            </svg>
          </div>

          {!isLogin && (
            <div
              className="relative group animate-fade-in-left"
              style={{ animationDelay: "0.1s" }}
            >
              <svg
                xmlns="http://www.w3.org/2000/svg"
                viewBox="0 0 24 24"
                fill="none"
                stroke="currentColor"
                strokeWidth="2"
                strokeLinecap="round"
                strokeLinejoin="round"
                className="absolute right-0 top-2 text-gray-400 w-5 h-5 group-focus-within:text-pink-300 transition-colors"
              >
                <path d="M19 21v-2a4 4 0 0 0-4-4H9a4 4 0 0 0-4 4v2" />
                <circle cx="12" cy="7" r="4" />
              </svg>
            </div>
          )}

          <div
            className="relative group animate-fade-in-left"
            style={{ animationDelay: "0.2s" }}
          >
            <input
              type="password"
              name="password"
              value={formData.password}
              onChange={handleInputChange}
              placeholder="Password"
              className="w-full bg-transparent border-b border-gray-400 py-2 pr-8 text-white placeholder-gray-400 focus:outline-none focus:border-pink-300 transition-colors duration-300"
              required
            />
            <svg
              xmlns="http://www.w3.org/2000/svg"
              viewBox="0 0 24 24"
              fill="none"
              stroke="currentColor"
              strokeWidth="2"
              strokeLinecap="round"
              strokeLinejoin="round"
              className="absolute right-0 top-2 text-gray-400 w-5 h-5 group-focus-within:text-pink-300 transition-colors"
            >
              <rect width="18" height="11" x="3" y="11" rx="2" ry="2" />
              <path d="M7 11V7a5 5 0 0 1 10 0v4" />
            </svg>
          </div>

          {!isLogin && (
            <div
              className="relative group animate-fade-in-left"
              style={{ animationDelay: "0.3s" }}
            >
              <input
                type="password"
                name="confirmPassword"
                value={formData.confirmPassword}
                onChange={handleInputChange}
                placeholder="Confirm Password"
                className="w-full bg-transparent border-b border-gray-400 py-2 pr-8 text-white placeholder-gray-400 focus:outline-none focus:border-pink-300 transition-colors duration-300"
                required={!isLogin}
              />
              <svg
                xmlns="http://www.w3.org/2000/svg"
                viewBox="0 0 24 24"
                fill="none"
                stroke="currentColor"
                strokeWidth="2"
                strokeLinecap="round"
                strokeLinejoin="round"
                className="absolute right-0 top-2 text-gray-400 w-5 h-5 group-focus-within:text-pink-300 transition-colors"
              >
                <rect width="18" height="11" x="3" y="11" rx="2" ry="2" />
                <path d="M7 11V7a5 5 0 0 1 10 0v4" />
              </svg>
            </div>
          )}
        </form>

        <div className="mt-16 space-y-6">
          <button
            type="submit"
            onClick={handleSubmit}
            disabled={isLoading}
            className="w-full py-3 px-6 rounded-full bg-gradient-to-r from-gray-50/80 to-gray-300/50 hover:from-gray-300 hover:to-gray-400 text-white font-semibold shadow-[0_0_20px_rgba(244,114,182,0.4)] hover:shadow-[0_0_25px_rgba(244,114,182,0.6)] transform hover:scale-[1.02] disabled:opacity-70 disabled:cursor-not-allowed transition-all duration-300 flex items-center justify-center gap-2 group"
          >
            {isLoading ? (
              <span className="animate-pulse">Loading...</span>
            ) : (
              <>
                {isLogin ? "Login" : "Sign Up"}
                <svg
                  xmlns="http://www.w3.org/2000/svg"
                  viewBox="0 0 24 24"
                  fill="none"
                  stroke="currentColor"
                  strokeWidth="2"
                  strokeLinecap="round"
                  strokeLinejoin="round"
                  className="w-4 h-4 opacity-0-translate-x-2 group-hover:opacity-100 group-hover:translate-x-0 transition-all duration-300"
                >
                  <path d="M5 12h14" />
                  <path d="m12 5 7 7-7 7" />
                </svg>
              </>
            )}
          </button>

          <div className="text-center text-sm text-gray-400">
            {isLogin ? (
              <p>
                Don't have an account?{" "}
                <button
                  onClick={toggleForm}
                  className="text-gray-300 hover:text-pink-200 underline underline-offset-4 transition-colors font-medium"
                >
                  Sign up now
                </button>
              </p>
            ) : (
              <p>
                Have an account?{" "}
                <button
                  onClick={toggleForm}
                  className="text-gray-300 hover:text-pink-200 underline underline-offset-4 transition-colors font-medium"
                >
                  Sign in here
                </button>
              </p>
            )}
          </div>
        </div>
      </div>

      <style jsx global>{`
        @keyframes fadeInUps {
          from {
            opacity: 0;
            transform: translateY(10px);
          }
          to {
            opacity: 1;
            transform: translateY(0);
          }
        }
        @keyframes fadeInLeft {
          from {
            opacity: 0;
            transform: translateX(-10px);
          }
          to {
            opacity: 1;
            transform: translateX(0);
          }
        }
        .animate-fade-in-up {
          animation: fadeInUps 0.5s ease-out forwards;
        }
        .animate-fade-in-left {
          animation: fadeInLeft 0.5s ease-out forwards;
        }
      `}</style>
    </div>
  );
}
