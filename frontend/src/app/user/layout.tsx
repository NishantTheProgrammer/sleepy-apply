import type { Metadata } from "next";
import Sidebar from "@/components/Sidebar";

export const metadata: Metadata = {
  title: "Sleepy Apply — Dashboard",
};

export default function UserLayout({ children }: { children: React.ReactNode }) {
  return (
    <>
      <Sidebar />
      <main className="min-h-screen pt-14 lg:pt-0 lg:ml-64 max-w-full overflow-x-hidden">
        {children}
      </main>
    </>
  );
}
