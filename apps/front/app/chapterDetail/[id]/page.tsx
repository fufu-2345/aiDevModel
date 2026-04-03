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
const SaveIcon = ({ className }: { className?: string }) => (
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
    <path d="M19 21H5a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h11l5 5v11a2 2 0 0 1-2 2z" />
    <polyline points="17 21 17 13 7 13 7 21" />
    <polyline points="7 3 7 8 15 8" />
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

export const formatNovelText = (text: string) => {
  if (!text) return null;

  let globalText = text
    .replace(/"([^"]*)"/g, '“$1”')
    .replace(/'([^']*)'/g, '‘$1’');

  globalText = globalText
    .replace(/(\d+)/g, '<span class="text-sky-300">$1</span>')
    .replace(/(!+)/g, '<span class="text-orange-400 font-bold text-2xl">$1</span>');

  globalText = globalText.replace(/“([^“”]*)”/g, (match, innerText) => {
    const spanOpen = '<span class="text-amber-200 font-medium break-words">';
    const spanClose = '</span>';
    const safeInner = innerText.replace(/\n/g, `${spanClose}\n${spanOpen}`);
    return `${spanOpen}“${safeInner}”${spanClose}`;
  });

  globalText = globalText.replace(/‘([^‘’]*)’/g, (match, innerText) => {
    const spanOpen = '<span class="text-slate-400 break-words">';
    const spanClose = '</span>';
    const safeInner = innerText.replace(/\n/g, `${spanClose}\n${spanOpen}`);
    return `${spanOpen}‘${safeInner}’${spanClose}`;
  });
  const paragraphs = globalText.split("\n");
  let isFirstParagraph = true;
  return paragraphs.map((paragraph, index) => {
    const trimmedText = paragraph.trim();
    if (!trimmedText) return <div key={index} className="h-4" />;
    let processedText = trimmedText;
    if (isFirstParagraph) {
      isFirstParagraph = false;
      processedText = processedText.replace(
        /^((?:<[^>]+>)*)([“‘"']?(?:[\u0E40-\u0E44][\u0E01-\u0E2E]|.))([\u0E31\u0E34-\u0E3A\u0E47-\u0E4E]*)/,
        (match, p1, p2, p3) => {
          const colorClass = p1.includes("text-") ? "" : "text-white";
          return `${p1}<span class="text-[3.5rem] font-extrabold ${colorClass} leading-none align-baseline pr-[2px]">${p2}${p3}</span>`;
        },
      );
    }
    return (
      <p
        key={index}
        className="mb-5 leading-[2.1] text-slate-200 tracking-wide font-light text-[1.15rem] text-justify indent-[2.5rem] first-of-type:indent-0 sm:indent-[1.5rem] sm:text-[1.05rem]"
        dangerouslySetInnerHTML={{ __html: processedText }}
      />
    );
  });
};

export const formatNovelText2 = (text: string) => {
  if (!text) return null;
  let globalText = text
    .replace(/"([^"]*)"/g, '“$1”')
    .replace(/'([^']*)'/g, '‘$1’');
  globalText = globalText
    .replace(/(\d+)/g, '<span class="text-sky-300">$1</span>')
    .replace(/(!+)/g, '<span class="text-orange-400 font-bold text-2xl">$1</span>');
  globalText = globalText.replace(/“([^“”]*)”/g, (match, innerText) => {
    const spanOpen = '<span class="text-amber-200 font-medium break-words">';
    const spanClose = '</span>';
    const safeInner = innerText.replace(/\n/g, `${spanClose}\n${spanOpen}`);
    return `${spanOpen}“${safeInner}”${spanClose}`;
  });
  globalText = globalText.replace(/‘([^‘’]*)’/g, (match, innerText) => {
    const spanOpen = '<span class="text-slate-400 break-words">';
    const spanClose = '</span>';
    const safeInner = innerText.replace(/\n/g, `${spanClose}\n${spanOpen}`);
    return `${spanOpen}‘${safeInner}’${spanClose}`;
  });
  const paragraphs = globalText.split("\n");
  return paragraphs.map((paragraph, index) => {
    const trimmedText = paragraph.trim();
    if (!trimmedText) return <div key={index} className="h-4" />;
    return (
      <p
        key={index}
        className="mb-5 leading-[2.1] text-slate-200 tracking-wide font-light text-[1.15rem] text-justify indent-[2.5rem] first-of-type:indent-0 sm:indent-[1.5rem] sm:text-[1.05rem]"
        dangerouslySetInnerHTML={{ __html: trimmedText }}
      />
    );
  });
};

