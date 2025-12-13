'use client';

import { useState, useEffect, use } from 'react';
import { useRouter } from 'next/navigation';
import toast, { Toaster } from 'react-hot-toast';

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

const PlayIcon = ({ className }: { className?: string }) => (
    <svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="currentColor" stroke="currentColor" strokeWidth="0" className={className}>
        <path d="M8 5v14l11-7z" />
    </svg>
);

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
    const [movie, setMovie] = useState<Movie | null>(null);
    const [chapters, setChapters] = useState<Chapter[]>([]);
    const [loading, setLoading] = useState(true);
    const resolvedParams = use(params);
    const movieId = resolvedParams.id;
    const router = useRouter();


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
                    const data = await chapterRes.json();
                    setChapters(data);
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
                <button onClick={() => router.push('/archive')} className="text-blue-600 hover:underline flex items-center gap-2">
                    <ArrowLeftIcon className="w-4 h-4" /> Back to Archive
                </button>
            </div>
        );
    }

    return (
        <div className="min-h-screen bg-gray-50 p-8">
            <Toaster position="top-center" />

            <div className="max-w-6xl mx-auto">
                {/* Header / Back Button */}
                <div className="mb-8">
                    <button
                        onClick={() => router.push('/archive')}
                        className="flex items-center gap-2 text-gray-600 hover:text-blue-600 transition font-medium mb-4"
                    >
                        <ArrowLeftIcon className="w-5 h-5" /> Back to Archive
                    </button>

                    <div className="bg-white p-6 rounded-2xl shadow-sm border border-gray-100 flex flex-col md:flex-row gap-8 items-start">
                        {/* Movie Cover */}
                        <div className="w-40 h-60 bg-gray-200 rounded-xl overflow-hidden shadow-md flex-shrink-0">
                            {movie.picPath ? (
                                <img src={movie.picPath} alt={movie.movieTitle} className="w-full h-full object-cover" />
                            ) : (
                                <div className="w-full h-full flex items-center justify-center text-gray-400 bg-gray-100">
                                    <ImageIcon className="w-16 h-16" />
                                </div>
                            )}
                        </div>

                        {/* Movie Info */}
                        <div className="flex-1 py-2">
                            <h1 className="text-3xl md:text-4xl font-bold text-gray-800 mb-3">{movie.movieTitle}</h1>
                            <div className="flex flex-wrap items-center gap-3 text-sm text-gray-600 mb-6">
                                <span className="bg-blue-100 text-blue-800 px-3 py-1 rounded-full font-medium">
                                    {chapters.length} Chapters
                                </span>
                                <span className="px-3 py-1 bg-gray-100 rounded-full">ID: {movie.id}</span>
                            </div>
                            <p className="text-gray-500 leading-relaxed max-w-2xl">
                                Select a chapter below to start reading or editing the content.
                            </p>
                        </div>
                    </div>
                </div>

                {/* Chapters Grid */}
                <div className="flex items-center justify-between mb-6">
                    <h2 className="text-2xl font-bold text-gray-800">Episodes</h2>
                    <span className="text-sm text-gray-500">{chapters.length} items</span>
                </div>

                {chapters.length > 0 ? (
                    <div className="grid grid-cols-2 sm:grid-cols-3 md:grid-cols-4 lg:grid-cols-5 gap-6">
                        {chapters.map((chapter) => (
                            <div
                                key={chapter.id}
                                onClick={() => router.push(`/chapterDetail/${chapter.id}`)}
                                className="bg-white rounded-xl shadow-sm hover:shadow-lg transition-all duration-200 border border-gray-100 overflow-hidden cursor-pointer group flex flex-col h-full"
                            >
                                {/* Thumbnail */}
                                <div className="aspect-video bg-gray-100 relative overflow-hidden">
                                    {chapter.picPath ? (
                                        <img src={chapter.picPath} alt={chapter.chapterTitle} className="w-full h-full object-cover transition-transform duration-500 group-hover:scale-105" />
                                    ) : (
                                        <div className="w-full h-full flex items-center justify-center text-gray-300 bg-gray-50">
                                            <ImageIcon className="w-10 h-10" />
                                        </div>
                                    )}

                                    {/* Overlay on Hover */}
                                    <div className="absolute inset-0 bg-black/0 group-hover:bg-black/10 transition-colors duration-200 flex items-center justify-center">
                                        <div className="bg-white/90 p-2 rounded-full opacity-0 group-hover:opacity-100 transform translate-y-2 group-hover:translate-y-0 transition-all duration-200 shadow-sm">
                                            <PlayIcon className="w-6 h-6 text-blue-600" />
                                        </div>
                                    </div>

                                    {/* Episode Badge */}
                                    <div className="absolute top-2 left-2 bg-black/70 backdrop-blur-sm text-white text-[10px] font-bold px-2 py-1 rounded-md shadow-sm">
                                        EP {chapter.episodeNumber}
                                    </div>
                                </div>

                                {/* Content */}
                                <div className="p-4 flex-1 flex flex-col">
                                    <h3 className="font-semibold text-gray-800 text-sm line-clamp-2 leading-snug group-hover:text-blue-600 transition-colors" title={chapter.chapterTitle}>
                                        {chapter.chapterTitle}
                                    </h3>
                                    <div className="mt-auto pt-3 flex items-center justify-between text-xs text-gray-400">
                                        <span>Click to read</span>
                                    </div>
                                </div>
                            </div>
                        ))}
                    </div>
                ) : (
                    <div className="flex flex-col items-center justify-center py-16 bg-white rounded-2xl border-2 border-dashed border-gray-200 text-gray-400">
                        <ImageIcon className="w-16 h-16 mb-4 opacity-50" />
                        <p className="text-lg font-medium">No chapters found</p>
                        <p className="text-sm">Upload a PDF to generate chapters for this movie.</p>
                    </div>
                )}
            </div>
        </div>
    );
}