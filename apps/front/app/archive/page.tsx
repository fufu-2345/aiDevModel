'use client';

import { useState, useEffect, useRef } from 'react';
import toast, { Toaster } from 'react-hot-toast';
import Swal from 'sweetalert2';
import { useRouter } from 'next/navigation';

// --- Inline SVGs (Icons) ---
const BookOpenIcon = ({ className }: { className?: string }) => (
    <svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" className={className}>
        <path d="M2 3h6a4 4 0 0 1 4 4v14a3 3 0 0 0-3-3H2z" />
        <path d="M22 3h-6a4 4 0 0 0-4 4v14a3 3 0 0 1 3-3h7z" />
    </svg>
);

const PlusIcon = ({ className }: { className?: string }) => (
    <svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" className={className}>
        <path d="M5 12h14" />
        <path d="M12 5v14" />
    </svg>
);

const LoaderIcon = ({ className }: { className?: string }) => (
    <svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" className={className}>
        <path d="M21 12a9 9 0 1 1-6.219-8.56" />
    </svg>
);

const EditIcon = ({ className }: { className?: string }) => (
    <svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" className={className}>
        <path d="M17 3a2.85 2.83 0 1 1 4 4L7.5 20.5 2 22l1.5-5.5Z" />
        <path d="m15 5 4 4" />
    </svg>
);

const CheckIcon = ({ className }: { className?: string }) => (
    <svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" className={className}>
        <path d="M20 6 9 17l-5-5" />
    </svg>
);

const TrashIcon = ({ className }: { className?: string }) => (
    <svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" className={className}>
        <path d="M3 6h18" />
        <path d="M19 6v14c0 1-1 2-2 2H7c-1 0-2-1-2-2V6" />
        <path d="M8 6V4c0-1 1-2 2-2h4c1 0 2 1 2 2v2" />
        <line x1="10" x2="10" y1="11" y2="17" />
        <line x1="14" x2="14" y1="11" y2="17" />
    </svg>
);

interface Movie {
    id: number;
    movieTitle: string;
    episodeAmount: number;
    picPath: string;
}

