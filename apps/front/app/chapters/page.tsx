'use client';

import { useState, useEffect, use } from 'react';
import { useRouter } from 'next/navigation'; // In Next.js 13+, use 'next/navigation'
import toast, { Toaster } from 'react-hot-toast';

// --- Icons ---
const ArrowLeftIcon = ({ className }: { className?: string }) => (
    <svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" className={className}>
        <path d="M19 12H5" />
        <path d="M12 19l-7-7 7-7" />
    </svg>
);

const ImageIcon = ({ className }: { className?: string }) => (
    <svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" className={className}>
        <rect width="18" height="18" x="3" y="3" rx="2" ry="2" />
        <circle cx="9" cy="9" r="2" />
        <path d="m21 15-3.086-3.086a2 2 0 0 0-2.828 0L6 21" />
    </svg>
);

// --- Interfaces ---
interface Movie {
    id: number;
    movieTitle: string;
    episodeAmount: number;
    picPath: string;
}

interface Chapter {
    id: number;
    episodeNumber: number;
    chapterTitle: string;
    chapterDetail: string;
    picPath: string;
}

export default function ChapterListPage({ params }: { params: Promise<{ id: string }> }) {
    const resolvedParams = use(params);
    const movieId = resolvedParams.id;
    const router = useRouter();

    const [movie, setMovie] = useState<Movie | null>(null);
    const [chapters, setChapters] = useState<Chapter[]>([]);
    const [loading, setLoading] = useState(true);

    useEffect(() => {
        if (!movieId) return;

        const fetchData = async () => {
            try {
                // Fetch Movie Data
                const movieRes = await fetch(`http://127.0.0.1:8000/movies/${movieId}`);
                if (movieRes.ok) {
                    setMovie(await movieRes.json());
                }

                // Fetch Chapters Data
                const chapterRes = await fetch(`http://127.0.0.1:8000/movies/${movieId}/chapters`);
                if (chapterRes.ok) {
                    setChapters(await chapterRes.json());
                }
            } catch (error) {
                console.error("Error:", error);
                toast.error("Failed to load data");
            } finally {
                setLoading(false);
            }
        };

        fetchData();
    }, [movieId]);

    if (loading) {
        return (
            <div className="min-h-screen bg-gray-50 flex items-center justify-center">
                <div className="animate-spin rounded-full h-12 w-12 border-b-2 border-blue-600"></div>
            </div>
        );
    }

    if (!movie) {
        return (
            <div className="min-h-screen bg-gray-50 flex flex-col items-center justify-center gap-4">
                <h1 className="text-2xl font-bold text-gray-800">Movie Not Found</h1>
                <button onClick={() => router.push('/')} className="text-blue-600 hover:underline flex items-center gap-2">
                    <ArrowLeftIcon className="w-4 h-4" /> Back to Library
                </button>
            </div>
        );
    }

    return (
        <div className="min-h-screen bg-gray-50 p-8">
            <Toaster position="top-center" />

            <div className="max-w-7xl mx-auto">
                {/* Header */}
                <div className="mb-8">
                    <button
                        onClick={() => router.push('/')}
                        className="flex items-center gap-2 text-gray-600 hover:text-blue-600 transition font-medium mb-4"
                    >
                        <ArrowLeftIcon className="w-5 h-5" /> Back to Library
                    </button>

                    <div className="flex flex-col md:flex-row gap-6 items-start bg-white p-6 rounded-2xl shadow-sm border border-gray-100">
                        <div className="w-32 h-48 md:w-48 md:h-72 bg-gray-200 rounded-lg flex-shrink-0 overflow-hidden">
                            {movie.picPath ? (
                                <img src={movie.picPath} alt={movie.movieTitle} className="w-full h-full object-cover" />
                            ) : (
                                <div className="w-full h-full flex items-center justify-center text-gray-400">
                                    <ImageIcon className="w-12 h-12" />
                                </div>
                            )}
                        </div>
                        <div className="flex-1">
                            <h1 className="text-3xl md:text-4xl font-bold text-gray-900 mb-2">{movie.movieTitle}</h1>
                            <div className="flex items-center gap-4 text-gray-500 mb-6">
                                <span className="bg-blue-100 text-blue-800 px-3 py-1 rounded-full text-sm font-medium">
                                    {chapters.length} Chapters
                                </span>
                                <span>ID: {movie.id}</span>
                            </div>
                        </div>
                    </div>
                </div>

                {/* Chapters Grid */}
                <h2 className="text-xl font-bold text-gray-800 mb-4 px-1">Episodes / Chapters</h2>

                {chapters.length > 0 ? (
                    <div className="grid grid-cols-2 sm:grid-cols-3 md:grid-cols-4 lg:grid-cols-5 gap-4">
                        {chapters.map((chapter) => (
                            <div
                                key={chapter.id}
                                // ✅ ลิ้งค์ไปที่หน้า /chapterDetail/[id]
                                onClick={() => router.push(`/chapterDetail/${chapter.id}`)}
                                // ✅ ใส่ bg-red-500 เพื่อเช็คการแสดงผล
                                className="bg-red-500 rounded-lg shadow-sm border border-gray-100 overflow-hidden hover:shadow-md transition cursor-pointer active:scale-95 duration-100 group"
                            >
                                <div className="aspect-video bg-gray-100 relative overflow-hidden pointer-events-none">
                                    {chapter.picPath ? (
                                        <img src={chapter.picPath} alt={chapter.chapterTitle} className="w-full h-full object-cover" />
                                    ) : (
                                        <div className="w-full h-full flex items-center justify-center text-gray-300">
                                            <ImageIcon className="w-8 h-8" />
                                        </div>
                                    )}
                                    <div className="absolute top-2 left-2 bg-black/60 text-white text-xs px-2 py-1 rounded backdrop-blur-sm">
                                        EP {chapter.episodeNumber}
                                    </div>
                                </div>
                                <div className="p-3 pointer-events-none">
                                    <h3 className="text-sm font-medium text-white line-clamp-2 leading-snug" title={chapter.chapterTitle}>
                                        {chapter.chapterTitle}
                                    </h3>
                                </div>
                            </div>
                        ))}
                    </div>
                ) : (
                    <div className="text-center py-12 text-gray-400 bg-white rounded-xl border border-dashed border-gray-200">
                        <p>No chapters found for this movie.</p>
                    </div>
                )}
            </div>
        </div>
    );
}