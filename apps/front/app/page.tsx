"use client";

import Link from "next/link";

export default function Page() {
  async function callBackend() {
    const res = await fetch("http://localhost:8000/ollama");
    const data = await res.json();
    console.log(data);
  }

  return (
    <div>
      <p>Main</p>
      <button onClick={callBackend}>test back</button>

      <br /><br />
      <Link href="/testPDF">Go to testPDF</Link>
    </div>
  );
}
