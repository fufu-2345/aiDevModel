'use client';

import { useState } from 'react';

export default function ProcessPdfPage() {
  const [selectedFile, setSelectedFile] = useState(null);
  const [outputText, setOutputText] = useState('');
  const [isLoading, setIsLoading] = useState(false);
  const [message, setMessage] = useState('');
  const FASTAPI_URL = 'http://localhost:8000/process-pdf/';

  const handleFileChange = (event) => {
    const file = event.target.files ? event.target.files[0] : null;
    if (file && file.type === 'application/pdf') {
      setSelectedFile(file);
      setMessage(`ไฟล์ที่เลือก: ${file.name}`);
      setOutputText('');
    } else {
      setSelectedFile(null);
      setMessage('กรุณาเลือกเฉพาะไฟล์ PDF เท่านั้น');
      setOutputText('');
    }
  };

  const handleSubmit = async (event) => {
    event.preventDefault();

    if (!selectedFile) {
      setMessage('u forgot to select pdf file');
      return;
    }

    setIsLoading(true);
    setMessage('pls wait for processing');

    const formData = new FormData();
    formData.append('file', selectedFile);
    try {
      const response = await fetch(FASTAPI_URL, {
        method: 'POST',
        body: formData,
      });
      if (!response.ok) {
        const errorData = await response.json();
        throw new Error(errorData.detail || 'การประมวลผลล้มเหลว');
      }

      const result = await response.json();
      setOutputText(result.corrected_text);
      setMessage(`✅ ประมวลผลสำเร็จ! (อ่านหน้า ${result.page_read} จาก ${result.filename})`);

    } catch (error) {
      console.error('Error:', error);
      setOutputText('');
      setMessage(`❌ เกิดข้อผิดพลาด: ${error.message}`);
    } finally {
      setIsLoading(false);
    }
  };

  return (
    <main className="flex flex-col items-center justify-start min-h-screen p-10 bg-gray-50">
      <div className="w-full max-w-2xl p-8 bg-white rounded-xl shadow-2xl">
        <h1 className="mb-6 text-3xl font-bold text-center text-indigo-700">
          PDF Text Corrector (Next.js + FastAPI + Ollama)
        </h1>
        <form onSubmit={handleSubmit} className="flex flex-col space-y-4">
          <label className="text-lg font-medium text-gray-700">
            อัปโหลดไฟล์ PDF (จะอ่านเฉพาะหน้า 2)
          </label>

          <input
            type="file"
            accept=".pdf"
            onChange={handleFileChange}
            disabled={isLoading}
            className="w-full p-2 border border-gray-300 rounded-lg file:mr-4 file:py-2 file:px-4 file:rounded-full file:border-0 file:text-sm file:font-semibold file:bg-indigo-50 file:text-indigo-700 hover:file:bg-indigo-100"
          />

          <button
            type="submit"
            disabled={!selectedFile || isLoading}
            className={`w-full py-3 text-white font-bold rounded-lg transition duration-200 
              ${!selectedFile || isLoading
                ? 'bg-gray-400 cursor-not-allowed'
                : 'bg-indigo-600 hover:bg-indigo-700 shadow-md'
              }`}
          >
            {isLoading ? '⏳ กำลังประมวลผล...' : '▶️ เริ่มประมวลผล PDF'}
          </button>
        </form>

        <hr className="my-6 border-gray-200" />

        <div className="p-4 text-center rounded-lg bg-indigo-50">
          <p className={`font-medium ${isLoading ? 'text-indigo-600 animate-pulse' : 'text-gray-800'}`}>
            {message || 'รอการเลือกไฟล์...'}
          </p>
        </div>

        {outputText && (
          <div className="mt-6 p-4 border-2 border-green-500 bg-green-50 rounded-lg">
            <h2 className="mb-2 text-xl font-bold text-green-700">
              ✅ ข้อความที่แก้ไขโดย Ollama:
            </h2>
            <pre className="p-3 whitespace-pre-wrap bg-white border border-gray-300 rounded-lg text-gray-800">
              {outputText}
            </pre>
          </div>
        )}

      </div>
    </main>
  );
}