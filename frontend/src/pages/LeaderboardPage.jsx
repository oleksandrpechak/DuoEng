import { useState, useEffect } from "react";
import { useNavigate } from "react-router-dom";
import { Button } from "@/components/ui/button";
import { Skeleton } from "@/components/ui/skeleton";
import {
  Trophy,
  Medal,
  Loader2,
} from "lucide-react";
import { toast } from "sonner";
import api from "@/lib/api";

const PERIODS = [
  { value: "today", label: "Today" },
  { value: "week", label: "This Week" },
  { value: "all", label: "All Time" },
];

function MedalIcon({ rank }) {
  if (rank === 1) return <span className="text-lg">🥇</span>;
  if (rank === 2) return <span className="text-lg">🥈</span>;
  if (rank === 3) return <span className="text-lg">🥉</span>;
  return <span className="w-6 text-center text-sm font-medium text-muted-foreground">#{rank}</span>;
}

export default function LeaderboardPage() {
  const navigate = useNavigate();
  const [period, setPeriod] = useState("week");
  const [rows, setRows] = useState([]);
  const [isLoading, setIsLoading] = useState(true);
  const [myStats, setMyStats] = useState(null);

  const accessToken = sessionStorage.getItem("accessToken");
  const userId = sessionStorage.getItem("userId");

  useEffect(() => {
    document.title = "Leaderboard — DuoEng";
    if (!accessToken || !userId) navigate("/", { replace: true });
  }, [accessToken, userId, navigate]);

  const fetchLeaderboard = async (p) => {
    setIsLoading(true);
    try {
      const res = await api.get("/leaderboard", { params: { limit: 50, period: p } });
      setRows(res.data || []);
    } catch (err) {
      toast.error("Failed to load leaderboard");
    }
    setIsLoading(false);
  };

  // Load my stats
  useEffect(() => {
    if (!userId) return;
    api
      .get(`/players/${userId}/stats`)
      .then((res) => setMyStats(res.data))
      .catch(() => {});
  }, [userId]);

  useEffect(() => {
    fetchLeaderboard(period);
  }, [period]);

  const myRow = rows.find((r) => r.player_id === userId);
  const myRank = myRow ? rows.indexOf(myRow) + 1 : null;

  return (
    <div className="min-h-screen bg-background">
      <div className="max-w-3xl mx-auto px-4 py-6">
        {/* Header */}
        <div className="flex items-center gap-3 mb-6">
          <Trophy className="w-7 h-7 text-yellow-500" />
          <h1 className="font-heading text-2xl sm:text-3xl font-bold">Leaderboard</h1>
        </div>

        {/* Period tabs */}
        <div className="flex gap-1 p-1 bg-muted rounded-full max-w-sm mb-6">
          {PERIODS.map((p) => (
            <button
              key={p.value}
              className={`flex-1 py-2 rounded-full text-sm font-medium transition-all ${
                period === p.value
                  ? "bg-card shadow-sm text-foreground"
                  : "text-muted-foreground hover:text-foreground"
              }`}
              onClick={() => setPeriod(p.value)}
              disabled={isLoading}
            >
              {p.label}
            </button>
          ))}
        </div>

        {/* Loading skeleton */}
        {isLoading && (
          <div className="space-y-2">
            {Array.from({ length: 8 }).map((_, i) => (
              <div key={i} className="flex items-center gap-4 rounded-xl border border-border bg-card p-3">
                <Skeleton className="h-6 w-6 rounded-full" />
                <Skeleton className="h-5 w-28" />
                <div className="ml-auto flex gap-4">
                  <Skeleton className="h-5 w-16" />
                  <Skeleton className="h-5 w-12" />
                </div>
              </div>
            ))}
          </div>
        )}

        {/* Empty state */}
        {!isLoading && rows.length === 0 && (
          <div className="text-center py-16">
            <Trophy className="w-14 h-14 mx-auto text-muted-foreground/30 mb-4" />
            <p className="text-lg font-medium text-muted-foreground">
              {period === "today"
                ? "No games played today yet. Be the first! 🎮"
                : "No leaderboard data available."}
            </p>
          </div>
        )}

        {/* Table */}
        {!isLoading && rows.length > 0 && (
          <div className="rounded-2xl border border-border bg-card overflow-hidden">
            {/* Header */}
            <div className="hidden sm:grid grid-cols-[3rem_1fr_5rem_4rem_4rem_5rem] gap-2 px-4 py-2.5 bg-muted/50 text-xs font-semibold text-muted-foreground uppercase tracking-wider sticky top-0 z-10">
              <span>#</span>
              <span>Player</span>
              <span className="text-right">ELO</span>
              <span className="text-right">W</span>
              <span className="text-right hidden sm:block">L</span>
              <span className="text-right">Win %</span>
            </div>

            <div className="divide-y divide-border">
              {rows.map((row, i) => {
                const rank = i + 1;
                const isMe = row.player_id === userId;
                const winRate = row.total_games > 0
                  ? Math.round((row.wins / row.total_games) * 100)
                  : 0;

                return (
                  <div
                    key={row.player_id}
                    className={`grid grid-cols-[3rem_1fr_5rem_4rem_5rem] sm:grid-cols-[3rem_1fr_5rem_4rem_4rem_5rem] gap-2 px-4 py-3 items-center text-sm transition-colors ${
                      isMe ? "bg-primary/5" : "hover:bg-muted/30"
                    }`}
                  >
                    <div className="flex items-center justify-center">
                      <MedalIcon rank={rank} />
                    </div>
                    <div className="flex items-center gap-2 min-w-0">
                      <div className="w-7 h-7 rounded-full bg-primary/20 flex items-center justify-center text-xs font-bold text-primary flex-shrink-0">
                        {row.nickname[0]?.toUpperCase()}
                      </div>
                      <span className="font-medium truncate">{row.nickname}</span>
                      {isMe && (
                        <span className="px-1.5 py-0.5 rounded text-[10px] font-semibold bg-primary/20 text-primary flex-shrink-0">
                          You
                        </span>
                      )}
                    </div>
                    <span className="text-right font-semibold">{row.elo}</span>
                    <span className="text-right text-green-600 dark:text-green-400 font-medium">{row.wins}</span>
                    <span className="text-right text-red-500 font-medium hidden sm:block">{row.losses}</span>
                    <span className="text-right font-medium">{winRate}%</span>
                  </div>
                );
              })}
            </div>
          </div>
        )}

        {/* My rank footer — show if I'm not in the list */}
        {!isLoading && myStats && !myRow && (
          <div className="mt-4 rounded-2xl border border-primary/30 bg-primary/5 px-4 py-3 flex flex-wrap items-center justify-center gap-4 text-sm">
            <span className="font-medium">Your rank: <span className="font-bold">Not in top 50</span></span>
            <span className="text-muted-foreground">•</span>
            <span>ELO: <span className="font-bold">{myStats.elo}</span></span>
            <span className="text-muted-foreground">•</span>
            <span>
              Win rate:{" "}
              <span className="font-bold">
                {myStats.total_games > 0
                  ? Math.round((myStats.wins / myStats.total_games) * 100)
                  : 0}
                %
              </span>
            </span>
          </div>
        )}

        {/* My rank footer — show if I am in the list */}
        {!isLoading && myRow && myRank && (
          <div className="mt-4 rounded-2xl border border-primary/30 bg-primary/5 px-4 py-3 flex flex-wrap items-center justify-center gap-4 text-sm">
            <span className="font-medium">
              Your rank: <span className="font-bold">#{myRank}</span>
            </span>
            <span className="text-muted-foreground">•</span>
            <span>ELO: <span className="font-bold">{myRow.elo}</span></span>
            <span className="text-muted-foreground">•</span>
            <span>
              Win rate:{" "}
              <span className="font-bold">
                {myRow.total_games > 0 ? Math.round((myRow.wins / myRow.total_games) * 100) : 0}%
              </span>
            </span>
          </div>
        )}
      </div>
    </div>
  );
}
