import type { ReactNode } from "react";
import { ClinicShell } from "@/components/clinic/ClinicShell";

export default function ClinicLayout({ children }: { children: ReactNode }) {
  return <ClinicShell>{children}</ClinicShell>;
}
