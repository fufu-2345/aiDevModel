"use client";

import { useState, useEffect, useCallback } from "react";
import { useRouter } from "next/navigation";
import toast, { Toaster } from "react-hot-toast";

const ArrowLeftIcon = ({ className }: { className?: string }) => (
    <svg
        xmlns="http://www.w3.org/2000/svg"
        viewBox="0 0 24 24"
        fill="none"
        stroke="currentColor"
        strokeWidth="2"
        strokeLinecap="round"
        strokeLinejoin="round"
        className={className}
    >
        <path d="M19 12H5" />
        <path d="M12 19l-7-7 7-7" />
    </svg>
);

const EyeIcon = ({ className }: { className?: string }) => (
    <svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" className={className}><path d="M2 12s3-7 10-7 10 7 10 7-3 7-10 7-10-7-10-7Z" /><circle cx="12" cy="12" r="3" /></svg>
);

const HeartIcon = ({ className }: { className?: string }) => (
    <svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="currentColor" className={className}>
        <path d="M1 21h4V9H1v12zm22-11c0-1.1-.9-2-2-2h-6.31l.95-4.57.03-.32c0-.41-.17-.79-.44-1.06L14.17 1 7.59 7.59C7.22 7.95 7 8.45 7 9v10c0 1.1.9 2 2 2h9c.83 0 1.54-.5 1.84-1.22l3.02-7.05c.09-.23.14-.47.14-.73v-2z" />
    </svg>
);

const RefreshIcon = ({ className }: { className?: string }) => (
    <svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" className={className}>
        <path d="M3 12a9 9 0 1 0 9-9 9.75 9.75 0 0 0-6.74 2.74L3 8" /><path d="M3 3v5h5" />
    </svg>
);

interface VideoStats {
    chapterTitle: string;
    episodeNumber: number;
    embed_url: string;
    view_count: number;
    like_count: number;
}

