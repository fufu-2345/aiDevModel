"use client";

import Link from "next/link";

export default function Page() {
  return (
    <div>
      <p>Main</p>

      <br />
      <br />
      <Link href="/testTTS">Go to testTTS</Link>

      <br />
      <br />
      <Link href="/archive">Go to archive</Link>
    </div>
  );
}
