'use client';

import { useState } from 'react';
import toast, { Toaster } from 'react-hot-toast';

// Icons
const SparklesIcon = ({ className }: { className?: string }) => (
    <svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" className={className}>
        <path d="m12 3-1.912 5.813a2 2 0 0 1-1.275 1.275L3 12l5.813 1.912a2 2 0 0 1 1.275 1.275L12 21l1.912-5.813a2 2 0 0 1 1.275-1.275L21 12l-5.813-1.912a2 2 0 0 1-1.275-1.275L12 3Z" />
    </svg>
);

const PhotoIcon = ({ className }: { className?: string }) => (
    <svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" className={className}>
        <rect width="18" height="18" x="3" y="3" rx="2" ry="2" />
        <circle cx="9" cy="9" r="2" />
        <path d="m21 15-3.086-3.086a2 2 0 0 0-2.828 0L6 21" />
    </svg>
);

export default function StableDiffusionPage() {
    const [prompt, setPrompt] = useState("");
    const [image, setImage] = useState<string | null>(null);
    const [loading, setLoading] = useState(false);

    const handleGenerate = async (e: React.FormEvent) => {
        e.preventDefault();
        if (!prompt) return;

        setLoading(true);
        const loadingToast = toast.loading('🎨 Generating image... (This might take a while)');

        try {
            const res = await fetch('http://127.0.0.1:8000/generate-image', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ prompt: prompt }),
            });

            if (!res.ok) {
                const errorData = await res.json();
                throw new Error(errorData.detail || 'Failed to generate');
            }

            const data = await res.json();
            // รับ Base64 มาแสดงผล
            setImage(`data:image/png;base64,${data.image_base64}`);
            toast.success('Image generated!', { id: loadingToast });
        } catch (error) {
            console.error(error);
            toast.error(`Error: ${error instanceof Error ? error.message : 'Something went wrong'}`, { id: loadingToast });
        } finally {
            setLoading(false);
        }
    };

    return (
        <div className="min-h-screen bg-gray-900 text-white p-8 flex flex-col items-center justify-center">
            <Toaster position="top-center" />

            <div className="max-w-2xl w-full">
                <div className="text-center mb-10">
                    <h1 className="text-4xl font-bold bg-gradient-to-r from-pink-500 to-violet-500 bg-clip-text text-transparent mb-2">
                        Stable Diffusion Lab
                    </h1>
                    <p className="text-gray-400">Generate images on your own server.</p>
                </div>

                {/* Input Area */}
                <form onSubmit={handleGenerate} className="bg-gray-800 p-6 rounded-2xl shadow-xl border border-gray-700 mb-8">
                    <label className="block text-sm font-medium text-gray-300 mb-2">Enter your prompt</label>
                    <div className="flex gap-4">
                        <input
                            type="text"
                            value={prompt}
                            onChange={(e) => setPrompt(e.target.value)}
                            placeholder="A futuristic city with flying cars, cyberpunk style..."
                            className="flex-1 bg-gray-900 border border-gray-700 rounded-xl px-4 py-3 focus:ring-2 focus:ring-violet-500 outline-none transition"
                        />
                        <button
                            type="submit"
                            disabled={loading || !prompt}
                            className="bg-violet-600 hover:bg-violet-700 disabled:opacity-50 disabled:cursor-not-allowed text-white px-6 py-3 rounded-xl font-bold transition flex items-center gap-2"
                        >
                            {loading ? (
                                <div className="animate-spin h-5 w-5 border-2 border-white border-t-transparent rounded-full" />
                            ) : (
                                <SparklesIcon className="w-5 h-5" />
                            )}
                            Generate
                        </button>
                    </div>
                </form>

                {/* Result Area */}
                <div className="bg-gray-800 rounded-2xl shadow-xl border border-gray-700 overflow-hidden min-h-[400px] flex items-center justify-center relative">
                    {image ? (
                        <div className="relative group w-full h-full">
                            <img src={image} alt="Generated" className="w-full h-auto object-contain max-h-[600px]" />
                            <div className="absolute inset-0 bg-black/50 opacity-0 group-hover:opacity-100 transition flex items-center justify-center">
                                <a
                                    href={image}
                                    download={`sd-generated-${Date.now()}.png`}
                                    className="bg-white text-black px-4 py-2 rounded-lg font-bold hover:bg-gray-200 transition"
                                >
                                    Download Image
                                </a>
                            </div>
                        </div>
                    ) : (
                        <div className="text-center text-gray-500">
                            {loading ? (
                                <div className="flex flex-col items-center animate-pulse">
                                    <SparklesIcon className="w-16 h-16 mb-4 text-violet-500 opacity-50" />
                                    <p>Dreaming pixels...</p>
                                </div>
                            ) : (
                                <div className="flex flex-col items-center">
                                    <PhotoIcon className="w-16 h-16 mb-4 opacity-30" />
                                    <p>Your creation will appear here</p>
                                </div>
                            )}
                        </div>
                    )}
                </div>
            </div>
        </div>
    );
}