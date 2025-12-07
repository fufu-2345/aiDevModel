'use client';

import { useState, ChangeEvent, FormEvent } from 'react';

interface ChapterData {
  chapter: number;
  start_page: number;
  end_page: number;
}
interface MapChaptersResponse {
  chapters: ChapterData[];
}
interface ApiError {
  detail: string;
}

export default function MapChaptersPage() {
  const [selectedFile, setSelectedFile] = useState<File | null>(null);
  const [startChapter, setStartChapter] = useState<string | number>(1);
  const [endChapter, setEndChapter] = useState<string | number>(10);
  const [mappedChapters, setMappedChapters] = useState<ChapterData[] | null>(null);
  const [isLoading, setIsLoading] = useState<boolean>(false);
  const [message, setMessage] = useState<string>('');
  const [executionTime, setExecutionTime] = useState<string | null>(null);

  const handleFileChange = (event: ChangeEvent<HTMLInputElement>) => {
    const file = event.target.files ? event.target.files[0] : null;
    if (file && file.type === 'application/pdf') {
      setSelectedFile(file);
      setMessage(`ไฟล์ที่เลือก: ${file.name}`);
      setExecutionTime(null);
    } else {
      setSelectedFile(null);
      setMessage('กรุณาเลือกเฉพาะไฟล์ PDF เท่านั้น');
    }
    setMappedChapters(null);
  };

  const handleSubmit = async (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    const startTime = performance.now();
    setIsLoading(true);
    setExecutionTime(null);
    setMessage('⏳ กำลังสแกนหา "ตอนที่..." กรุณารอสักครู่ (เร็วกว่าเดิมแน่นอน)...');

    if (!selectedFile) {
      setMessage('ลืมเลือกไฟล์ PDF ครับ');
      setIsLoading(false);
      return;
    }
    if (Number(startChapter) > Number(endChapter)) {
      setMessage('❌ ตอนเริ่มต้น ต้องน้อยกว่าหรือเท่ากับ ตอนสุดท้าย');
      setIsLoading(false);
      return;
    }

    const formData = new FormData();
    formData.append('file', selectedFile);
    formData.append('startChapter', String(startChapter));
    formData.append('endChapter', String(endChapter));

    try {
      const response = await fetch("http://localhost:8000/map-chapters/", {
        method: 'POST',
        body: formData,
      });
      if (!response.ok) {
        const errorData: ApiError = await response.json();
        throw new Error(errorData.detail || 'การประมวลผลล้มเหลว');
      }

      const result: MapChaptersResponse = await response.json();
      setExecutionTime(((performance.now() - startTime) / 1000).toFixed(3));
      setMappedChapters(result.chapters);

      if (result.chapters.length === 0) {
        setMessage(`⚠️ ไม่พบตอนที่ ${startChapter} - ${endChapter} ในไฟล์นี้ หรือรูปแบบหัวกระดาษไม่ตรง`);
      } else {
        setMessage(`✅ เรียบร้อย! พบทั้งหมด ${result.chapters.length} ตอน`);
      }
    } catch (error: any) {
      console.error('Error:', error);
      setMappedChapters(null);
      setExecutionTime(null);
      const errorMessage = error instanceof Error ? error.message : 'Unknown error';
      setMessage(`❌ เกิดข้อผิดพลาด: ${errorMessage}`);
    } finally {
      setIsLoading(false);
    }
  };

  return (
    <main className="flex flex-col items-center justify-start min-h-screen p-10 bg-slate-50">
      <div className="w-full max-w-3xl p-8 bg-white rounded-xl shadow-xl border border-slate-200">
        <h1 className="mb-2 text-3xl font-bold text-center text-blue-800">
          PDF Chapter Mapper
        </h1>
        <p className="mb-6 text-center text-gray-500">
          สแกนหาเลขหน้าของแต่ละตอนโดยอัตโนมัติด้วย AI
        </p>
        <form onSubmit={handleSubmit} className="flex flex-col space-y-5">
          <div className="p-4 border-2 border-dashed border-blue-200 rounded-lg bg-blue-50/50">
            <label className="block mb-2 text-lg font-medium text-blue-900">
              📂 1. อัปโหลดไฟล์นิยาย (PDF)
            </label>
            <input
              type="file"
              accept=".pdf"
              onChange={handleFileChange}
              disabled={isLoading}
              className="w-full text-sm text-slate-500
                file:mr-4 file:py-2 file:px-4
                file:rounded-full file:border-0
                file:text-sm file:font-semibold
                file:bg-blue-600 file:text-white
                hover:file:bg-blue-700
                cursor-pointer"
            />
          </div>

          <div className="flex space-x-4">
            <div className="w-1/2">
              <label className="block mb-1 font-medium text-gray-700">🔍 เริ่มหาจาก "ตอนที่":</label>
              <input
                type="number"
                min="1"
                value={startChapter}
                onChange={(e) => setStartChapter(e.target.value)}
                className="w-full p-2 border border-gray-300 rounded-lg text-center focus:ring-2 focus:ring-blue-500 outline-none"
              />
            </div>
            <div className="w-1/2">
              <label className="block mb-1 font-medium text-gray-700">ถึง "ตอนที่":</label>
              <input
                type="number"
                min="1"
                value={endChapter}
                onChange={(e) => setEndChapter(e.target.value)}
                className="w-full p-2 border border-gray-300 rounded-lg text-center focus:ring-2 focus:ring-blue-500 outline-none"
              />
            </div>
          </div>
          <button
            type="submit"
            disabled={!selectedFile || isLoading}
            className={`w-full py-3 text-white font-bold rounded-lg transition-all duration-200 shadow-md
              ${!selectedFile || isLoading
                ? 'bg-gray-400 cursor-not-allowed'
                : 'bg-blue-600 hover:bg-blue-700 hover:shadow-lg transform active:scale-95'
              }`}
          >
            {isLoading ? '🤖 AI กำลังสแกนหัวกระดาษ...' : '🚀 เริ่มค้นหาเลขหน้า'}
          </button>
        </form>

        <hr className="my-6 border-gray-200" />
        <div className="text-center mb-4">
          <span className={`inline-block px-4 py-2 rounded-full font-medium text-sm
             ${isLoading ? 'bg-yellow-100 text-yellow-800 animate-pulse' :
              message.includes('❌') ? 'bg-red-100 text-red-800' :
                message.includes('✅') ? 'bg-green-100 text-green-800' : 'bg-gray-100 text-gray-600'
            }`}>
            {message || 'รอคำสั่ง...'}
          </span>
        </div>

        {mappedChapters && mappedChapters.length > 0 && (
          <div className="mt-6 animation-fade-in-up">
            <div className="flex justify-between items-center mb-3">
              <h2 className="text-xl font-bold text-gray-800">
                📊 ผลลัพธ์การค้นหา
              </h2>
              {executionTime && (
                <span className="text-xs text-gray-500 font-mono">
                  ⏱️ ใช้เวลา: {executionTime} วินาที
                </span>
              )}
            </div>

            <div className="overflow-hidden border border-gray-200 rounded-lg shadow-sm">
              <table className="w-full text-left border-collapse bg-white">
                <thead className="bg-gray-50">
                  <tr>
                    <th className="p-3 text-sm font-semibold text-gray-600 uppercase tracking-wider border-b">ตอนที่</th>
                    <th className="p-3 text-sm font-semibold text-gray-600 uppercase tracking-wider border-b text-center">หน้าเริ่มต้น</th>
                    <th className="p-3 text-sm font-semibold text-gray-600 uppercase tracking-wider border-b text-center">หน้าสิ้นสุด</th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-gray-200">
                  {mappedChapters.map((chap, index) => (
                    <tr key={index} className="hover:bg-blue-50 transition-colors">
                      <td className="p-3 font-medium text-blue-700">
                        ตอนที่ {chap.chapter}
                      </td>
                      <td className="p-3 text-center text-gray-700">
                        {chap.start_page}
                      </td>
                      <td className="p-3 text-center text-gray-700">
                        {chap.end_page}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>

            <div className="mt-4">
              <details className="text-xs text-gray-400 cursor-pointer">
                <summary>ดูข้อมูล JSON ดิบ</summary>
                <pre className="mt-2 p-2 bg-gray-800 text-green-400 rounded overflow-x-auto">
                  {JSON.stringify(mappedChapters, null, 2)}
                </pre>
              </details>
            </div>
          </div>
        )}
      </div>
    </main>
  );
}