"use client";
import { useState } from "react";
import { Button } from "@/components/ui/button";
import type { RequestNarrative } from "@/lib/types";

export function OutcomeCard({ narrative }: { narrative: RequestNarrative }) {
  const [accepted, setAccepted] = useState(false);
  const alt = narrative.suggested_alternative;
  if (!alt) return null;
  return (
    <div className="mt-3 space-y-2">
      <div className="rounded-lg border border-green-300 bg-green-50 p-3 text-sm">
        <div className="font-semibold">Pharmacist suggests</div>
        <div className="text-zinc-600">{alt.med} — {alt.reason}</div>
      </div>
      {accepted ? (
        <div className="text-center text-xs text-green-700">Alternative accepted ✓</div>
      ) : (
        <Button className="h-10 w-full" onClick={() => setAccepted(true)}>
          Accept alternative
        </Button>
      )}
    </div>
  );
}
