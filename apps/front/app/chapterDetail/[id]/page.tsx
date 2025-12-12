'use client';

import { useState, useEffect, use } from 'react';
import { useRouter } from 'next/navigation';
import toast, { Toaster } from 'react-hot-toast';

// --- Icons ---
const ArrowLeftIcon = ({ className }: { className?: string }) => (
    <svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" className={className}>
        <path d="M19 12H5" />
        <path d="M12 19l-7-7 7-7" />
    </svg>
);

const EditIcon = ({ className }: { className?: string }) => (
    <svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" className={className}>
        <path d="M17 3a2.85 2.83 0 1 1 4 4L7.5 20.5 2 22l1.5-5.5Z" />
        <path d="m15 5 4 4" />
    </svg>
);

const SaveIcon = ({ className }: { className?: string }) => (
    <svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" className={className}>
        <path d="M19 21H5a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h11l5 5v11a2 2 0 0 1-2 2z" />
        <polyline points="17 21 17 13 7 13 7 21" />
        <polyline points="7 3 7 8 15 8" />
    </svg>
);

interface Chapter {
    id: number;
    episodeNumber: number;
    chapterTitle: string;
    chapterDetail: string;
    movieId: number;
}

export default function ChapterReaderPage({ params }: { params: Promise<{ id: string }> }) {
    const resolvedParams = use(params);
    const chapterId = resolvedParams.id;
    const router = useRouter();

    const [chapter, setChapter] = useState<Chapter | null>(null);
    const [loading, setLoading] = useState(true);

    // Edit States
    const [isEditing, setIsEditing] = useState(false);
    const [editTitle, setEditTitle] = useState("");
    const [editContent, setEditContent] = useState("");

    useEffect(() => {
        if (!chapterId) return;
        const fetchChapter = async () => {
            try {
                const res = await fetch(`http://127.0.0.1:8000/chapters/${chapterId}`);
                if (res.ok) {
                    const data = await res.json();
                    setChapter(data);
                    setEditTitle(data.chapterTitle);
                    setEditContent(data.chapterDetail || "");
                } else {
                    toast.error("Chapter not found");
                }
            } catch (error) {
                console.error("Error:", error);
                toast.error("Failed to load chapter");
            } finally {
                setLoading(false);
            }
        };
        fetchChapter();
    }, [chapterId]);

    const handleSave = async () => {
        if (!chapterId) return;
        const loadingToast = toast.loading('Saving changes...');
        try {
            const res = await fetch(`http://127.0.0.1:8000/chapters/${chapterId}`, {
                method: 'PUT',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({
                    chapterTitle: editTitle,
                    chapterDetail: editContent
                })
            });

            if (res.ok) {
                const updatedChapter = await res.json();
                setChapter(updatedChapter);
                setIsEditing(false);
                toast.success('Chapter saved!', { id: loadingToast });
            } else {
                throw new Error('Failed to update');
            }
        } catch (error) {
            console.error(error);
            toast.error('Failed to save', { id: loadingToast });
        }
    };

    if (loading) {
        return (
            <div className="min-h-screen bg-gray-50 flex items-center justify-center">
                <div className="animate-spin rounded-full h-12 w-12 border-b-2 border-blue-600"></div>
            </div>
        );
    }

    if (!chapter) {
        return (
            <div className="min-h-screen bg-gray-50 flex flex-col items-center justify-center gap-4">
                <h1 className="text-2xl font-bold text-gray-800">Chapter Not Found</h1>
                <button onClick={() => router.back()} className="text-blue-600 hover:underline">Go Back</button>
            </div>
        );
    }

    return (
        <div className="min-h-screen bg-gray-50 p-8">
            <Toaster position="top-center" />
            <div className="max-w-4xl mx-auto bg-white rounded-2xl shadow-sm border border-gray-100 overflow-hidden min-h-[90vh] flex flex-col">

                {/* Header */}
                <div className="px-8 py-6 border-b border-gray-100 flex justify-between items-center bg-white sticky top-0 z-10 shadow-sm">
                    <div className="flex items-center gap-4 flex-1">
                        <button
                            // ย้อนกลับไปหน้า Chapters (Movie Detail)
                            onClick={() => router.push(`/chapters/${chapter.movieId}`)}
                            className="p-2 text-gray-500 hover:text-blue-600 hover:bg-gray-100 rounded-lg transition"
                            title="Back to Movie"
                        >
                            <ArrowLeftIcon className="w-6 h-6" />
                        </button>

                        <div className="flex-1 overflow-hidden">
                            {isEditing ? (
                                <input
                                    type="text"
                                    value={editTitle}
                                    onChange={(e) => setEditTitle(e.target.value)}
                                    className="text-2xl font-bold text-gray-800 w-full border border-gray-300 rounded px-3 py-1 focus:ring-2 focus:ring-blue-500 outline-none"
                                />
                            ) : (
                                <h1 className="text-2xl font-bold text-gray-800 truncate" title={chapter.chapterTitle}>
                                    <span className="text-blue-600 mr-2">EP {chapter.episodeNumber}</span>
                                    {chapter.chapterTitle}
                                </h1>
                            )}
                        </div>
                    </div>

                    <div className="flex gap-2 ml-4">
                        {isEditing ? (
                            <>
                                <button
                                    onClick={() => {
                                        setIsEditing(false);
                                        setEditTitle(chapter.chapterTitle);
                                        setEditContent(chapter.chapterDetail || "");
                                    }}
                                    className="px-4 py-2 text-gray-600 bg-gray-100 hover:bg-gray-200 rounded-lg font-medium transition"
                                >
                                    Cancel
                                </button>
                                <button
                                    onClick={handleSave}
                                    className="px-4 py-2 bg-blue-600 hover:bg-blue-700 text-white rounded-lg font-medium shadow-sm transition flex items-center gap-2"
                                >
                                    <SaveIcon className="w-4 h-4" /> Save
                                </button>
                            </>
                        ) : (
                            <button
                                onClick={() => setIsEditing(true)}
                                className="px-4 py-2 text-gray-600 hover:bg-gray-100 border border-gray-200 rounded-lg font-medium transition flex items-center gap-2"
                            >
                                <EditIcon className="w-4 h-4" /> Edit Content
                            </button>
                        )}
                    </div>
                </div>

                {/* Content */}
                <div className="flex-1 p-8 md:p-12">
                    {isEditing ? (
                        <textarea
                            value={editContent}
                            onChange={(e) => setEditContent(e.target.value)}
                            className="w-full h-[60vh] p-4 border border-gray-200 rounded-lg focus:ring-2 focus:ring-blue-500 outline-none resize-none font-mono text-lg leading-relaxed text-gray-800"
                            placeholder="Type content here..."
                        />
                    ) : (
                        <article className="prose prose-lg max-w-none text-gray-800 leading-loose whitespace-pre-wrap font-sans">
                            {chapter.chapterDetail}
                        </article>
                    )}
                </div>

            </div>
        </div>
    );
}