"use client";

import { useRouter } from "next/navigation";

type ActiveMenu = "queue" | "workbench" | "admin";

interface AppSidebarProps {
  activeMenu: ActiveMenu;
}

export default function AppSidebar({ activeMenu }: AppSidebarProps) {
  const router = useRouter();

  function menuClass(menu: ActiveMenu) {
    const isActive = activeMenu === menu;
    return isActive
      ? "w-full rounded-md border border-slate-300 bg-white px-3 py-2.5 text-left font-semibold text-slate-900 shadow-sm"
      : "w-full rounded-md px-3 py-2.5 text-left font-semibold text-slate-700 hover:bg-slate-200";
  }

  const navigationItems: Array<{ key: ActiveMenu; label: string; path: string; className?: string }> = [
    { key: "queue", label: "민원 선택", path: "/" },
    { key: "workbench", label: "처리 워크벤치", path: "/workbench", className: "mt-1" },
    { key: "admin", label: "관리자 통계", path: "/admin", className: "mt-1" },
  ];

  return (
    <aside className="w-52 shrink-0 border-r border-slate-300 bg-[#d9dee7] flex flex-col">
      <div className="flex items-center justify-between border-b border-slate-300 px-4 py-4 text-xl font-black tracking-tight text-slate-900">
        <span>CRM AI</span>
        <span className="text-sm">◀</span>
      </div>

      <div className="flex-1 px-2 py-6 text-sm">
        {navigationItems.map((item) => (
          <button
            key={item.key}
            type="button"
            onClick={() => router.push(item.path)}
            className={`${item.className || ""} ${menuClass(item.key)}`.trim()}
          >
            {item.label}
          </button>
        ))}
      </div>

      <div className="border-t border-slate-300 px-3 py-4 text-[10px] text-slate-500">© CRM AI System</div>
    </aside>
  );
}
