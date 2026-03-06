import { useNavigate, useLocation } from "react-router-dom";
import {
  Home,
  UserRound,
  Gamepad2,
  BookOpen,
  XCircle,
  Plus,
  Trophy,
  Search,
  History,
  LogOut,
  Menu,
  X,
} from "lucide-react";
import { useState, useEffect } from "react";

const NAV_ITEMS = [
  { path: "/me", icon: UserRound, label: "Profile" },
  { path: "/?action=play", icon: Gamepad2, label: "Play", matchPath: "/" },
  { path: "/my-words", icon: Plus, label: "My Words" },
  { path: "/wrong-words", icon: XCircle, label: "Wrong Words" },
  { path: "/dictionary", icon: Search, label: "Dictionary" },
  { path: "/leaderboard", icon: Trophy, label: "Leaderboard" },
  { path: "/history", icon: History, label: "History" },
];

const BOTTOM_NAV_ITEMS = [
  { path: "/me", icon: UserRound, label: "Profile" },
  { path: "/?action=play", icon: Gamepad2, label: "Play", matchPath: "/" },
  { path: "/my-words", icon: Plus, label: "Words" },
  { path: "/wrong-words", icon: XCircle, label: "Review" },
];

function isActive(item, location) {
  if (item.matchPath && location.pathname === "/" && location.search.includes(item.matchPath.split("?")[1])) {
    return true;
  }
  if (item.path === "/?action=play" && location.pathname === "/" && (!location.search || location.search === "?action=play")) {
    return true;
  }
  return location.pathname === item.path;
}