export default function MovieDashboard() {
    const router = useRouter(); // เรียกใช้ Router
    const [movies, setMovies] = useState<Movie[]>([]);
    const [isModalOpen, setIsModalOpen] = useState(false);
    const [isLoading, setIsLoading] = useState(false);
    const [isEditMode, setIsEditMode] = useState(false);

    // Form State
    const [titleInput, setTitleInput] = useState('');
    const [selectedFile, setSelectedFile] = useState<File | null>(null);
    const fileInputRef = useRef<HTMLInputElement>(null);

    // Fetch Movies
    const fetchMovies = async () => {
        try {
            const res = await fetch('http://127.0.0.1:8000/movies/');
            if (res.ok) {
                const data = await res.json();
                setMovies(data);
            } else {
                console.error('Fetch movies error:', res.status, res.statusText);
                toast.error('Failed to load movies');
            }
        } catch (error) {
            console.error('Failed to fetch movies:', error);
            toast.error('Connection error: Failed to fetch movies');
        }
    };

    useEffect(() => {
        fetchMovies();
    }, []);

    // Handle Delete with SweetAlert2
    const handleDelete = async (e: React.MouseEvent, id: number) => {
        e.stopPropagation();

        // ใช้ SweetAlert2 แทน window.confirm
        const result = await Swal.fire({
            title: 'Are you sure?',
            text: "You won't be able to revert this!",
            icon: 'warning',
            showCancelButton: true,
            confirmButtonColor: '#ef4444', // Tailwind red-500
            cancelButtonColor: '#9ca3af', // Tailwind gray-400
            confirmButtonText: 'Yes, delete it!'
        });

        if (!result.isConfirmed) return;

        try {
            const res = await fetch(`http://127.0.0.1:8000/movies/${id}`, {
                method: 'DELETE',
            });
            if (res.ok) {
                setMovies(prev => prev.filter(m => m.id !== id));
                toast.success('Movie deleted successfully');
            } else {
                toast.error('Failed to delete movie');
            }
        } catch (error) {
            console.error('Error deleting movie:', error);
            toast.error('Error deleting movie');
        }
    };

    // Handle Upload with React Hot Toast
    const handleUpload = async (e: React.FormEvent) => {
        e.preventDefault();
        if (!selectedFile || !titleInput) return;

        setIsLoading(true);
        const loadingToast = toast.loading('Uploading and processing PDF...'); // แสดง Loading

        const formData = new FormData();
        formData.append('title', titleInput);
        formData.append('file', selectedFile);

        try {
            const res = await fetch('http://127.0.0.1:8000/upload-movie/', {
                method: 'POST',
                body: formData,
            });

            if (!res.ok) {
                const errorText = await res.text();
                throw new Error(`Upload failed: ${res.status} ${res.statusText} - ${errorText}`);
            }

            // Reset & Reload
            setIsModalOpen(false);
            setTitleInput('');
            setSelectedFile(null);
            await fetchMovies();

            // อัปเดต Toast เป็น Success
            toast.success('Upload & Process Successful!', { id: loadingToast });
        } catch (error) {
            console.error(error);
            // อัปเดต Toast เป็น Error
            toast.error(`Upload failed: ${error instanceof Error ? error.message : 'Unknown error'}`, { id: loadingToast });
        } finally {
            setIsLoading(false);
        }
    };

    // ฟังก์ชันนำทางไปหน้า movie detail
    const handleCardClick = (id: number) => {
        if (isEditMode) return; // ถ้าอยู่ในโหมด Edit ไม่ให้คลิกไปหน้าอื่น
        router.push(`/chapters/${id}`);
    };

    return (
        <div className="min-h-screen bg-gray-50 p-8">
            {/* ใส่ Toaster ไว้ที่ Root ของ component */}
            <Toaster position="top-center" reverseOrder={false} />

            <div className="max-w-6xl mx-auto">
                {/* Header Section */}
                <div className="flex justify-between items-center mb-8">
                    <h1 className="text-3xl font-bold text-gray-800">📚 Movie / Book Library</h1>

                    {/* Toggle Edit Mode Button */}
                    <button
                        onClick={() => setIsEditMode(!isEditMode)}
                        className={`flex items-center gap-2 px-4 py-2 rounded-lg font-medium transition ${isEditMode
                            ? 'bg-green-100 text-green-700 hover:bg-green-200'
                            : 'bg-gray-200 text-gray-700 hover:bg-gray-300'
                            }`}
                    >
                        {isEditMode ? (
                            <>
                                <CheckIcon className="w-5 h-5" /> Done
                            </>
                        ) : (
                            <>
                                <EditIcon className="w-5 h-5" /> Edit
                            </>
                        )}
                    </button>
                </div>

                {/* --- GRID LAYOUT (4 Columns) --- */}
                <div className="grid grid-cols-2 md:grid-cols-3 lg:grid-cols-4 gap-6">

                    {/* Render Movies */}
                    {movies.map((movie) => (
                        <div
                            key={movie.id}
                            onClick={() => handleCardClick(movie.id)}
                            className={`bg-white rounded-xl shadow-sm hover:shadow-md transition overflow-hidden border border-gray-100 flex flex-col group cursor-pointer relative ${isEditMode ? 'ring-2 ring-red-100' : ''}`}
                        >

                            {/* DELETE BUTTON (Visible only in Edit Mode) */}
                            {isEditMode && (
                                <button
                                    onClick={(e) => handleDelete(e, movie.id)}
                                    className="absolute top-2 right-2 z-10 bg-red-500 hover:bg-red-600 text-white p-2 rounded-full shadow-md transition transform hover:scale-110"
                                    title="Delete Movie"
                                >
                                    <TrashIcon className="w-4 h-4" />
                                </button>
                            )}

                            {/* Cover Image Area */}
                            <div className="h-48 bg-gray-200 flex items-center justify-center relative overflow-hidden">
                                {movie.picPath ? (
                                    <img src={movie.picPath} alt={movie.movieTitle} className="w-full h-full object-cover" />
                                ) : (
                                    <BookOpenIcon className="w-12 h-12 text-gray-400" />
                                )}
                                {/* Overlay Effect (Disable hover effect in Edit Mode to focus on delete) */}
                                {!isEditMode && (
                                    <div className="absolute inset-0 bg-black/0 group-hover:bg-black/10 transition" />
                                )}
                            </div>

                            {/* Content Area */}
                            <div className="p-4 flex-1 flex flex-col justify-between">
                                <div>
                                    <h3 className="font-semibold text-lg text-gray-800 line-clamp-1" title={movie.movieTitle}>
                                        {movie.movieTitle}
                                    </h3>
                                    <p className="text-sm text-gray-500 mt-1">
                                        Chapters: <span className="font-medium text-blue-600">{movie.episodeAmount}</span>
                                    </p>
                                </div>
                            </div>
                        </div>
                    ))}

                    {/* --- ADD BUTTON CARD --- */}
                    <button
                        onClick={() => setIsModalOpen(true)}
                        disabled={isEditMode} // Disable Add button in Edit Mode
                        className={`h-[280px] rounded-xl border-2 border-dashed border-gray-300 flex flex-col items-center justify-center text-gray-400 transition gap-2 group ${isEditMode ? 'opacity-50 cursor-not-allowed' : 'hover:text-blue-500 hover:border-blue-400 hover:bg-blue-50'}`}
                    >
                        <div className={`w-12 h-12 rounded-full bg-gray-100 flex items-center justify-center transition ${!isEditMode && 'group-hover:bg-blue-100'}`}>
                            <PlusIcon className="w-6 h-6" />
                        </div>
                        <span className="font-medium">Add New Movie</span>
                    </button>
                </div>
            </div>

            {/* --- MODAL POPUP --- */}
            {isModalOpen && (
                <div className="fixed inset-0 bg-black/50 flex items-center justify-center z-50 p-4 backdrop-blur-sm">
                    <div className="bg-white rounded-2xl shadow-2xl w-full max-w-md overflow-hidden animate-in fade-in zoom-in duration-200">
                        {/* Modal Header */}
                        <div className="bg-gray-50 px-6 py-4 border-b border-gray-100 flex justify-between items-center">
                            <h2 className="text-xl font-semibold text-gray-800">Upload New Movie</h2>
                            <button
                                onClick={() => setIsModalOpen(false)}
                                className="text-gray-400 hover:text-gray-600"
                            >
                                ✕
                            </button>
                        </div>

                        {/* Modal Form */}
                        <form onSubmit={handleUpload} className="p-6 space-y-4">
                            {/* Title Input */}
                            <div>
                                <label className="block text-sm font-medium text-gray-700 mb-1">Movie Title</label>
                                <input
                                    type="text"
                                    required
                                    value={titleInput}
                                    onChange={(e) => setTitleInput(e.target.value)}
                                    placeholder="Enter movie name..."
                                    className="w-full px-4 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-blue-500 focus:border-blue-500 outline-none transition"
                                />
                            </div>

                            {/* File Input */}
                            <div>
                                <label className="block text-sm font-medium text-gray-700 mb-1">PDF File</label>
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
                                            <p className="text-xs text-gray-400 mt-1">Support .pdf only</p>
                                        </div>
                                    )}
                                </div>
                            </div>

                            {/* Action Buttons */}
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
                                            <LoaderIcon className="w-4 h-4 animate-spin" /> Processing...
                                        </>
                                    ) : (
                                        'Upload & Process'
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