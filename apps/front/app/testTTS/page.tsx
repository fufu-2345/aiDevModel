'use client';

import { useState, useRef } from 'react';

export default function TTSPage() {
    const [text, setText] = useState('สวัสดีครับ วันนี้อากาศดีมากเลย');
    const [isLoading, setIsLoading] = useState(false);
    const audioRef = useRef<HTMLAudioElement>(null);

    const generateAudio = async (model: 'piper' | 'vits') => {
        setIsLoading(true);
        try {
            const response = await fetch(`http://localhost:8000/tts/${model}`, {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json',
                },
                body: JSON.stringify({ text }),
            });
            if (!response.ok) throw new Error('Generation failed');
            // รับ Blob จาก Backend
            const blob = await response.blob();
            const url = URL.createObjectURL(blob);
            // สั่งเล่นเสียง
            if (audioRef.current) {
                audioRef.current.src = url;
                audioRef.current.play();
            }
        } catch (error) {
            console.error(error);
            alert('เกิดข้อผิดพลาดในการสร้างเสียง');
        } finally {
            setIsLoading(false);
        }
    };

    return (
        <div className="p-10 max-w-2xl mx-auto space-y-6">
            <h1 className="text-2xl font-bold">Local Thai TTS (Piper & VITS)</h1>

            <textarea
                className="w-full p-4 border rounded-lg text-black"
                rows={4}
                value={text}
                onChange={(e) => setText(e.target.value)}
                placeholder="พิมพ์ข้อความภาษาไทยที่นี่..."
            />

            <div className="flex gap-4">
                <button
                    onClick={() => generateAudio('piper')}
                    disabled={isLoading}
                    className="px-6 py-2 bg-blue-600 text-white rounded hover:bg-blue-700 disabled:bg-gray-400"
                >
                    {isLoading ? 'Generating...' : 'Speak with Piper (Fast)'}
                </button>

                <button
                    onClick={() => generateAudio('vits')}
                    disabled={isLoading}
                    className="px-6 py-2 bg-green-600 text-white rounded hover:bg-green-700 disabled:bg-gray-400"
                >
                    {isLoading ? 'Generating...' : 'Speak with VITS (High Quality)'}
                </button>
            </div>

            <audio ref={audioRef} controls className="w-full mt-4" />

            <p className="text-sm text-gray-500 mt-2">
                * Piper ต้องติดตั้ง binary และมีไฟล์ model.onnx <br />
                * VITS จะดาวน์โหลดโมเดลอัตโนมัติในครั้งแรก (MMS-TTS)
            </p>
        </div>
    );
}