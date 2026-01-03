"use client";

import React, { useState } from "react";
import axios from "axios";

// --- Interfaces & Types ---
interface IconProps {
  size?: number | string;
  className?: string;
}

interface RagResult {
  type: "success" | "error";
  data?: any;
  message?: string;
}

interface GenPromptResponse {
  sd_prompt: string;
  // add other fields if API returns more
}

// --- Icons (Inline SVGs to avoid dependencies) ---
const PlayIcon: React.FC<IconProps> = ({ size = 20, className = "" }) => (
  <svg
    width={size}
    height={size}
    viewBox="0 0 24 24"
    fill="none"
    stroke="currentColor"
    strokeWidth="2"
    strokeLinecap="round"
    strokeLinejoin="round"
    className={className}
  >
    <polygon points="5 3 19 12 5 21 5 3"></polygon>
  </svg>
);
const ImageIcon: React.FC<IconProps> = ({ size = 20, className = "" }) => (
  <svg
    width={size}
    height={size}
    viewBox="0 0 24 24"
    fill="none"
    stroke="currentColor"
    strokeWidth="2"
    strokeLinecap="round"
    strokeLinejoin="round"
    className={className}
  >
    <rect x="3" y="3" width="18" height="18" rx="2" ry="2"></rect>
    <circle cx="8.5" cy="8.5" r="1.5"></circle>
    <polyline points="21 15 16 10 5 21"></polyline>
  </svg>
);
const CopyIcon: React.FC<IconProps> = ({ size = 20, className = "" }) => (
  <svg
    width={size}
    height={size}
    viewBox="0 0 24 24"
    fill="none"
    stroke="currentColor"
    strokeWidth="2"
    strokeLinecap="round"
    strokeLinejoin="round"
    className={className}
  >
    <rect x="9" y="9" width="13" height="13" rx="2" ry="2"></rect>
    <path d="M5 15H4a2 2 0 0 1-2-2V4a2 2 0 0 1 2-2h9a2 2 0 0 1 2 2v1"></path>
  </svg>
);
const CheckIcon: React.FC<IconProps> = ({ size = 20, className = "" }) => (
  <svg
    width={size}
    height={size}
    viewBox="0 0 24 24"
    fill="none"
    stroke="currentColor"
    strokeWidth="2"
    strokeLinecap="round"
    strokeLinejoin="round"
    className={className}
  >
    <polyline points="20 6 9 17 4 12"></polyline>
  </svg>
);
const AlertIcon: React.FC<IconProps> = ({ size = 20, className = "" }) => (
  <svg
    width={size}
    height={size}
    viewBox="0 0 24 24"
    fill="none"
    stroke="currentColor"
    strokeWidth="2"
    strokeLinecap="round"
    strokeLinejoin="round"
    className={className}
  >
    <circle cx="12" cy="12" r="10"></circle>
    <line x1="12" y1="8" x2="12" y2="12"></line>
    <line x1="12" y1="16" x2="12.01" y2="16"></line>
  </svg>
);
const SpinnerIcon: React.FC<IconProps> = ({ size = 20, className = "" }) => (
  <svg
    width={size}
    height={size}
    viewBox="0 0 24 24"
    fill="none"
    stroke="currentColor"
    strokeWidth="2"
    strokeLinecap="round"
    strokeLinejoin="round"
    className={className}
  >
    <path d="M21 12a9 9 0 1 1-6.219-8.56"></path>
  </svg>
);

