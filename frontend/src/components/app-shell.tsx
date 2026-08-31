import { BarChart3, BookOpen, CalendarClock, CheckSquare2, LogOut, PencilLine, Utensils } from "lucide-react";
import type { ReactNode } from "react";
import { NavLink } from "react-router-dom";

import { Button } from "@/components/ui/button";
import { cn } from "@/lib/utils";

type AppShellProps = {
  children: ReactNode;
  onLogout: () => void;
};

export function AppShell({ children, onLogout }: AppShellProps) {
  return (
    <div className="min-h-screen bg-stone-50 text-neutral-900">
      <aside className="fixed inset-y-0 left-0 hidden w-56 border-r border-neutral-200 bg-white p-4 md:flex md:flex-col">
        <div className="mb-8 px-2 text-lg font-semibold">personal-tracker</div>
        <nav className="space-y-1">
          <NavItem to="/record" icon={<PencilLine size={17} />} label="记录" />
          <NavItem to="/pending" icon={<CheckSquare2 size={17} />} label="待处理" />
          <NavItem to="/ledger" icon={<BookOpen size={17} />} label="账目" />
          <NavItem to="/analysis" icon={<BarChart3 size={17} />} label="开销分析" />
          <NavItem to="/cross-period" icon={<CalendarClock size={17} />} label="跨期费用" />
          <NavItem to="/diet" icon={<Utensils size={17} />} label="饮食" />
        </nav>
        <Button className="mt-auto justify-start" variant="ghost" onClick={onLogout}>
          <LogOut size={16} />
          退出登录
        </Button>
      </aside>
      <div className="md:pl-56">
        <header className="flex h-14 items-center justify-between border-b border-neutral-200 bg-white px-4 md:hidden">
          <span className="font-semibold">personal-tracker</span>
          <Button size="sm" variant="ghost" onClick={onLogout}>退出</Button>
        </header>
        <main className="mx-auto w-full max-w-[1600px] p-4 sm:p-6 lg:p-8">{children}</main>
      </div>
    </div>
  );
}

function NavItem({ to, icon, label }: { to: string; icon: ReactNode; label: string }) {
  return (
    <NavLink
      to={to}
      className={({ isActive }) =>
        cn(
          "flex items-center gap-3 rounded-md px-3 py-2 text-sm transition-colors",
          isActive ? "bg-neutral-900 text-white" : "text-neutral-600 hover:bg-neutral-100",
        )
      }
    >
      {icon}
      {label}
    </NavLink>
  );
}