export default function AppLayout({ children }) {
  const navigate = useNavigate();
  const location = useLocation();
  const [sidebarOpen, setSidebarOpen] = useState(false);
  const isSignedIn = !!localStorage.getItem("accessToken");
  const nickname = localStorage.getItem("nickname") || "Player";

  // Restore auth from localStorage if missing in localStorage (noop now)
  useEffect(() => {
    // No-op: all auth is now in localStorage
  }, []);

  // Don't show nav on game/lobby/end/join pages
  const gameRoutePatterns = ["/game/", "/lobby/", "/end/", "/join/"];
  const isGameRoute = gameRoutePatterns.some((p) => location.pathname.startsWith(p));

  // Close sidebar on route change
  useEffect(() => {
    setSidebarOpen(false);
  }, [location]);

  if (!isSignedIn || isGameRoute) {
    return <>{children}</>;
  }

  const handleLogout = () => {
    localStorage.removeItem("accessToken");
    localStorage.removeItem("userId");
    localStorage.removeItem("nickname");
    localStorage.removeItem("authType");
    localStorage.removeItem("duoeng_platform_stats");
    navigate("/", { replace: true });
  };

  return (
    <div className="min-h-screen bg-background lg:flex">
      {/* ── Desktop Sidebar ── */}
      <aside className="hidden lg:flex lg:flex-col lg:w-64 lg:fixed lg:inset-y-0 lg:z-30 border-r border-border bg-card">
        {/* Logo / Brand */}
        <div className="flex items-center gap-3 px-6 py-5 border-b border-border">
          <img
            src="/logo.svg"
            alt="DuoVocab"
            className="h-9 w-9 rounded-full shadow-soft"
          />
          <div>
            <p className="font-heading text-lg font-bold leading-tight">DuoVocab</p>
            <p className="text-xs text-muted-foreground">Vocabulary Duel</p>
          </div>
        </div>

        {/* User */}
        <div className="flex items-center gap-3 px-6 py-4">
          <div className="w-9 h-9 rounded-full bg-primary flex items-center justify-center text-primary-foreground font-bold text-sm">
            {nickname[0].toUpperCase()}
          </div>
          <div className="min-w-0 flex-1">
            <p className="text-sm font-medium truncate">{nickname}</p>
            <p className="text-xs text-muted-foreground">
              {localStorage.getItem("authType") === "google" ? "Google" : "Guest"}
            </p>
          </div>
        </div>

        {/* Nav Links */}
        <nav className="flex-1 px-3 py-2 space-y-1 overflow-y-auto">
          {NAV_ITEMS.map((item) => {
            const Icon = item.icon;
            const active = isActive(item, location);
            return (
              <button
                key={item.path}
                onClick={() => navigate(item.path)}
                className={`w-full flex items-center gap-3 px-3 py-2.5 rounded-xl text-sm font-medium transition-all ${
                  active
                    ? "bg-primary/10 text-primary"
                    : "text-muted-foreground hover:bg-muted hover:text-foreground"
                }`}
              >
                <Icon className="w-4.5 h-4.5 flex-shrink-0" />
                <span>{item.label}</span>
              </button>
            );
          })}
        </nav>

        {/* Logout */}
        <div className="px-3 py-4 border-t border-border">
          <button
            onClick={handleLogout}
            className="w-full flex items-center gap-3 px-3 py-2.5 rounded-xl text-sm font-medium text-destructive hover:bg-destructive/10 transition-all"
          >
            <LogOut className="w-4.5 h-4.5" />
            <span>Log Out</span>
          </button>
        </div>
      </aside>

      {/* ── Main Content ── */}
      <main className="flex-1 lg:ml-64 pb-20 lg:pb-0">
        {/* Mobile top bar */}
        <div className="lg:hidden flex items-center justify-between px-4 py-3 border-b border-border bg-card/80 backdrop-blur sticky top-0 z-20">
          <div className="flex items-center gap-2">
            <img src="/logo.svg" alt="DuoVocab" className="h-7 w-7 rounded-full" />
            <span className="font-heading text-base font-bold">DuoVocab</span>
          </div>
          <button
            onClick={() => setSidebarOpen(!sidebarOpen)}
            className="p-2 rounded-xl hover:bg-muted transition-colors"
          >
            {sidebarOpen ? <X className="w-5 h-5" /> : <Menu className="w-5 h-5" />}
          </button>
        </div>

        {/* Mobile slide-out nav */}
        {sidebarOpen && (
          <>
            <div
              className="lg:hidden fixed inset-0 bg-black/40 z-30"
              onClick={() => setSidebarOpen(false)}
            />
            <div className="lg:hidden fixed right-0 top-0 bottom-0 w-64 bg-card z-40 shadow-xl animate-fade-in-up border-l border-border">
              <div className="flex items-center justify-between px-4 py-4 border-b border-border">
                <div className="flex items-center gap-2">
                  <div className="w-8 h-8 rounded-full bg-primary flex items-center justify-center text-primary-foreground font-bold text-xs">
                    {nickname[0].toUpperCase()}
                  </div>
                  <span className="text-sm font-medium">{nickname}</span>
                </div>
                <button
                  onClick={() => setSidebarOpen(false)}
                  className="p-1 rounded-lg hover:bg-muted"
                >
                  <X className="w-5 h-5" />
                </button>
              </div>
              <nav className="px-3 py-3 space-y-1">
                {NAV_ITEMS.map((item) => {
                  const Icon = item.icon;
                  const active = isActive(item, location);
                  return (
                    <button
                      key={item.path}
                      onClick={() => navigate(item.path)}
                      className={`w-full flex items-center gap-3 px-3 py-2.5 rounded-xl text-sm font-medium transition-all ${
                        active
                          ? "bg-primary/10 text-primary"
                          : "text-muted-foreground hover:bg-muted hover:text-foreground"
                      }`}
                    >
                      <Icon className="w-4 h-4 flex-shrink-0" />
                      <span>{item.label}</span>
                    </button>
                  );
                })}
              </nav>
              <div className="px-3 py-4 border-t border-border mt-auto absolute bottom-0 left-0 right-0">
                <button
                  onClick={handleLogout}
                  className="w-full flex items-center gap-3 px-3 py-2.5 rounded-xl text-sm font-medium text-destructive hover:bg-destructive/10 transition-all"
                >
                  <LogOut className="w-4 h-4" />
                  <span>Log Out</span>
                </button>
              </div>
            </div>
          </>
        )}

        {children}
      </main>

      {/* ── Mobile Bottom Navigation ── */}
      <nav className="lg:hidden fixed bottom-0 inset-x-0 z-20 bg-card/95 backdrop-blur border-t border-border safe-area-bottom">
        <div className="flex items-center justify-around py-2">
          {BOTTOM_NAV_ITEMS.map((item) => {
            const Icon = item.icon;
            const active = isActive(item, location);
            return (
              <button
                key={item.path}
                onClick={() => navigate(item.path)}
                className={`flex flex-col items-center gap-0.5 px-3 py-1 rounded-xl transition-all ${
                  active
                    ? "text-primary"
                    : "text-muted-foreground hover:text-foreground"
                }`}
              >
                <Icon className={`w-5 h-5 ${active ? "stroke-[2.5]" : ""}`} />
                <span className="text-[10px] font-medium">{item.label}</span>
              </button>
            );
          })}
        </div>
      </nav>
    </div>
  );
}