export default function YouTubeWatchPage(props: any) {
    const [chapterId, setChapterId] = useState<string>("");
    const [stats, setStats] = useState<VideoStats | null>(null);
    const [loading, setLoading] = useState(true);
    const [isRefreshing, setIsRefreshing] = useState(false);
    const router = useRouter();

    useEffect(() => {
        let id = "";
        if (props?.params?.id) {
            id = String(props.params.id);
        } else if (typeof window !== "undefined") {
            const pathParts = window.location.pathname.split("/");
            const lastPart = pathParts[pathParts.length - 1];
            if (lastPart && lastPart !== "watch" && lastPart !== "") {
                id = lastPart;
            }
        }
        setChapterId(id);
    }, [props]);

    const handleBack = () => {
        if (typeof window !== "undefined") {
            window.history.back();
        }
    };

    const fetchVideoStats = useCallback(async (refresh = false) => {
        if (!chapterId) {
            setLoading(false);
            return;
        }

        try {
            if (refresh) {
                setIsRefreshing(true);
            } else {
                setLoading(true);
            }

            const baseUrl = process.env.NEXT_PUBLIC_BACK_URL || 'http://localhost:8000';

            const url = `${baseUrl}/yt/stats/${chapterId}${refresh ? '?refresh=true' : ''}`;
            const res = await fetch(url);

            if (res.ok) {
                const data = await res.json();
                setStats(data);
                if (refresh) toast.success("อัปเดตสถิติล่าสุดแล้ว");
            } else {
                const errorData = await res.json().catch(() => ({}));
                if (!refresh) toast.error(errorData.detail || "ไม่พบข้อมูลวิดีโอ");
                else toast.error("อัปเดตสถิติไม่สำเร็จ");
            }
        } catch (error) {
            toast.error("เกิดข้อผิดพลาดในการเชื่อมต่อข้อมูล");
        } finally {
            setLoading(false);
            setIsRefreshing(false);
        }
    }, [chapterId]);

    useEffect(() => {
        if (chapterId) {
            fetchVideoStats(false);
        }
    }, [chapterId, fetchVideoStats]);

    if (loading) {
        return (
            <div className="min-h-screen flex items-center justify-center bg-gray-900 text-white">
                <div className="animate-pulse flex flex-col items-center gap-4">
                    <div className="w-12 h-12 border-4 border-pink-500 border-t-transparent rounded-full animate-spin"></div>
                    <div className="text-xl font-medium tracking-wider">กำลังโหลด...</div>
                </div>
            </div>
        );
    }

    if (!stats) {
        return (
            <div className="min-h-screen flex flex-col items-center justify-center bg-gray-900 text-white gap-6">
                <div className="text-2xl text-red-400 font-bold">ไม่พบข้อมูลวิดีโอ</div>
                <button onClick={handleBack} className="px-6 py-2 bg-white/10 hover:bg-white/20 rounded-full transition-all">
                    กลับหน้าเดิม
                </button>
            </div>
        );
    }

    return (
        <div className="min-h-screen bg-gray-50 p-8">
            <div className="fixed inset-0 z-0 bg-cover bg-center bg-no-repeat" style={{ backgroundImage: "url('/pic/bg.png')", backgroundColor: "#111827" }} />
            <Toaster position="top-center" />

            <div className="max-w-6xl mx-auto relative z-10">
                <button
                    onClick={() => router.push(`/chapterDetail/${chapterId}`)}
                    className="flex items-center gap-2 text-white transition font-medium mb-4 relative z-10"
                >
                    <ArrowLeftIcon className="w-5 h-5" /> Back
                </button>

                <div className="max-w-6xl mx-auto bg-white/10 backdrop-blur-3xl rounded-2xl shadow-[0_8px_32px_rgba(0,0,0,0.3)] border border-white/10 overflow-hidden min-h-[80vh] flex flex-col relative z-10">
                    <div className="px-8 py-6 border-b border-white/10 flex justify-between items-center sticky top-0 z-10 bg-black/20">
                        <div className="flex items-center gap-4 flex-1">
                            <div className="flex-1 overflow-hidden">
                                <h1 className="text-2xl text-white font-bold truncate drop-shadow-md flex items-center gap-3">
                                    <span className="bg-gradient-to-r from-pink-500 to-orange-400 text-transparent bg-clip-text text-3xl">
                                        EP {stats.episodeNumber}
                                    </span>
                                    <span className="opacity-90">{stats.chapterTitle}</span>
                                </h1>
                            </div>
                        </div>
                    </div>

                    <div className="flex-1 p-8 flex flex-col items-center">
                        <div className="w-full max-w-4xl relative overflow-hidden rounded-2xl bg-black/80 shadow-[0_0_40px_rgba(0,0,0,0.6)] border border-white/5 group" style={{ paddingTop: '56.25%' }}>
                            <iframe className="absolute top-0 left-0 w-full h-full transition-transform duration-700 group-hover:scale-[1.01]" src={stats.embed_url} title="YouTube video player" frameBorder="0" allow="accelerometer; autoplay; clipboard-write; encrypted-media; gyroscope; picture-in-picture" allowFullScreen></iframe>
                        </div>

                        <div className="w-full max-w-4xl mt-8 flex justify-end items-center gap-4 sm:gap-6">

                            <div className="flex items-center gap-3 bg-gradient-to-br from-white/10 to-white/5 backdrop-blur-md px-6 py-3 rounded-full border border-white/10 shadow-lg transition-all duration-300">
                                <EyeIcon className="w-6 h-6 text-sky-400 drop-shadow-[0_0_8px_rgba(56,189,248,0.6)]" />
                                <span className="text-xl font-bold text-white tracking-wider">{stats.view_count.toLocaleString()}</span>
                            </div>

                            <div className="flex items-center gap-3 bg-gradient-to-br from-white/10 to-white/5 backdrop-blur-md px-6 py-3 rounded-full border border-white/10 shadow-lg transition-all duration-300">
                                <HeartIcon className="w-6 h-6 text-pink-500 drop-shadow-[0_0_8px_rgba(236,72,153,0.6)]" />
                                <span className="text-xl font-bold text-white tracking-wider">{stats.like_count.toLocaleString()}</span>
                            </div>

                            {/* ปุ่ม Refresh สถิติ */}
                            <button
                                onClick={() => fetchVideoStats(true)}
                                disabled={isRefreshing}
                                className="flex items-center justify-center bg-white/10 hover:bg-white/20 backdrop-blur-md p-3 rounded-full border border-white/10 shadow-lg transition-all duration-300 disabled:opacity-50"
                                title="อัปเดตยอดวิวจาก YouTube"
                            >
                                <RefreshIcon className={`w-6 h-6 text-white ${isRefreshing ? 'animate-spin' : ''}`} />
                            </button>

                        </div>
                    </div>
                </div>
            </div>
        </div>
    );
}