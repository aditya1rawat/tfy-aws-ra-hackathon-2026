export function SideCards() {
  return (
    <div className="space-y-4">
      {/* Next appointment */}
      <div className="rounded-2xl border border-slate-200 bg-white p-5 shadow-sm">
        <h3 className="mb-3 text-sm font-semibold">Next appointment</h3>
        <div className="flex items-center gap-3">
          <div className="flex h-12 w-12 flex-col items-center justify-center rounded-xl bg-emerald-50 text-emerald-700">
            <span className="text-[10px] font-semibold uppercase">Jun</span>
            <span className="text-lg font-bold leading-none">12</span>
          </div>
          <div>
            <div className="text-sm font-medium">Anticoagulation review</div>
            <div className="text-xs text-slate-400">10:30 AM · Dr. A. Patel</div>
          </div>
        </div>
        <button className="mt-4 w-full cursor-pointer rounded-lg border border-slate-200 py-2 text-xs font-medium text-slate-600 hover:bg-slate-50">
          Reschedule
        </button>
      </div>

      {/* Care team message */}
      <div className="rounded-2xl border border-slate-200 bg-white p-5 shadow-sm">
        <h3 className="mb-3 text-sm font-semibold">From your care team</h3>
        <div className="flex gap-3">
          <div className="flex h-9 w-9 shrink-0 items-center justify-center rounded-full bg-sky-100 text-sm font-semibold text-sky-700">RO</div>
          <div>
            <div className="text-sm text-slate-700">
              &ldquo;Hi Aditya — remember to keep your INR check appointment this week. Reach out with any questions.&rdquo;
            </div>
            <div className="mt-1 text-xs text-slate-400">R. Okafor, PharmD · 2h ago</div>
          </div>
        </div>
      </div>

      {/* Coverage summary */}
      <div className="rounded-2xl border border-slate-200 bg-white p-5 shadow-sm">
        <h3 className="mb-3 text-sm font-semibold">Coverage</h3>
        <dl className="space-y-2 text-sm">
          <div className="flex justify-between"><dt className="text-slate-400">Plan</dt><dd className="font-medium">Basic PPO</dd></div>
          <div className="flex justify-between"><dt className="text-slate-400">Member ID</dt><dd className="font-medium">PB-100482</dd></div>
          <div className="flex justify-between"><dt className="text-slate-400">Rx deductible</dt><dd className="font-medium">$120 / $250</dd></div>
          <div className="flex justify-between"><dt className="text-slate-400">Status</dt><dd className="font-medium text-emerald-600">Active</dd></div>
        </dl>
      </div>

      {/* Health tip */}
      <div className="rounded-2xl border border-emerald-200 bg-emerald-50 p-5">
        <h3 className="mb-1 text-sm font-semibold text-emerald-800">💡 Health tip</h3>
        <p className="text-xs text-emerald-700">
          On warfarin? Keep vitamin-K intake (leafy greens) consistent week to week to stabilize your INR.
        </p>
      </div>
    </div>
  );
}
