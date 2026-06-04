"use client";
import { Button } from "@/components/ui/button";

export function PharmacistActions({
  onAction, busy, hasAlternative,
}: { onAction: (action: string) => void; busy: boolean; hasAlternative: boolean }) {
  return (
    <div className="mt-3 space-y-2">
      {hasAlternative ? (
        <Button className="w-full" disabled={busy} onClick={() => onAction("approve_alternative")}>
          Approve alternative &amp; notify patient
        </Button>
      ) : (
        <Button className="w-full" disabled={busy} onClick={() => onAction("override")}>
          Approve &amp; notify patient
        </Button>
      )}
      <div className="flex gap-2">
        <Button variant="outline" size="sm" className="flex-1" disabled={busy} onClick={() => onAction("override")}>Override</Button>
        <Button variant="outline" size="sm" className="flex-1" disabled={busy} onClick={() => onAction("reject")}>Reject</Button>
      </div>
    </div>
  );
}
