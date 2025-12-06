'use client';

import { useState } from 'react';

export default function ProcessPdfPage() {
  const [selectedFile, setSelectedFile] = useState(null);
  const [startPage, setStartPage] = useState(2);
  const [endPage, setEndPage] = useState(7);
  const [outputText, setOutputText] = useState('');
  const [isLoading, setIsLoading] = useState(false);
  const [message, setMessage] = useState('');
  const [executionTime, setExecutionTime] = useState(null);
  const FASTAPI_URL = 'http://localhost:8000/process-pdf/';

  const handleFileChange = (event) => {
    const file = event.target.files ? event.target.files[0] : null;
    if (file && file.type === 'application/pdf') {
      setSelectedFile(file);
      setMessage(`ไฟล์ที่เลือก: ${file.name}`);
      setOutputText('');
      setExecutionTime(null);
    } else {
      setSelectedFile(null);
      setMessage('กรุณาเลือกเฉพาะไฟล์ PDF เท่านั้น');
      setOutputText('');
    }
  };

  const handleSubmit = async (event) => {
    event.preventDefault();

    if (!selectedFile) {
      setMessage('ลืมเลือกไฟล์ PDF ครับ');
      return;
    }
    if (parseInt(startPage) > parseInt(endPage)) {
      setMessage('❌ หน้าเริ่มต้น ต้องน้อยกว่าหรือเท่ากับ หน้าสุดท้าย');
      return;
    }

    setIsLoading(true);
    setExecutionTime(null);
    setMessage('⏳ กำลังประมวลผล กรุณารอสักครู่...');

    const startTime = performance.now();
    const formData = new FormData();
    formData.append('file', selectedFile);
    formData.append('start', startPage);
    formData.append('end', endPage);

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
      setExecutionTime(((performance.now() - startTime) / 1000).toFixed(2));
      setOutputText(result.corrected_text);
      setMessage(`✅ สำเร็จ! (อ่านหน้า ${result.pages_processed} จาก ${result.filename})`);

    } catch (error) {
      console.error('Error:', error);
      setOutputText('');
      setExecutionTime(null);
      setMessage(`❌ เกิดข้อผิดพลาด: ${error.message}`);
    } finally {
      setIsLoading(false);
    }
  };

  return (
    <main className="flex flex-col items-center justify-start min-h-screen p-10 bg-gray-50">
      <div className="w-full max-w-2xl p-8 bg-white rounded-xl shadow-2xl">
        <h1 className="mb-6 text-3xl font-bold text-center text-indigo-700">
          PDF Text Corrector
        </h1>
        <form onSubmit={handleSubmit} className="flex flex-col space-y-4">

          <div>
            <label className="block mb-2 text-lg font-medium text-gray-700">
              1. อัปโหลดไฟล์ PDF
            </label>
            <input
              type="file"
              accept=".pdf"
              onChange={handleFileChange}
              disabled={isLoading}
              className="w-full p-2 border border-gray-300 rounded-lg file:mr-4 file:py-2 file:px-4 file:rounded-full file:border-0 file:text-sm file:font-semibold file:bg-indigo-50 file:text-indigo-700 hover:file:bg-indigo-100"
            />
          </div>

          <div className="flex space-x-4">
            <div className="w-1/2">
              <label className="block mb-1 font-medium text-gray-700">เริ่มหน้าที่:</label>
              <input
                type="number"
                min="1"
                value={startPage}
                onChange={(e) => setStartPage(e.target.value)}
                className="w-full p-2 border border-gray-300 rounded-lg text-center"
              />
            </div>
            <div className="w-1/2">
              <label className="block mb-1 font-medium text-gray-700">ถึงหน้าที่:</label>
              <input
                type="number"
                min="1"
                value={endPage}
                onChange={(e) => setEndPage(e.target.value)}
                className="w-full p-2 border border-gray-300 rounded-lg text-center"
              />
            </div>
          </div>

          <button
            type="submit"
            disabled={!selectedFile || isLoading}
            className={`w-full py-3 text-white font-bold rounded-lg transition duration-200 
              ${!selectedFile || isLoading
                ? 'bg-gray-400 cursor-not-allowed'
                : 'bg-indigo-600 hover:bg-indigo-700 shadow-md'
              }`}
          >
            {isLoading ? '⏳ กำลังประมวลผล...' : '▶️ เริ่มประมวลผล'}
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
            <div className="flex justify-between items-center mb-2">
              <h2 className="text-xl font-bold text-green-700">
                ✅ ผลลัพธ์จาก Ollama:
              </h2>
              {executionTime && (
                <span className="bg-green-200 text-green-800 px-3 py-1 rounded-full text-sm font-semibold shadow-sm">
                  ⏱️ ใช้เวลา: {executionTime} วินาที
                </span>
              )}
            </div>

            <pre className="p-3 whitespace-pre-wrap bg-white border border-gray-300 rounded-lg text-gray-800 text-sm">
              {outputText}
            </pre>
          </div>
        )}

      </div>
    </main>
  );
}