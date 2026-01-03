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
      <br />
      <br />
      <Link href="/testRag">Go to testRag</Link>
    </div>
  );
}
