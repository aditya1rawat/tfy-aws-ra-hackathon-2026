import type { ReactNode } from "react";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { cn } from "@/lib/utils";

export function Panel({
  title, action, children, tone = "light",
}: { title: string; action?: ReactNode; children: ReactNode; tone?: "light" | "dark" }) {
  const dark = tone === "dark";
  return (
    <Card className={cn("flex h-full flex-col", dark && "bg-zinc-900 text-zinc-100 ring-1 ring-zinc-800")}>
      <CardHeader className="flex flex-row items-center justify-between space-y-0 pb-2">
        <CardTitle className={cn("text-sm font-semibold", dark && "text-zinc-100")}>{title}</CardTitle>
        {action}
      </CardHeader>
      <CardContent className="flex-1 overflow-auto">{children}</CardContent>
    </Card>
  );
}
