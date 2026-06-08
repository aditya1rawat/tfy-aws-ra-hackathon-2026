"use client";
import { useState } from "react";

interface Thread {
  id: string;
  who: string;
  initials: string;
  preview: string;
  time: string;
  unread: boolean;
  body: string[];
}

const THREADS: Thread[] = [
  {
    id: "t1", who: "John Doe", initials: "JD", time: "12m", unread: true,
    preview: "Thanks! Should I keep taking warfarin at the same time…",
    body: [
      "Hi John — remember to keep your INR check appointment this week.",
      "Thanks! Should I keep taking warfarin at the same time each day?",
    ],
  },
  {
    id: "t2", who: "Dr. A. Patel", initials: "AP", time: "1h", unread: true,
    preview: "Please confirm the lisinopril hold for patient #100482.",
    body: ["Please confirm the lisinopril hold for patient #100482 until the dose review."],
  },
  {
    id: "t3", who: "Bob Martinez", initials: "BM", time: "3h", unread: false,
    preview: "Refill went through, thank you for the quick turnaround.",
    body: ["Refill went through, thank you for the quick turnaround."],
  },
];

export default function ClinicMessagesPage() {
  const [activeId, setActiveId] = useState(THREADS[0].id);
  const active = THREADS.find((t) => t.id === activeId) ?? THREADS[0];

  return (
    <div className="mx-auto max-w-5xl space-y-4">
      <div>
        <h1 className="text-2xl font-bold tracking-tight">Messages</h1>
        <p className="text-sm text-slate-400">Patient and provider conversations</p>
      </div>

      <div className="grid h-[calc(100vh-13rem)] grid-cols-1 gap-4 lg:grid-cols-3">
        <div className="overflow-auto rounded-2xl border border-slate-200 bg-white shadow-sm">
          {THREADS.map((t, i) => (
            <button
              key={t.id}
              onClick={() => setActiveId(t.id)}
              className={`flex w-full gap-3 px-4 py-3 text-left transition-colors ${t.id === activeId ? "bg-blue-50" : "hover:bg-slate-50"} ${i > 0 ? "border-t border-slate-100" : ""}`}
            >
              <div className="flex h-9 w-9 shrink-0 items-center justify-center rounded-full bg-blue-100 text-sm font-semibold text-blue-700">{t.initials}</div>
              <div className="min-w-0 flex-1">
                <div className="flex items-center justify-between">
                  <span className="truncate text-sm font-medium">{t.who}</span>
                  <span className="text-[11px] text-slate-400">{t.time}</span>
                </div>
                <div className="truncate text-xs text-slate-400">{t.preview}</div>
              </div>
              {t.unread ? <span className="mt-1 h-2 w-2 shrink-0 rounded-full bg-blue-500" /> : null}
            </button>
          ))}
        </div>

        <div className="flex flex-col overflow-hidden rounded-2xl border border-slate-200 bg-white shadow-sm lg:col-span-2">
          <div className="border-b border-slate-100 px-5 py-3">
            <div className="font-semibold">{active.who}</div>
            <div className="text-xs text-slate-400">Conversation</div>
          </div>
          <div className="flex-1 space-y-3 overflow-auto p-5">
            {active.body.map((line, i) => (
              <div key={i} className={`max-w-[75%] rounded-2xl px-4 py-2 text-sm ${i % 2 === 0 ? "bg-slate-100 text-slate-700" : "ml-auto bg-blue-600 text-white"}`}>
                {line}
              </div>
            ))}
          </div>
          <div className="flex gap-2 border-t border-slate-100 p-3">
            <input placeholder="Reply…" className="h-10 flex-1 rounded-full border border-slate-200 bg-white px-4 text-sm outline-none focus:border-blue-400" />
            <button className="cursor-pointer rounded-full bg-blue-600 px-5 text-sm font-semibold text-white hover:bg-blue-700">Send</button>
          </div>
        </div>
      </div>
    </div>
  );
}
