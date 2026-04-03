"use client";

import { useState, useEffect, useRef } from "react";
import { useRouter } from "next/navigation";
import toast, { Toaster } from "react-hot-toast";
import Swal from "sweetalert2";

const BookOpenIcon = ({ className }: { className?: string }) => (
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
    <path d="M2 3h6a4 4 0 0 1 4 4v14a3 3 0 0 0-3-3H2z" />
    <path d="M22 3h-6a4 4 0 0 0-4 4v14a3 3 0 0 1 3-3h7z" />
  </svg>
);
const PlusIcon = ({ className }: { className?: string }) => (
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
    <path d="M5 12h14" />
    <path d="M12 5v14" />
  </svg>
);
const LoaderIcon = ({ className }: { className?: string }) => (
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
    <path d="M21 12a9 9 0 1 1-6.219-8.56" />
  </svg>
);
const EditIcon = ({ className }: { className?: string }) => (
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
    <path d="M17 3a2.85 2.83 0 1 1 4 4L7.5 20.5 2 22l1.5-5.5Z" />
    <path d="m15 5 4 4" />
  </svg>
);
const CheckIcon = ({ className }: { className?: string }) => (
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
    <path d="M20 6 9 17l-5-5" />
  </svg>
);
const TrashIcon = ({ className }: { className?: string }) => (
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
    <path d="M3 6h18" />
    <path d="M19 6v14c0 1-1 2-2 2H7c-1 0-2-1-2-2V6" />
    <path d="M8 6V4c0-1 1-2 2-2h4c1 0 2 1 2 2v2" />
    <line x1="10" x2="10" y1="11" y2="17" />
    <line x1="14" x2="14" y1="11" y2="17" />
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

export default function MovieDashboard() {
  const [movies, setMovies] = useState<Movie[]>([]);
  const [isModalOpen, setIsModalOpen] = useState(false);
  const [isLoading, setIsLoading] = useState(false);
  const [isEditMode, setIsEditMode] = useState(false);
  const [titleInput, setTitleInput] = useState("");
  const [selectedFile, setSelectedFile] = useState<File | null>(null);
  const [searchBar, setSearchBar] = useState("");
  const [moviePics, setMoviePics] = useState<Record<string, string>>({});
  const [userRole, setUserRole] = useState<string | null>("");
  const fileInputRef = useRef<HTMLInputElement>(null);
  const router = useRouter();

  const fetchMovies = async () => {
    try {
      const res = await fetch(`${process.env.NEXT_PUBLIC_BACK_URL}/movies/`);
      if (res.ok) {
        const data = await res.json();
        setMovies(data);
      } else {
        toast.error("Failed to load movies");
      }
    } catch (error) {
      toast.error("Connection error");
    }
  };

  const search = async () => {
    if (searchBar.trim() === "") {
      fetchMovies();
      return;
    } else {
      try {
        const res = await fetch(
          `${process.env.NEXT_PUBLIC_BACK_URL}/movies/chapters/searchArchive/${searchBar}/`,
        );
        if (res.ok) {
          const data = await res.json();
          setMovies(data);
        } else {
          toast.error("Failed to load movies");
        }
      } catch (error) {
        toast.error("Connection error");
      }
    }
  };

  const fetchMoviePics = async () => {
    try {
      const res = await fetch(`${process.env.NEXT_PUBLIC_BACK_URL}/movies/pic/allMovies`);
      if (res.ok) {
        const data = await res.json();
        setMoviePics(data);
      }
    } catch (error) {
      console.error("Error fetching movie pictures:", error);
    }
  };

  useEffect(() => {
    fetchMovies();
    fetchMoviePics();
    setUserRole(localStorage.getItem("user_role"));
  }, []);

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
      localStorage.removeItem("access_token");
      localStorage.removeItem("user_role");
      localStorage.removeItem("user_email");

      window.location.href = "/";
    }
  };

  const handleDelete = async (e: React.MouseEvent, id: number) => {
    e.stopPropagation();
    const result = await Swal.fire({
      title: "Are you sure?",
      text: "You won't be able to revert this!",
      icon: "warning",
      showCancelButton: true,
      confirmButtonColor: "#ef4444",
      cancelButtonColor: "#9ca3af",
      confirmButtonText: "Yes, delete it!",
    });
    if (!result.isConfirmed) return;
    try {
      const res = await fetch(`${process.env.NEXT_PUBLIC_BACK_URL}/movies/${id}`, {
        method: "DELETE",
      });
      if (res.ok) {
        setMovies((prev) => prev.filter((m) => m.id !== id));
        toast.success("Movie deleted");
      } else {
        toast.error("Failed to delete");
      }
    } catch (error) {
      toast.error("Error deleting movie");
    }
  };

  const handleUpload = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!selectedFile || !titleInput) return;
    setIsLoading(true);
    const loadingToast = toast.loading("Uploading and processing PDF...");
    const formData = new FormData();
    formData.append("title", titleInput);
    formData.append("file", selectedFile);
    try {
      const res = await fetch(`${process.env.NEXT_PUBLIC_BACK_URL}/uploadPDF/`, {
        method: "POST",
        body: formData,
      });
      if (!res.ok) throw new Error();
      setIsModalOpen(false);
      setTitleInput("");
      setSelectedFile(null);
      await fetchMovies();
      toast.success("Upload & Process Successful!", { id: loadingToast });
    } catch (error) {
      toast.error("Upload failed" + error);
    } finally {
      setIsLoading(false);
    }
  };

  const handleCardClick = (id: number) => {
    if (isEditMode) return;
    router.push(`/chapters/${id}`);
  };

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
        <div className="flex justify-between items-center mb-8">
          <h1 className="text-6xl font-bold tracking-wide drop-shadow-[0_0_15px_rgba(244,114,182,0.6)] text-transparent bg-clip-text bg-gradient-to-br from-gray-200 via-gray-300 to-gray-400 py-2 leading-tight">
            Archive
          </h1>
          <button
            onClick={handleLogout}
            className="ml-auto mr-5 px-4 py-2.5 rounded-full bg-white/50 hover:bg-red-700 text-red-700 hover:text-white border border-red-200 hover:border-transparent font-medium shadow-sm transition-all duration-300 flex items-center gap-2 backdrop-blur-sm group"
          >
            <LogoutIcon className="w-5 h-5 group-hover:-translate-x-1 transition-transform" />
            <span>Logout</span>
          </button>
          {userRole === "admin" && (
            <button
              onClick={() => setIsEditMode(!isEditMode)}
              className="w-[10%] py-3 px-6 rounded-full bg-gradient-to-r from-gray-50/80 to-gray-300/50 hover:from-gray-300 hover:to-gray-400 text-white font-semibold shadow-[0_0_20px_rgba(244,114,182,0.4)] hover:shadow-[0_0_25px_rgba(244,114,182,0.6)] transform hover:scale-[1.02] disabled:opacity-70 disabled:cursor-not-allowed transition-all duration-300 flex items-center justify-center gap-2 group"
            >
              <>
                {isEditMode ? (
                  <>
                    <CheckIcon className="w-5 h-5" /> Done
                  </>
                ) : (
                  <>
                    <EditIcon className="w-5 h-5" /> Edit
                  </>
                )}
              </>
            </button>
          )}
        </div>
        <div className="bg-white/10 backdrop-blur-md p-8 rounded-2xl shadow-sm border border-gray-100 w-[110%] relative left-1/2 -translate-x-1/2">
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
          <div className="grid grid-cols-2 md:grid-cols-3 lg:grid-cols-4 gap-6">
            {movies.map((movie) => (
              <div
                key={movie.id}
                onClick={() => handleCardClick(movie.id)}
                className={`bg-white rounded-xl shadow-sm hover:shadow-md transition overflow-hidden border border-gray-100 flex flex-col group cursor-pointer relative ${isEditMode ? "ring-2 ring-red-100" : ""}`}
              >
                {isEditMode && (
                  <button
                    onClick={(e) => handleDelete(e, movie.id)}
                    className="absolute top-2 right-2 z-10 bg-red-500 hover:bg-red-600 text-white p-2 rounded-full shadow-md transition transform hover:scale-110"
                    title="Delete Movie"
                  >
                    <TrashIcon className="w-4 h-4" />
                  </button>
                )}
                <div className="h-48 bg-gray-200 flex items-center justify-center relative overflow-hidden">
                  {moviePics[movie.id] ? (
                    <img
                      src={`${process.env.NEXT_PUBLIC_BACK_URL}/static/${moviePics[movie.id]}`}
                      alt={movie.movieTitle}
                      className="w-full h-full object-cover"
                    />
                  ) : (
                    <BookOpenIcon className="w-12 h-12 text-gray-400" />
                  )}
                  {!isEditMode && (
                    <div className="absolute inset-0 bg-black/0 group-hover:bg-black/10 transition" />
                  )}
                </div>
                <div className="p-4 flex-1">
                  <h3
                    className="font-semibold text-lg text-gray-800 line-clamp-1"
                    title={movie.movieTitle}
                  >
                    {movie.movieTitle}
                  </h3>
                  <p className="text-sm text-gray-500 mt-1">
                    Chapters:{" "}
                    <span className="font-medium text-blue-600">
                      {movie.episodeAmount}
                    </span>
                  </p>
                </div>
              </div>
            ))}
            {userRole === "admin" && (
              <button
                onClick={() => setIsModalOpen(true)}
                disabled={isEditMode}
                className={`h-[280px] rounded-xl border-2 border-dashed border-gray-300 flex flex-col items-center justify-center text-gray-400 transition gap-2 group ${isEditMode ? "opacity-50 cursor-not-allowed" : "hover:bg-white/30"}`}
              >
                <div
                  className={`w-12 h-12 rounded-full bg-gray-100 flex items-center justify-center transition ${!isEditMode}`}
                >
                  <PlusIcon className="w-6 h-6" />
                </div>
                <span className="font-medium text-white">Add New Novel</span>
              </button>
            )}
          </div>
        </div>
      </div>
      {isModalOpen && (
        <div className="fixed inset-0 bg-black/50 flex items-center justify-center z-50 p-4 backdrop-blur-sm">
          <div className="bg-white rounded-2xl shadow-2xl w-full max-w-md overflow-hidden animate-in fade-in zoom-in duration-200">
            <div className="bg-gray-50 px-6 py-4 border-b border-gray-100 flex justify-between items-center">
              <h2 className="text-xl font-semibold text-gray-800">
                Upload New Novel
              </h2>
              <button
                onClick={() => setIsModalOpen(false)}
                className="text-gray-400 hover:text-gray-600"
              >
                ✕
              </button>
            </div>
            <form onSubmit={handleUpload} className="p-6 space-y-4">
              <div>
                <label className="block text-sm font-medium text-gray-700 mb-1">
                  Novel Title
                </label>
                <input
                  type="text"
                  required
                  value={titleInput}
                  onChange={(e) => setTitleInput(e.target.value)}
                  placeholder="Enter Novel name..."
                  className="w-full px-4 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-blue-500 focus:border-blue-500 outline-none transition"
                />
              </div>
              <div>
                <label className="block text-sm font-medium text-gray-700 mb-1">
                  PDF File
                </label>
                <div
                  className="border-2 border-dashed border-gray-300 rounded-lg p-6 text-center cursor-pointer hover:bg-gray-50 transition"
                  onClick={() => fileInputRef.current?.click()}
                >
                  <input
                    type="file"
                    accept=".pdf"
                    ref={fileInputRef}
                    className="hidden"
                    onChange={(e) => {
                      if (e.target.files && e.target.files[0]) {
                        setSelectedFile(e.target.files[0]);
                      }
                    }}
                  />
                  {selectedFile ? (
                    <div className="flex items-center justify-center gap-2 text-blue-600 font-medium">
                      📄 {selectedFile.name}
                    </div>
                  ) : (
                    <div className="text-gray-500">
                      <p>Click to select PDF</p>
                      <p className="text-xs text-gray-400 mt-1">
                        Support .pdf only
                      </p>
                    </div>
                  )}
                </div>
              </div>
              <div className="pt-2 flex gap-3">
                <button
                  type="button"
                  onClick={() => setIsModalOpen(false)}
                  className="flex-1 px-4 py-2 text-gray-700 bg-gray-100 hover:bg-gray-200 rounded-lg font-medium transition"
                  disabled={isLoading}
                >
                  Cancel
                </button>
                <button
                  type="submit"
                  disabled={isLoading || !selectedFile || !titleInput}
                  className="flex-1 px-4 py-2 bg-blue-600 hover:bg-blue-700 text-white rounded-lg font-medium shadow-md hover:shadow-lg transition disabled:opacity-50 disabled:cursor-not-allowed flex items-center justify-center gap-2"
                >
                  {isLoading ? (
                    <>
                      <LoaderIcon className="w-4 h-4 animate-spin" />{" "}
                      Processing...
                    </>
                  ) : (
                    "Upload & Process"
                  )}
                </button>
              </div>
            </form>
          </div>
        </div>
      )}
    </div>
  );
}
