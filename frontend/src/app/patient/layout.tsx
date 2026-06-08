import type { ReactNode } from "react";
import { PatientShell } from "@/components/patient/PatientShell";

export default function PatientLayout({ children }: { children: ReactNode }) {
  return <PatientShell>{children}</PatientShell>;
}
