import { Badge } from "@/components/ui/badge";

const TONE: Record<string, string> = {
  done: "bg-green-600",
  in_progress: "bg-blue-600",
  pending: "bg-zinc-500",
  queued: "bg-amber-600",
  escalated: "bg-red-600",
  failed: "bg-red-700",
};

export function StatusBadge({ status }: { status: string }) {
  return <Badge className={`${TONE[status] ?? "bg-zinc-500"} text-white`}>{status}</Badge>;
}
