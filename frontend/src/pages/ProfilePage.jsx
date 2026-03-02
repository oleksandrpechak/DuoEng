import { useState, useEffect } from "react";
import { useNavigate } from "react-router-dom";
import { Button } from "@/components/ui/button";
import { Card, CardContent } from "@/components/ui/card";
import {
  Trophy,
  Gamepad2,
  BookOpen,
  BarChart3,
  LogOut,
  Loader2,
  History,
  Target,
  Clock,
  ChevronRight,
  Shield,
} from "lucide-react";
import { toast } from "sonner";
import api from "@/lib/api";

export default function ProfilePage() {
  const navigate = useNavigate();
  const [stats, setStats] = useState(null);
  const [isLoading, setIsLoading] = useState(true);

  const accessToken = sessionStorage.getItem("accessToken");
  const userId = sessionStorage.getItem("userId");
  const nickname = sessionStorage.getItem("nickname") || "Player";
  const authType = sessionStorage.getItem("authType") || "guest";

  // Redirect to home if not logged in
  useEffect(() => {
    if (!accessToken || !userId) {
      navigate("/", { replace: true });
    }
  }, [accessToken, userId, navigate]);

  // Fetch player stats
  useEffect(() => {
    if (!accessToken || !userId) return;

    const fetchStats = async () => {
      try {
        const response = await api.get(`/players/${userId}/stats`);
        setStats(response.data);
      } catch (error) {
        console.error("Failed to fetch stats", error);
      }
      setIsLoading(false);
    };
    fetchStats();
  }, [accessToken, userId]);

  const handleLogout = () => {
    sessionStorage.removeItem("accessToken");
    sessionStorage.removeItem("userId");
    sessionStorage.removeItem("nickname");
    sessionStorage.removeItem("authType");
    sessionStorage.removeItem("duoeng_platform_stats");
    toast.success("Logged out");
    navigate("/", { replace: true });
  };

  if (!accessToken || !userId) return null;

  const avatarLetter = (nickname || "P")[0].toUpperCase();

  return (
    <div className="min-h-screen bg-background flex flex-col items-center p-4 pt-8">
      <div className="w-full max-w-md space-y-6 animate-fade-in-up">

        {/* ─── Avatar + Identity ─── */}
        <div className="text-center">
          <div className="w-24 h-24 mx-auto rounded-full bg-primary flex items-center justify-center text-primary-foreground text-4xl font-bold shadow-lg mb-4">
            {avatarLetter}
          </div>
          <h1 className="font-heading text-3xl font-bold text-foreground">{nickname}</h1>

          {/* ELO badge */}
          <div className="flex items-center justify-center gap-2 mt-2">
            <Trophy className="w-5 h-5 text-yellow-500" />
            <span className="text-lg font-semibold text-foreground">
              {isLoading ? "—" : stats?.elo ?? 1000}
            </span>
          </div>

          {/* Auth type badge */}
          <div className="mt-2 inline-flex items-center gap-1.5 px-3 py-1 rounded-full text-xs font-medium bg-muted text-muted-foreground">
            <Shield className="w-3.5 h-3.5" />
            {authType === "google" ? "Google account" : "Guest account"}
          </div>
        </div>

        {/* ─── Stats Cards ─── */}
        {isLoading ? (
          <div className="flex justify-center py-8">
            <Loader2 className="w-8 h-8 animate-spin text-primary" />
          </div>
        ) : stats ? (
          <div className="grid grid-cols-3 gap-3">
            <Card className="rounded-2xl border-0 shadow-soft">
              <CardContent className="p-4 text-center">
                <p className="text-xs text-muted-foreground mb-1">Wins</p>
                <p className="font-heading text-2xl font-bold text-accent-foreground">{stats.wins}</p>
              </CardContent>
            </Card>
            <Card className="rounded-2xl border-0 shadow-soft">
              <CardContent className="p-4 text-center">
                <p className="text-xs text-muted-foreground mb-1">Losses</p>
                <p className="font-heading text-2xl font-bold text-destructive">{stats.losses}</p>
              </CardContent>
            </Card>
            <Card className="rounded-2xl border-0 shadow-soft">
              <CardContent className="p-4 text-center">
                <p className="text-xs text-muted-foreground mb-1">Games</p>
                <p className="font-heading text-2xl font-bold">{stats.total_games}</p>
              </CardContent>
            </Card>
          </div>
        ) : null}

        {stats && (
          <div className="grid grid-cols-2 gap-3">
            <Card className="rounded-2xl border-0 shadow-soft">
              <CardContent className="p-4 flex items-center gap-3">
                <Target className="w-5 h-5 text-primary flex-shrink-0" />
                <div>
                  <p className="text-xs text-muted-foreground">Win Rate</p>
                  <p className="font-semibold">{stats.win_rate != null ? `${(stats.win_rate * 100).toFixed(1)}%` : "—"}</p>
                </div>
              </CardContent>
            </Card>
            <Card className="rounded-2xl border-0 shadow-soft">
              <CardContent className="p-4 flex items-center gap-3">
                <Clock className="w-5 h-5 text-secondary-foreground flex-shrink-0" />
                <div>
                  <p className="text-xs text-muted-foreground">Avg Response</p>
                  <p className="font-semibold">{stats.avg_response_time != null ? `${stats.avg_response_time.toFixed(1)}s` : "—"}</p>
                </div>
              </CardContent>
            </Card>
          </div>
        )}

        {/* ─── Action Buttons ─── */}
        <div className="space-y-3">
          <Button
            className="w-full rounded-2xl h-14 text-base font-bold bg-primary hover:bg-primary/90 flex items-center justify-between px-6"
            onClick={() => navigate("/?action=play")}
          >
            <span className="flex items-center gap-3">
              <Gamepad2 className="w-5 h-5" />
              Play Now
            </span>
            <ChevronRight className="w-5 h-5" />
          </Button>

          <div className="grid grid-cols-2 gap-3">
            <Button
              variant="outline"
              className="rounded-2xl h-12 text-sm font-medium flex items-center gap-2"
              onClick={() => navigate("/?tab=history")}
            >
              <History className="w-4 h-4" />
              History
            </Button>
            <Button
              variant="outline"
              className="rounded-2xl h-12 text-sm font-medium flex items-center gap-2"
              onClick={() => navigate("/?tab=dictionary")}
            >
              <BookOpen className="w-4 h-4" />
              Dictionary
            </Button>
          </div>

          <Button
            variant="outline"
            className="w-full rounded-2xl h-12 text-sm font-medium flex items-center justify-center gap-2"
            onClick={() => navigate("/?tab=leaderboard")}
          >
            <BarChart3 className="w-4 h-4" />
            Leaderboard
          </Button>
        </div>

        {/* ─── Logout ─── */}
        <Button
          variant="ghost"
          className="w-full rounded-2xl h-12 text-destructive hover:text-destructive hover:bg-destructive/10 font-medium flex items-center justify-center gap-2"
          onClick={handleLogout}
        >
          <LogOut className="w-4 h-4" />
          Log Out
        </Button>
      </div>
    </div>
  );
}
