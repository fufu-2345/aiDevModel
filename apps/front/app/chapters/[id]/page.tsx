"use client";

import { useState, useEffect, use } from "react";
import { useRouter } from "next/navigation";
import toast, { Toaster } from "react-hot-toast";
import Swal from "sweetalert2";

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

const ImageIcon = ({ className }: { className?: string }) => (
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
    <rect width="18" height="18" x="3" y="3" rx="2" ry="2" />
    <circle cx="9" cy="9" r="2" />
    <path d="m21 15-3.086-3.086a2 2 0 0 0-2.828 0L6 21" />
  </svg>
);

const PlayIcon = ({ className }: { className?: string }) => (
  <svg
    xmlns="http://www.w3.org/2000/svg"
    viewBox="0 0 24 24"
    fill="currentColor"
    stroke="currentColor"
    strokeWidth="0"
    className={className}
  >
    <path d="M8 5v14l11-7z" />
  </svg>
);

const LogoutIcon = ({ className }: { className?: string }) => (
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
    <path d="M9 21H5a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h4" />
    <polyline points="16 17 21 12 16 7" />
    <line x1="21" y1="12" x2="9" y2="12" />
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

export default function ChapterListPage({
  params,
}: {
  params: Promise<{ id: string }>;
}) {
  const [movie, setMovie] = useState<Movie | null>(null);
  const [chapters, setChapters] = useState<Chapter[]>([]);
  const [loading, setLoading] = useState(true);
  const [searchBar, setSearchBar] = useState("");
  const [pictures, setPictures] = useState<{
    moviePic: string | null;
    chapters: Record<string, string>;
  }>({ moviePic: null, chapters: {} });
  const [userRole, setUserRole] = useState<string | null>("");
  const resolvedParams = use(params);
  const movieId = resolvedParams.id;
  const router = useRouter();

  const fetchData = async () => {
    try {
      // Fetch Movie Data
      const movieRes = await fetch(`${process.env.NEXT_PUBLIC_BACK_URL}/movies/${movieId}`);
      if (movieRes.ok) {
        setMovie(await movieRes.json());
      }
      // Fetch Chapters Data
      const chapterRes = await fetch(
        `${process.env.NEXT_PUBLIC_BACK_URL}/movies/${movieId}/chapters`,
      );
      if (chapterRes.ok) {
        const data = await chapterRes.json();
        setChapters(data);
      }

      const picRes = await fetch(`${process.env.NEXT_PUBLIC_BACK_URL}/movies/pic/${movieId}`);
      if (picRes.ok) {
        const picData = await picRes.json();
        setPictures(picData);
      }
    } catch (error) {
      console.error("Error:", error);
      toast.error("Failed to load data");
    } finally {
      setLoading(false);
    }
  };

  const handleLogout = async () => {
    const result = await Swal.fire({
      title: "Logout?",
      text: "Are you sure you want to logout?",
      icon: "warning",
      showCancelButton: true,
      confirmButtonColor: "#d33",
      cancelButtonColor: "#9ca3af",
      confirmButtonText: "Yes, logout!",
      cancelButtonText: "Cancel",
    });

    if (result.isConfirmed) {
      router.push("/");
    }
  };

  const search = async () => {
    if (searchBar.trim() === "") {
      fetchData();
      return;
    } else {
      try {
        const res = await fetch(
          `${process.env.NEXT_PUBLIC_BACK_URL}/movies/chapters/searchChapters/${searchBar}/${movieId}/`,
        );
        if (res.ok) {
          const data = await res.json();
          setChapters(data);
        } else {
          toast.error("Failed to load chapters");
        }
      } catch (error) {
        toast.error("Connection error");
      }
    }
  };

  useEffect(() => {
    if (!movieId) return;
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
        <button
          onClick={() => router.push("/archive")}
          className="text-blue-600 hover:underline flex items-center gap-2"
        >
          <ArrowLeftIcon className="w-4 h-4" /> Back to Archive
        </button>
      </div>
    );
  }

  return (
    <div className="min-h-screen bg-gray-50 p-8">
      <div
        className="fixed inset-0 z-0 bg-cover bg-center bg-no-repeat"
        style={{
          backgroundImage: "url('/pic/bg.png')",
        }}
      />
      <Toaster position="top-center" />

      <div className="max-w-6xl mx-auto relative z-10">
        <div className="mb-8">
          {/* เอา 2 ปุ่มมาไว้ในบรรทัดเดียวกัน */}
          <div className="flex justify-between items-center mb-4">
            <button
              onClick={() => router.push("/archive")}
              className="flex items-center gap-2 text-white transition font-medium"
            >
              <ArrowLeftIcon className="w-5 h-5" /> Back to Archive
            </button>

            <button
              onClick={handleLogout}
              className="px-4 py-2.5 rounded-full bg-white/50 hover:bg-red-700 text-red-700 hover:text-white border border-red-200 hover:border-transparent font-medium shadow-sm transition-all duration-300 flex items-center gap-2 backdrop-blur-sm group"
            >
              <LogoutIcon className="w-5 h-5 group-hover:-translate-x-1 transition-transform" />
              <span>Logout</span>
            </button>
          </div>

          <div className="bg-white/10 backdrop-blur-md p-6 rounded-2xl shadow-sm border border-gray-100 flex flex-col md:flex-row gap-8 items-start">
            <div className="w-80 h-60 bg-gray-200 rounded-xl overflow-hidden shadow-md flex-shrink-0">
              {pictures && pictures.moviePic ? (
                <img
                  src={`${process.env.NEXT_PUBLIC_BACK_URL}/static/${pictures.moviePic}`}
                  alt={movie.movieTitle}
                  className="w-full h-full object-cover"
                />
              ) : (
                <div className="w-full h-full flex items-center justify-center text-gray-400 bg-gray-100">
                  <ImageIcon className="w-16 h-16" />
                </div>
              )}
            </div>

            <div className="flex-1 py-2">
              <p className="text-3xl md:text-4xl font-bold text-white mb-3">
                {movie.movieTitle}
              </p>
            </div>
          </div>
        </div>

        <div className="bg-white/10 backdrop-blur-md p-6 rounded-2xl shadow-sm border border-gray-100">
          <div className="flex items-center justify-between mb-6">
            <div className="relative w-full max-w-xl mb-6">
              <div className="absolute inset-y-0 left-0 pl-3 flex items-center pointer-events-none">
                <svg
                  className="h-5 w-5 text-gray-400"
                  fill="none"
                  viewBox="0 0 24 24"
                  stroke="currentColor"
                >
                  <path
                    strokeLinecap="round"
                    strokeLinejoin="round"
                    strokeWidth="2"
                    d="M21 21l-6-6m2-5a7 7 0 11-14 0 7 7 0 0114 0z"
                  />
                </svg>
              </div>
              <input
                type="text"
                className="block w-full pl-10 pr-3 py-2 border border-gray-300 rounded-lg leading-5 bg-white placeholder-gray-500 focus:outline-none focus:placeholder-gray-400 focus:ring-1 focus:ring-black sm:text-sm transition duration-150 ease-in-out cursor-pointer"
                placeholder="name of novel"
                value={searchBar}
                onChange={(e) => setSearchBar(e.target.value)}
                onKeyDown={(e) => {
                  if (e.key === "Enter") {
                    search();
                  }
                }}
              />
            </div>
            <span className="text-sm text-gray-300">
              {chapters.length} Episodes
            </span>
          </div>

          {chapters.length > 0 ? (
            <div className="grid grid-cols-2 sm:grid-cols-3 md:grid-cols-4 lg:grid-cols-5 gap-6">
              {chapters.map((chapter) => (
                <div
                  key={chapter.id}
                  onClick={() => router.push(`/chapterDetail/${chapter.id}`)}
                  className="bg-white rounded-xl shadow-sm hover:shadow-lg transition-all duration-200 border border-gray-100 overflow-hidden cursor-pointer group flex flex-col h-full"
                >
                  <div className="aspect-video bg-gray-100 relative overflow-hidden">
                    {pictures && pictures.chapters[chapter.id] ? (
                      <img
                        src={`${process.env.NEXT_PUBLIC_BACK_URL}/static/${pictures.chapters[chapter.id]}`}
                        alt={chapter.chapterTitle}
                        className="w-full h-full object-cover transition-transform duration-500 group-hover:scale-105"
                      />
                    ) : (
                      <div className="w-full h-full flex items-center justify-center text-gray-300 bg-gray-50">
                        <ImageIcon className="w-10 h-10" />
                      </div>
                    )}
                    <div className="absolute inset-0 bg-black/0 group-hover:bg-black/10 transition-colors duration-200 flex items-center justify-center">
                      <div className="bg-white/90 p-2 rounded-full opacity-0 group-hover:opacity-100 transform translate-y-2 group-hover:translate-y-0 transition-all duration-200 shadow-sm">
                        <PlayIcon className="w-6 h-6 text-blue-600" />
                      </div>
                    </div>
                    <div className="absolute top-2 left-2 bg-black/70 backdrop-blur-sm text-white text-[10px] font-bold px-2 py-1 rounded-md shadow-sm">
                      EP {chapter.episodeNumber}
                    </div>
                  </div>
                  <div className="p-4 flex-1 flex flex-col">
                    <h3
                      className="font-semibold text-gray-800 text-sm line-clamp-2 leading-snug group-hover:text-blue-600 transition-colors"
                      title={chapter.chapterTitle}
                    >
                      {chapter.chapterTitle}
                    </h3>
                  </div>
                </div>
              ))}
            </div>
          ) : (
            <div className="flex flex-col items-center justify-center py-16 bg-white rounded-2xl border-2 border-dashed border-gray-200 text-gray-400">
              <ImageIcon className="w-16 h-16 mb-4 opacity-50" />
              <p className="text-lg font-medium">No chapters found</p>
              <p className="text-sm">
                Upload a PDF to generate chapters for this movie.
              </p>
            </div>
          )}
        </div>
      </div>
    </div>
  );
}