export default function RAGTester() {
  // --- States with Types ---
  const [movieId, setMovieId] = useState<number>(1);
  const [ragLoading, setRagLoading] = useState<boolean>(false);
  const [ragResult, setRagResult] = useState<RagResult | null>(null);

  const [sceneQuery, setSceneQuery] = useState<string>(
    "หานลี่กำลังปรุงยาในถ้ำมืด"
  );
  const [promptLoading, setPromptLoading] = useState<boolean>(false);
  const [generatedPrompt, setGeneratedPrompt] = useState<string | null>(null);
  const [copySuccess, setCopySuccess] = useState<boolean>(false);

  // --- Configuration ---
  const API_BASE_URL = "http://localhost:8000"; // แก้เป็น Port Backend ของคุณ

  // --- 1. Function Trigger RAG ---
  const handleTriggerRAG = async () => {
    setRagLoading(true);
    setRagResult(null);
    try {
      // เรียก API จริง
      const res = await axios.post(
        `${API_BASE_URL}/movies/${movieId}/process-rag`
      );
      setRagResult({
        type: "success",
        data: res.data,
      });
    } catch (error: any) {
      console.error(error);
      setRagResult({
        type: "error",
        message: error.response?.data?.detail || "เชื่อมต่อ Backend ไม่ได้",
      });
    } finally {
      setRagLoading(false);
    }
  };

  // --- 2. Function Generate Prompt ---
  const handleGenPrompt = async () => {
    setPromptLoading(true);
    setGeneratedPrompt(null);
    try {
      // เรียก API จริง
      const res = await axios.post<GenPromptResponse>(
        `${API_BASE_URL}/gen-image-prompt?movie_id=${movieId}&scene_query=${sceneQuery}`
      );
      setGeneratedPrompt(res.data.sd_prompt);
    } catch (error) {
      console.error(error);
      // Fallback: ถ้า Error จะโชว์ Mock Data ให้ดูเป็นตัวอย่าง
      alert("เชื่อมต่อ Backend ไม่ได้ จะแสดงผลลัพธ์ตัวอย่างแทน");
      setGeneratedPrompt(
        "(Han Li:1.2), black hair, plain face, wearing green robe, ancient chinese alchemy lab, dark cave background, floating herbs, magical fire effect, masterpiece, best quality, 8k"
      );
    } finally {
      setPromptLoading(false);
    }
  };

  // --- Helper: Copy to Clipboard ---
  const copyToClipboard = () => {
    if (generatedPrompt) {
      navigator.clipboard.writeText(generatedPrompt);
      setCopySuccess(true);
      setTimeout(() => setCopySuccess(false), 2000);
    }
  };

  return (
    <div className="min-h-screen bg-slate-50 p-8 font-sans text-slate-800">
      <div className="max-w-3xl mx-auto space-y-10">
        {/* Header */}
        <div className="text-center space-y-2">
          <h1 className="text-3xl font-bold text-indigo-700">
            🛠️ RAG & AI Art Tester
          </h1>
          <p className="text-slate-500">
            เครื่องมือทดสอบระบบนิยาย AI (Backend Connection)
          </p>
        </div>

        {/* ----------------------------------------------------------
            SECTION 1: RAG PROCESSOR
           ---------------------------------------------------------- */}
        <div className="bg-white rounded-2xl shadow-sm border border-slate-200 overflow-hidden">
          <div className="bg-indigo-600 px-6 py-4 flex justify-between items-center">
            <h2 className="text-white font-semibold flex items-center gap-2">
              <PlayIcon size={20} /> 1. สั่งประมวลผล RAG (Process Movie)
            </h2>
            <span className="text-xs bg-indigo-500 text-white px-2 py-1 rounded-md font-mono">
              POST /process-rag
            </span>
          </div>

          <div className="p-6 space-y-4">
            <p className="text-sm text-slate-500">
              สั่งให้ Worker เบื้องหลังอ่านเนื้อหาจาก Database {"->"} ตัดคำ{" "}
              {"->"} สร้าง Vector Index
            </p>

            <div className="flex gap-4 items-end">
              <div className="flex-1">
                <label className="block text-sm font-medium text-slate-700 mb-1">
                  Movie ID
                </label>
                <input
                  type="number"
                  value={movieId}
                  onChange={(e) => setMovieId(parseInt(e.target.value) || 0)}
                  className="w-full px-4 py-2 border border-slate-300 rounded-lg focus:ring-2 focus:ring-indigo-500 outline-none transition"
                />
              </div>
              <button
                onClick={handleTriggerRAG}
                disabled={ragLoading}
                className="bg-indigo-600 hover:bg-indigo-700 disabled:bg-indigo-300 text-white font-medium py-2 px-6 rounded-lg transition flex items-center gap-2 h-[42px]"
              >
                {ragLoading ? (
                  <SpinnerIcon className="animate-spin" size={18} />
                ) : (
                  "เริ่ม Process"
                )}
              </button>
            </div>

            {/* Result Box */}
            {ragResult && (
              <div
                className={`p-4 rounded-lg border ${ragResult.type === "success" ? "bg-green-50 border-green-200 text-green-800" : "bg-red-50 border-red-200 text-red-800"}`}
              >
                <h3 className="font-bold text-sm mb-1">
                  {ragResult.type === "success"
                    ? "✅ ส่งคำสั่งสำเร็จ"
                    : "❌ เกิดข้อผิดพลาด"}
                </h3>
                <pre className="text-xs whitespace-pre-wrap font-mono">
                  {JSON.stringify(ragResult.data || ragResult.message, null, 2)}
                </pre>
              </div>
            )}
          </div>
        </div>

        {/* ----------------------------------------------------------
            SECTION 2: IMAGE PROMPT GENERATOR
           ---------------------------------------------------------- */}
        <div className="bg-white rounded-2xl shadow-sm border border-slate-200 overflow-hidden">
          <div className="bg-pink-600 px-6 py-4 flex justify-between items-center">
            <h2 className="text-white font-semibold flex items-center gap-2">
              <ImageIcon size={20} /> 2. สร้าง Prompt รูปภาพ (Stability Matrix)
            </h2>
            <span className="text-xs bg-pink-500 text-white px-2 py-1 rounded-md font-mono">
              POST /gen-image-prompt
            </span>
          </div>

          <div className="p-6 space-y-4">
            <p className="text-sm text-slate-500">
              ทดสอบดึงข้อมูล Visual Tags ของตัวละครมาผสมกับฉาก
              เพื่อความต่อเนื่องของหน้าตา (Consistency)
            </p>

            <div>
              <label className="block text-sm font-medium text-slate-700 mb-1">
                บรรยายฉาก (Scene Description)
              </label>
              <textarea
                rows={3}
                value={sceneQuery}
                onChange={(e) => setSceneQuery(e.target.value)}
                className="w-full px-4 py-2 border border-slate-300 rounded-lg focus:ring-2 focus:ring-pink-500 outline-none transition"
                placeholder="เช่น หานลี่กำลังต่อสู้กับสัตว์อสูร..."
              />
            </div>

            <button
              onClick={handleGenPrompt}
              disabled={promptLoading}
              className="w-full bg-pink-600 hover:bg-pink-700 disabled:bg-pink-300 text-white font-medium py-2 rounded-lg transition flex justify-center items-center gap-2"
            >
              {promptLoading ? (
                <>
                  <SpinnerIcon className="animate-spin" size={18} /> กำลังสร้าง
                  Prompt...
                </>
              ) : (
                <>
                  <ImageIcon size={18} /> Generate SD Prompt
                </>
              )}
            </button>

            {/* Prompt Result Display */}
            {generatedPrompt && (
              <div className="mt-6 space-y-2">
                <div className="flex justify-between items-center">
                  <span className="text-sm font-bold text-slate-700">
                    ผลลัพธ์ (Copy ไปวางใน Stability Matrix):
                  </span>
                  <button
                    onClick={copyToClipboard}
                    className="text-xs flex items-center gap-1 text-slate-500 hover:text-indigo-600 transition"
                  >
                    {copySuccess ? (
                      <CheckIcon size={14} className="text-green-600" />
                    ) : (
                      <CopyIcon size={14} />
                    )}
                    {copySuccess ? "Copied!" : "Copy"}
                  </button>
                </div>

                <div className="relative group">
                  <div className="p-4 bg-slate-900 text-green-400 font-mono text-sm rounded-lg border border-slate-700 break-words leading-relaxed shadow-inner min-h-[100px]">
                    {generatedPrompt}
                  </div>
                </div>

                {/* Example Explanation */}
                <div className="p-3 bg-blue-50 border border-blue-100 rounded-lg flex gap-3">
                  <AlertIcon
                    className="text-blue-500 flex-shrink-0"
                    size={20}
                  />
                  <div className="text-xs text-blue-800 space-y-1">
                    <p className="font-bold">สังเกตผลลัพธ์:</p>
                    <p>
                      1. ระบบจะดึง <b>Visual Tags</b> มาแปะให้ (เช่น{" "}
                      <code>(Han Li:1.2), black hair, green robe</code>)
                    </p>
                    <p>
                      2. ตามด้วย <b>Action</b> ที่เราพิมพ์ไป (เช่น{" "}
                      <code>alchemy lab, floating herbs</code>)
                    </p>
                    <p>
                      3. ปิดท้ายด้วย <b>Quality Tags</b> (เช่น{" "}
                      <code>masterpiece, 8k</code>)
                    </p>
                  </div>
                </div>
              </div>
            )}
          </div>
        </div>
      </div>
    </div>
  );
}
