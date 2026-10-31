import "@/styles/app-shell.css";
import {
  BarChart3,
  BookOpen,
  CalendarClock,
  CheckSquare2,
  LogOut,
  ListTodo,
  PencilLine,
  Settings,
  Utensils,
} from "lucide-react";
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
    <div className="app-shell">
      <aside className="app-sidebar">
        <div className="app-brand">拾记</div>
        <nav className="app-navigation">
          <NavItem to="/todo" icon={<ListTodo size={17} />} label="待办" />
          <NavItem to="/record" icon={<PencilLine size={17} />} label="记录" />
          <NavItem to="/pending" icon={<CheckSquare2 size={17} />} label="待处理" />
          <NavItem to="/ledger" icon={<BookOpen size={17} />} label="账目" />
          <NavItem to="/analysis" icon={<BarChart3 size={17} />} label="开销分析" />
          <NavItem to="/cross-period" icon={<CalendarClock size={17} />} label="跨期费用" />
          <NavItem to="/diet" icon={<Utensils size={17} />} label="饮食" />
          <NavItem to="/settings" icon={<Settings size={17} />} label="设置" />
        </nav>
        <Button className="app-logout" variant="ghost" onClick={onLogout}>
          <LogOut size={16} />
          退出登录
        </Button>
      </aside>
      <div className="app-main">
        <header className="app-mobile-header">
          <span className="section-title">拾记</span>
          <Button size="sm" variant="ghost" onClick={onLogout}>
            退出
          </Button>
        </header>
        <nav aria-label="页面导航" className="app-mobile-navigation">
          {(
            [
              ["/todo", "待办"],
              ["/record", "记录"],
              ["/pending", "待处理"],
              ["/ledger", "账目"],
              ["/analysis", "开销分析"],
              ["/cross-period", "跨期费用"],
              ["/diet", "饮食"],
              ["/settings", "设置"],
            ] as const
          ).map(([to, label]) => (
            <NavLink
              key={to}
              to={to}
              className={({ isActive }) =>
                cn("app-mobile-link", isActive ? "navigation-selected" : "navigation-label")
              }
            >
              {label}
            </NavLink>
          ))}
        </nav>
        <main className="app-content">{children}</main>
      </div>
    </div>
  );
}

function NavItem({ to, icon, label }: { to: string; icon: ReactNode; label: string }) {
  return (
    <NavLink
      to={to}
      className={({ isActive }) =>
        cn("app-navigation-link", isActive ? "navigation-selected" : "navigation-idle")
      }
    >
      {icon}
      {label}
    </NavLink>
  );
}
