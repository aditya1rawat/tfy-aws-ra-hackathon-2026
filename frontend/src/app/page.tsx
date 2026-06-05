import Link from "next/link";

export default function Home() {
  return (
    <main className="mx-auto max-w-xl p-10">
      <h1 className="mb-2 text-2xl font-bold">Lifeline</h1>
      <p className="mb-6 text-zinc-600">Resilient medication &amp; coverage agent — choose a surface:</p>
      <div className="grid gap-3">
        <Link className="rounded border p-4 hover:bg-zinc-50" href="/patient">📱 Patient app</Link>
        <Link className="rounded border p-4 hover:bg-zinc-50" href="/clinic">🏥 Clinic console</Link>
        <Link className="rounded border p-4 hover:bg-zinc-50" href="/xray">🔬 X-ray / ops</Link>
      </div>
    </main>
  );
}