interface Chapter {
  id: number;
  episodeNumber: number;
  chapterTitle: string;
  chapterDetail: string;
  vdoPath: string | null;
  movieId: number;
}

export default function ChapterReaderPage({
  params,
}: {
  params: Promise<{ id: string }>;
}) {
  const [chapter, setChapter] = useState<Chapter | null>(null); // main data
  const [loading, setLoading] = useState(true);
  const [chunks, setChunks] = useState<any[]>([]);
  const [isEditing, setIsEditing] = useState(false);
  const [editTitle, setEditTitle] = useState("");
  const [editContent, setEditContent] = useState("");
  const [isUpload, setIsUpload] = useState(false);
  const [userRole, setUserRole] = useState<string | null>("");
  const resolvedParams = use(params);
  const chapterId = resolvedParams.id;
  const router = useRouter();

  const delay = (ms: number) =>
    new Promise((resolve) => setTimeout(resolve, ms));

  const fetchChapter = async () => {
    try {
      const res = await fetch(
        `${process.env.NEXT_PUBLIC_BACK_URL}/movies/chapters/${chapterId}`,
      );
      const temp = await fetch(
        `${process.env.NEXT_PUBLIC_BACK_URL}/yt/${chapterId}`,
      );
      if (temp.ok) {
        setIsUpload(true);
      }
      if (res.ok) {
        const data = await res.json();
        setChapter(data);
        setEditTitle(data.chapterTitle);
        setEditContent(data.chapterDetail || "");

        try {
          setLoading(true);
          const response = await fetch(
            `${process.env.NEXT_PUBLIC_BACK_URL}/movies/chunk/${chapterId}`,
          );
          if (!response.ok) throw new Error("Network response was not ok");
          const data = await response.json();

          const formattedChunks = Object.entries(data)
            .map(([key, value]: [string, any]) => ({
              id: parseInt(key, 10),
              text: (value as any).text,
              picRef: (value as any).picRef,
            }))
            .sort((a, b) => a.id - b.id);

          setChunks(formattedChunks);
        } catch (error) {
          console.error("Error fetching data:", error);
        } finally {
          setLoading(false);
        }
      } else {
        toast.error("Chapter not found");
      }
    } catch (error) {
      toast.error("Failed to load");
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    if (!chapterId) return;
    fetchChapter();
    setUserRole(localStorage.getItem("user_role"));
  }, [chapterId]);

  const extractGen = async () => {
    try {
      const response1 = await fetch(
        `${process.env.NEXT_PUBLIC_BACK_URL}/extractEntities/${chapterId}`,
      );

      await delay(3000);
      const response2 = await fetch(
        `${process.env.NEXT_PUBLIC_BACK_URL}/sound/${chapterId}/analysis`,
      );

      await delay(3000);
      const response3 = await fetch(
        `${process.env.NEXT_PUBLIC_BACK_URL}/createPic/generate-images/${chapterId}`,
      );

      await delay(3000);
      const response4 = await fetch(
        `${process.env.NEXT_PUBLIC_BACK_URL}/matcher/${chapterId}`,
      );
      await delay(1000);
      fetchChapter();
    } catch (error) {
      console.error("err API:", error);
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

  const uploadToYouTube = async (chapterId: number) => {
    try {
      const response = await fetch(`http://127.0.0.1:8000/yt/upload/${chapterId}`, {
        method: 'GET',
        headers: {
          'Content-Type': 'application/json',
        }
      });

      if (!response.ok) {
        const errorData = await response.json();
        throw new Error(errorData.detail || 'Upload failed');
      }

      const data = await response.json();

      Swal.fire({
        title: 'Success!',
        text: `Video uploaded successfully! URL: ${data.video_url}`,
        icon: 'success',
        confirmButtonText: 'OK'
      });

      return data;

    } catch (error) {
      console.error('Upload Error:', error);

      if (error instanceof Error) {
        Swal.fire({
          title: 'Error!',
          text: error.message,
          icon: 'error',
          confirmButtonText: 'OK'
        });
      } else {
        Swal.fire({
          title: 'Error!',
          text: 'An unknown error occurred.',
          icon: 'error',
          confirmButtonText: 'OK'
        });
      }
    }
  };

  const handleSave = async () => {
    if (!chapterId) return;
    const loadingToast = toast.loading("Saving...");
    try {
      const res = await fetch(
        `${process.env.NEXT_PUBLIC_BACK_URL}/movies/chapters/${chapterId}`,
        {
          method: "PUT",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({
            chapterTitle: editTitle,
            chapterDetail: editContent,
          }),
        },
      );
      if (res.ok) {
        const updated = await res.json();
        setChapter(updated);
        setIsEditing(false);
        toast.success("Saved!", { id: loadingToast });
      } else throw new Error();
    } catch (error) {
      toast.error("Failed to save", { id: loadingToast });
    }
  };

  if (loading)
    return (
      <div className="min-h-screen flex items-center justify-center">
        Loading...
      </div>
    );
  if (!chapter) return <div>Not Found</div>;

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
        <button
          onClick={() => router.push(`/chapters/${chapter.movieId}`)}
          className="flex items-center gap-2 text-white transition font-medium mb-4 relative z-10"
        >
          <ArrowLeftIcon className="w-5 h-5" /> Back to all chapters
        </button>
        <div className="max-w-6xl mx-auto bg-white/10 backdrop-blur-3xl rounded-2xl shadow-sm border border-gray-100 overflow-hidden min-h-[90vh] flex flex-col relative z-10">
          <div className="px-8 py-6 border-b border-gray-100 flex justify-between items-center sticky top-0 z-10">
            <div className="flex items-center gap-4 flex-1">
              <div className="flex-1 overflow-hidden">
                {isEditing ? (
                  <input
                    type="text"
                    value={editTitle}
                    onChange={(e) => setEditTitle(e.target.value)}
                    className="text-2xl font-bold w-full border p-1 rounded"
                  />
                ) : (
                  <h1 className="text-2xl text-white font-bold truncate">
                    <span className="text-white mr-2">
                      EP {chapter.episodeNumber}
                    </span>
                    {chapter.chapterTitle}
                  </h1>
                )}
              </div>
            </div>
            <div className="flex gap-2 ml-4">
              <button
                onClick={handleLogout}
                className="ml-auto  px-4 py-2.5 rounded-full bg-white/50 hover:bg-red-700 text-red-700 hover:text-white border border-red-200 hover:border-transparent font-medium shadow-sm transition-all duration-300 flex items-center gap-2 backdrop-blur-sm group"
              >
                <LogoutIcon className="w-5 h-5 group-hover:-translate-x-1 transition-transform" />
                <span>Logout</span>
              </button>
              {userRole === "admin" && (
                <>
                  <button
                    onClick={() => extractGen()}
                    className=" py-3 px-6 rounded-full bg-gradient-to-r from-gray-50/80 to-gray-300/50 hover:from-gray-300 hover:to-gray-400 font-semibold shadow-[0_0_20px_rgba(244,114,182,0.4)] hover:shadow-[0_0_25px_rgba(244,114,182,0.6)] transform hover:scale-[1.02] disabled:opacity-70 disabled:cursor-not-allowed transition-all duration-300 flex items-center justify-center gap-2 group"
                  >
                    Gen Video
                  </button>
                  {isUpload && (
                    <button
                      onClick={() => uploadToYouTube(chapter.id)}
                      className=" py-3 px-6 rounded-full bg-gradient-to-r from-gray-50/80 to-gray-300/50 hover:from-gray-300 hover:to-gray-400 font-semibold shadow-[0_0_20px_rgba(244,114,182,0.4)] hover:shadow-[0_0_25px_rgba(244,114,182,0.6)] transform hover:scale-[1.02] disabled:opacity-70 disabled:cursor-not-allowed transition-all duration-300 flex items-center justify-center gap-2 group"
                    >
                      Upload Video
                    </button>
                  )}
                  {chapter.vdoPath && (
                    <button
                      onClick={() => router.push(`/yt/${chapterId}`)}
                      className=" py-3 px-6 rounded-full bg-gradient-to-r from-gray-50/80 to-gray-300/50 hover:from-gray-300 hover:to-gray-400 font-semibold shadow-[0_0_20px_rgba(244,114,182,0.4)] hover:shadow-[0_0_25px_rgba(244,114,182,0.6)] transform hover:scale-[1.02] disabled:opacity-70 disabled:cursor-not-allowed transition-all duration-300 flex items-center justify-center gap-2 group"
                    >
                      Visit YouTube
                    </button>
                  )}
                  {isEditing ? (
                    <>
                      <button
                        onClick={() => setIsEditing(false)}
                        className=" py-3 px-6 rounded-full bg-gradient-to-r from-gray-50/80 to-gray-300/50 hover:from-gray-300 hover:to-gray-400 font-semibold shadow-[0_0_20px_rgba(244,114,182,0.4)] hover:shadow-[0_0_25px_rgba(244,114,182,0.6)] transform hover:scale-[1.02] disabled:opacity-70 disabled:cursor-not-allowed transition-all duration-300 flex items-center justify-center gap-2 group"
                      >
                        Cancel
                      </button>
                      <button
                        onClick={handleSave}
                        className="py-3 px-6 rounded-full bg-gradient-to-r from-gray-50/80 to-gray-300/50 hover:from-gray-300 hover:to-gray-400 font-semibold shadow-[0_0_20px_rgba(244,114,182,0.4)] hover:shadow-[0_0_25px_rgba(244,114,182,0.6)] transform hover:scale-[1.02] disabled:opacity-70 disabled:cursor-not-allowed transition-all duration-300 flex items-center justify-center gap-2 group"
                      >
                        <SaveIcon className="w-4 h-4" /> Save
                      </button>
                    </>
                  ) : (
                    <button
                      onClick={() => setIsEditing(true)}
                      className="py-3 px-6 rounded-full bg-gradient-to-r from-gray-50/80 to-gray-300/50 hover:from-gray-300 hover:to-gray-400 font-semibold shadow-[0_0_20px_rgba(244,114,182,0.4)] hover:shadow-[0_0_25px_rgba(244,114,182,0.6)] transform hover:scale-[1.02] disabled:opacity-70 disabled:cursor-not-allowed transition-all duration-300 flex items-center justify-center gap-2 group"
                    >
                      <EditIcon className="w-4 h-4" /> Edit
                    </button>
                  )}
                </>
              )}
            </div>
          </div>
          <div className="flex-1 p-8">
            {isEditing ? (
              <textarea
                value={editContent}
                onChange={(e) => setEditContent(e.target.value)}
                className="w-full h-[60vh] p-4 border rounded-lg font-mono text-lg"
              />
            ) : !chapter.vdoPath ? (
              // ไม่มี vdo
              <div className="w-full max-w-4xl mx-auto font-['Sarabun']">
                {formatNovelText(chapter.chapterDetail)}
              </div>
            ) : (
              <div>
                <video
                  width="1280"
                  height="640"
                  controls
                  className="rounded-lg shadow-lg"
                >
                  <source
                    src={`${process.env.NEXT_PUBLIC_BACK_URL}/static/${chapter.vdoPath}`}
                    type="video/mp4"
                  />
                  เบราว์เซอร์ของคุณไม่รองรับการเล่นวิดีโอ
                </video >
                <br />
                <hr className="my-8 border-gray-300" />
                <div>
                  <div className="max-w-4xl mx-auto py-8 px-4 flex flex-col gap-12">
                    {chunks.map((chunk) => (
                      <div key={chunk.id} className="flex flex-col gap-6">
                        {chunk.picRef && (
                          <div className="w-full flex justify-center">
                            <img
                              src={`${process.env.NEXT_PUBLIC_BACK_URL}/static/${chunk.picRef}`}
                              className="max-w-full h-auto object-contain rounded-md"
                            />
                          </div>
                        )}

                        {chunk.text && (
                          <div className="text-lg md:text-xl leading-relaxed whitespace-pre-wrap text-white/90 font-serif">
                            {formatNovelText2(chunk.text)}
                          </div>
                        )}
                      </div>
                    ))}
                  </div>
                </div>
              </div >
            )
            }
          </div >
        </div >
      </div >
    </div >
  );
}
