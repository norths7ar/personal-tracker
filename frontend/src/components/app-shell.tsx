import "@/components/app-shell.css";
import {
  BarChart3,
  BookOpen,
  CheckSquare2,
  ListTodo,
  LogOut,
  PencilLine,
  Settings,
  Utensils,
} from "lucide-react";
import { useEffect, useRef, type ReactNode } from "react";
import { useQueryClient } from "@tanstack/react-query";
import { useCapturePending } from "@/features/pending/use-capture-pending";
import { NavLink } from "react-router-dom";

import { Button } from "@/components/ui/button";
import { cn } from "@/lib/utils";

type AppShellProps = {
  children: ReactNode;
  onLogout: () => void;
};

export function AppShell({ children, onLogout }: AppShellProps) {
  const pending = useCapturePending();
  const client = useQueryClient();
  const lastToken = useRef<string | null>(null);
  const token = pending.data?.change_token;
  useEffect(() => {
    if (token !== undefined && lastToken.current !== null && lastToken.current !== token) {
      void client.invalidateQueries({ queryKey: ["ledger"] });
      void client.invalidateQueries({ queryKey: ["diet"] });
      void client.invalidateQueries({ queryKey: ["capture", "home"] });
      void client.invalidateQueries({ queryKey: ["capture", "suggestions"] });
    }
    if (token !== undefined) lastToken.current = token;
  }, [client, token]);
  const pendingCount = pending.data?.pending_count ?? 0;
  return (
    <div className="app-shell">
      <aside className="app-sidebar">
        <div className="app-brand">
          <span className="app-brand-mark" aria-hidden="true">
            拾
          </span>
          <span>
            拾记<small>日常，自有脉络</small>
          </span>
        </div>
        <nav className="app-navigation">
          <div className="navigation-section">日常</div>
          <NavItem to="/todo" icon={<ListTodo size={17} />} label="待办" />
          <NavItem to="/record" icon={<PencilLine size={17} />} label="记录" />
          <NavItem
            to="/pending"
            icon={<CheckSquare2 size={17} />}
            label="待处理"
            count={pendingCount}
          />
          <div className="navigation-section">回看</div>
          <NavItem to="/ledger" icon={<BookOpen size={17} />} label="账目" />
          <NavItem to="/analysis" icon={<BarChart3 size={17} />} label="开销分析" />
          <NavItem to="/diet" icon={<Utensils size={17} />} label="饮食" />
          <div className="navigation-section">偏好</div>
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
              {to === "/pending" && pendingCount > 0 && (
                <span className="navigation-count" aria-label={`${pendingCount} 项待处理`}>
                  {pendingCount}
                </span>
              )}
            </NavLink>
          ))}
        </nav>
        <main className="app-content">{children}</main>
      </div>
    </div>
  );
}

function NavItem({
  to,
  icon,
  label,
  count = 0,
}: {
  to: string;
  icon: ReactNode;
  label: string;
  count?: number;
}) {
  return (
    <NavLink
      to={to}
      className={({ isActive }) =>
        cn("app-navigation-link", isActive ? "navigation-selected" : "navigation-idle")
      }
    >
      {icon}
      {label}
      {count > 0 && (
        <span className="navigation-count" aria-label={`${count} 项待处理`}>
          {count}
        </span>
      )}
    </NavLink>
  );
}
