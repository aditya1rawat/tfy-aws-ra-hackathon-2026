"use client";
import { useState } from "react";

interface Msg {
  from: "patient" | "care";
  author: string;
  text: string;
  time: string;
}

const SEED: Msg[] = [
  { from: "care", author: "R. Okafor, PharmD", text: "Hi John — remember to keep your INR check appointment this week. Reach out with any questions.", time: "2h ago" },
  { from: "patient", author: "You", text: "Thanks! Should I keep taking warfarin at the same time each day?", time: "1h ago" },
  { from: "care", author: "R. Okafor, PharmD", text: "Yes — same time daily keeps your levels steady. Evening with dinner is a good anchor.", time: "58m ago" },
];

export default function PatientMessagesPage() {
  const [messages, setMessages] = useState<Msg[]>(SEED);
  const [draft, setDraft] = useState("");

  const send = () => {
    const text = draft.trim();
    if (!text) return;
    setMessages((prev) => [...prev, { from: "patient", author: "You", text, time: "now" }]);
    setDraft("");
  };

  return (
    <div className="mx-auto flex h-[calc(100vh-9rem)] max-w-3xl flex-col">
      <div className="mb-4">
        <h1 className="text-2xl font-bold tracking-tight">Messages</h1>
        <p className="text-sm text-slate-400">Your care team at Mercy General — typically replies within an hour</p>
      </div>

      <div className="flex-1 space-y-4 overflow-auto rounded-2xl border border-slate-200 bg-white p-5 shadow-sm">
        {messages.map((m, i) => (
          <div key={i} className={`flex gap-3 ${m.from === "patient" ? "flex-row-reverse" : ""}`}>
            <div className={`flex h-9 w-9 shrink-0 items-center justify-center rounded-full text-sm font-semibold ${m.from === "patient" ? "bg-emerald-100 text-emerald-700" : "bg-sky-100 text-sky-700"}`}>
              {m.from === "patient" ? "JD" : "RO"}
            </div>
            <div className={`max-w-[75%] ${m.from === "patient" ? "text-right" : ""}`}>
              <div className={`rounded-2xl px-4 py-2 text-sm ${m.from === "patient" ? "bg-emerald-600 text-white" : "bg-slate-100 text-slate-700"}`}>
                {m.text}
              </div>
              <div className="mt-1 text-[11px] text-slate-400">{m.author} · {m.time}</div>
            </div>
          </div>
        ))}
      </div>

      <div className="mt-3 flex gap-2">
        <input
          value={draft}
          onChange={(e) => setDraft(e.target.value)}
          onKeyDown={(e) => { if (e.key === "Enter") send(); }}
          placeholder="Write a message to your care team…"
          className="h-11 flex-1 rounded-full border border-slate-200 bg-white px-4 text-sm outline-none focus:border-emerald-400"
        />
        <button onClick={send} disabled={!draft.trim()} className="cursor-pointer rounded-full bg-emerald-600 px-5 text-sm font-semibold text-white transition-colors hover:bg-emerald-700 disabled:cursor-not-allowed disabled:opacity-40">
          Send
        </button>
      </div>
    </div>
  );
}
