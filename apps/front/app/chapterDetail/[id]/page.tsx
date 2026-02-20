"use client";

import { useState, useEffect, use } from "react";
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

interface Chapter {
  id: number;
  episodeNumber: number;
  chapterTitle: string;
  chapterDetail: string;
  movieId: number;
}

export default function ChapterReaderPage({
  params,
}: {
  params: Promise<{ id: string }>;
}) {
  const [chapter, setChapter] = useState<Chapter | null>(null); // maina data
  const [loading, setLoading] = useState(true);
  const [isEditing, setIsEditing] = useState(false);
  const [editTitle, setEditTitle] = useState("");
  const [editContent, setEditContent] = useState("");
  const resolvedParams = use(params);
  const chapterId = resolvedParams.id;
  const router = useRouter();

  const delay = (ms: number) =>
    new Promise((resolve) => setTimeout(resolve, ms));

  useEffect(() => {
    if (!chapterId) return;
    const fetchChapter = async () => {
      try {
        const res = await fetch(
          `http://127.0.0.1:8000/movies/chapters/${chapterId}`,
        );
        if (res.ok) {
          const data = await res.json();
          setChapter(data);
          setEditTitle(data.chapterTitle);
          setEditContent(data.chapterDetail || "");
        } else {
          toast.error("Chapter not found");
        }
      } catch (error) {
        toast.error("Failed to load");
      } finally {
        setLoading(false);
      }
    };
    fetchChapter();
  }, [chapterId]);

  const extractGen = async () => {
    try {
      const response1 = await fetch(
        `http://127.0.0.1:8000/extractEntities/${chapterId}`,
      );
      const data1 = await response1.json();
      console.log("done extract/ ", data1);

      await delay(3000);
      const response2 = await fetch(
        `http://127.0.0.1:8000/sound/${chapterId}/analysis`,
      );
      const data2 = await response2.json();
      console.log("done sound/ ", data2);

      await delay(3000);
      const response3 = await fetch(
        `http://127.0.0.1:8000/createPic/generate-images/${chapterId}`,
      );
      const data3 = await response3.json();
      console.log("done generateImages ", data3);

      await delay(3000);
      const response4 = await fetch(
        `http://127.0.0.1:8000/matcher/${chapterId}`,
      );
      const data4 = await response4.json();
      console.log("done matcher ", data4);
    } catch (error) {
      console.error("err API:", error);
    }
  };

  // const genPic = async () => {
  //   try {
  //     const response = await fetch(
  //       `http://127.0.0.1:8000/genPic/${chapterId}`,
  //       {
  //         method: "GET",
  //       },
  //     );
  //     console.log(response, "aaaaa");
  //     if (response.ok) {
  //       toast.success("Image generation started!");
  //     } else {
  //       toast.error("Failed to start image generation.");
  //     }
  //   } catch (error) {
  //     console.error("Error:", error);
  //     toast.error("An error occurred while starting image generation.");
  //   }
  // };

  const handleSave = async () => {
    if (!chapterId) return;
    const loadingToast = toast.loading("Saving...");
    try {
      const res = await fetch(
        `http://127.0.0.1:8000/movies/chapters/${chapterId}`,
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
                onClick={() => extractGen()}
                className=" py-3 px-6 rounded-full bg-gradient-to-r from-gray-50/80 to-gray-300/50 hover:from-gray-300 hover:to-gray-400 font-semibold shadow-[0_0_20px_rgba(244,114,182,0.4)] hover:shadow-[0_0_25px_rgba(244,114,182,0.6)] transform hover:scale-[1.02] disabled:opacity-70 disabled:cursor-not-allowed transition-all duration-300 flex items-center justify-center gap-2 group"
              >
                Gen Pic
              </button>
              {isEditing ? (
                <>
                  <button
                    onClick={() => setIsEditing(false)}
                    className="px-4 py-2 bg-gray-100 rounded-lg"
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
            </div>
          </div>
          <div className="flex-1 p-8">
            {isEditing ? (
              <textarea
                value={editContent}
                onChange={(e) => setEditContent(e.target.value)}
                className="w-full h-[60vh] p-4 border rounded-lg font-mono text-lg"
              />
            ) : (
              <article className="prose prose-lg max-w-none whitespace-pre-wrap text-white">
                {chapter.chapterDetail}
              </article>
            )}
          </div>
        </div>
      </div>
    </div>
  );
}
