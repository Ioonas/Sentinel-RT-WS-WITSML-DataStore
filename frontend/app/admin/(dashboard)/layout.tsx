import type { ReactNode } from "react";
import { ReauthProvider } from "@/components/Reauth";
import { Shell } from "@/components/Shell";

export default function DashboardLayout({ children }: { children: ReactNode }) {
  return (
    <ReauthProvider>
      <Shell>{children}</Shell>
    </ReauthProvider>
  );
}
