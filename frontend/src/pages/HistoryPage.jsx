import { useState, useEffect, useCallback } from "react";
import { useNavigate } from "react-router-dom";
import { Button } from "@/components/ui/button";
import { Skeleton } from "@/components/ui/skeleton";
import {
  Trophy,
  XCircle,
  ChevronLeft,
  ChevronRight,
  Loader2,
  Gamepad2,
  BarChart3,
  Clock,
  Target,
  Swords,
  Bot,
  Filter,
} from "lucide-react";
import { toast } from "sonner";
import api from "@/lib/api";
import timeAgo from "@/lib/timeAgo";

const PER_PAGE = 10;

const OUTCOME_FILTERS = [
  { value: "all", label: "All" },
  { value: "won", label: "Wins" },
  { value: "lost", label: "Losses" },
];

function StatCard({ icon: Icon, label, value, sub, className = "" }) {
  return (
    <div className={`flex flex-col items-center p-4 rounded-2xl border border-border bg-card ${className}`}>
      <Icon className="w-5 h-5 text-muted-foreground mb-1" />
      <span className="text-2xl font-bold tabular-nums">{value}</span>
      <span className="text-xs text-muted-foreground">{label}</span>
      {sub && <span className="text-[10px] text-muted-foreground/70 mt-0.5">{sub}</span>}
    </div>
  );
}

export default function HistoryPage() {
  const navigate = useNavigate();
  const [stats, setStats] = useState(null);
  const [historyData, setHistoryData] = useState(null);
  const [page, setPage] = useState(1);
  const [isLoading, setIsLoading] = useState(true);
  const [isPageLoading, setIsPageLoading] = useState(false);
  const [outcomeFilter, setOutcomeFilter] = useState("all");

  const accessToken = sessionStorage.getItem("accessToken");
  const userId = sessionStorage.getItem("userId");

  useEffect(() => {
    document.title = "Match History — DuoVocab";
    if (!accessToken || !userId) navigate("/", { replace: true });
  }, [accessToken, userId, navigate]);

  // Fetch player stats (summary)
  useEffect(() => {
    if (!accessToken || !userId) return;
    api
      .get(`/players/${userId}/stats`)
      .then((res) => setStats(res.data))
      .catch(() => {});
  }, [accessToken, userId]);

  // Fetch match history
  const fetchHistory = useCallback(
    async (p = 1) => {
      if (!accessToken || !userId) return;
      const loader = p === 1 ? setIsLoading : setIsPageLoading;
      loader(true);
      try {
        const res = await api.get(`/players/${userId}/history`, {
          params: { page: p, per_page: PER_PAGE },
        });
        setHistoryData(res.data);
        setPage(p);
      } catch {
        toast.error("Failed to load match history");
      }
      loader(false);
    },
    [accessToken, userId]
  );

  useEffect(() => {
    fetchHistory(1);
  }, [fetchHistory]);

  const totalPages = historyData
    ? Math.max(1, Math.ceil(historyData.total / (historyData.per_page || PER_PAGE)))
    : 1;

  // Client-side outcome filter (applied on current page data)
  const filteredMatches = (historyData?.matches || []).filter((m) => {
    if (outcomeFilter === "won") return m.won;
    if (outcomeFilter === "lost") return !m.won;
    return true;
  });

  const handleCreateRoom = () => {
    navigate("/?action=play");
  };

  /* ── Rendering ── */

  return (
    <div className="min-h-screen bg-background">
      {/* Header */}
      <div className="border-b border-border bg-card/80 backdrop-blur sticky top-0 z-10">
        <div className="max-w-3xl mx-auto px-4 py-4 flex items-center justify-between">
          <div>
            <h1 className="font-heading text-2xl font-bold">Match History</h1>
            <p className="text-sm text-muted-foreground">
              {historyData ? `${historyData.total} games played` : "Loading…"}
            </p>
          </div>
          <Button
            onClick={handleCreateRoom}
            className="rounded-full gap-2"
          >
            <Swords className="w-4 h-4" />
            <span className="hidden sm:inline">New Game</span>
          </Button>
        </div>
      </div>

      <div className="max-w-3xl mx-auto px-4 py-6 space-y-6">
        {/* Stats Summary */}
        {stats ? (
          <div className="grid grid-cols-2 sm:grid-cols-4 gap-3">
            <StatCard
              icon={Gamepad2}
              label="Games"
              value={stats.total_games}
            />
            <StatCard
              icon={Trophy}
              label="Wins"
              value={stats.wins}
              sub={`${(stats.win_rate * 100).toFixed(0)}% win rate`}
            />
            <StatCard
              icon={BarChart3}
              label="ELO"
              value={stats.elo}
            />
            <StatCard
              icon={Clock}
              label="Avg Time"
              value={`${stats.avg_response_time.toFixed(1)}s`}
              sub="per move"
            />
          </div>
        ) : (
          <div className="grid grid-cols-2 sm:grid-cols-4 gap-3">
            {[...Array(4)].map((_, i) => (
              <Skeleton key={i} className="h-28 rounded-2xl" />
            ))}
          </div>
        )}

        {/* Filters */}
        <div className="flex items-center gap-2 flex-wrap">
          <Filter className="w-4 h-4 text-muted-foreground" />
          {OUTCOME_FILTERS.map((f) => (
            <button
              key={f.value}
              className={`px-3 py-1.5 rounded-full text-xs font-medium border transition-all ${
                outcomeFilter === f.value
                  ? "bg-primary text-primary-foreground border-primary"
                  : "bg-muted text-muted-foreground border-border hover:border-primary/40"
              }`}
              onClick={() => setOutcomeFilter(f.value)}
            >
              {f.label}
            </button>
          ))}
        </div>

        {/* Match List */}
        {isLoading ? (
          <div className="space-y-3">
            {[...Array(5)].map((_, i) => (
              <Skeleton key={i} className="h-24 rounded-2xl" />
            ))}
          </div>
        ) : filteredMatches.length === 0 ? (
          <div className="text-center py-16">
            <Gamepad2 className="w-12 h-12 mx-auto text-muted-foreground/40 mb-3" />
            <p className="text-muted-foreground font-medium">
              {outcomeFilter !== "all"
                ? "No matches for this filter"
                : "No matches yet — play a game!"}
            </p>
            <Button
              variant="outline"
              className="mt-4 rounded-full gap-2"
              onClick={handleCreateRoom}
            >
              <Swords className="w-4 h-4" />
              Start Playing
            </Button>
          </div>
        ) : (
          <div className="space-y-3">
            {filteredMatches.map((m) => {
              const isAI = (m.opponent_nickname || "").toLowerCase().includes("ai");
              return (
                <div
                  key={m.match_id}
                  className={`rounded-2xl border p-4 transition-all hover:shadow-soft ${
                    m.won
                      ? "border-accent/40 bg-accent/5"
                      : "border-destructive/20 bg-destructive/5"
                  }`}
                >
                  {/* Top Row */}
                  <div className="flex items-center justify-between mb-2">
                    <div className="flex items-center gap-2">
                      {m.won ? (
                        <div className="w-8 h-8 rounded-full bg-accent/20 flex items-center justify-center">
                          <Trophy className="w-4 h-4 text-accent-foreground" />
                        </div>
                      ) : (
                        <div className="w-8 h-8 rounded-full bg-destructive/10 flex items-center justify-center">
                          <XCircle className="w-4 h-4 text-destructive" />
                        </div>
                      )}
                      <div>
                        <span className={`font-semibold text-sm ${m.won ? "text-accent-foreground" : "text-destructive"}`}>
                          {m.won ? "Victory" : "Defeat"}
                        </span>
                        <p className="text-[11px] text-muted-foreground">
                          {m.started_at ? timeAgo(m.started_at) : "—"}
                        </p>
                      </div>
                    </div>
                    <div className="text-right">
                      <p className="text-xl font-bold tabular-nums">
                        {m.my_score} <span className="text-muted-foreground text-sm">–</span> {m.opponent_score}
                      </p>
                    </div>
                  </div>

                  {/* Bottom Row */}
                  <div className="flex items-center justify-between">
                    <div className="flex items-center gap-1.5 text-sm text-muted-foreground">
                      {isAI ? (
                        <Bot className="w-3.5 h-3.5" />
                      ) : (
                        <Target className="w-3.5 h-3.5" />
                      )}
                      <span>vs {m.opponent_nickname}</span>
                    </div>
                    <Button
                      variant="ghost"
                      size="sm"
                      className="rounded-full text-xs h-7 px-3 gap-1"
                      onClick={() => navigate(`/lobby/${m.room_code}`)}
                    >
                      <Swords className="w-3 h-3" />
                      Rematch
                    </Button>
                  </div>
                </div>
              );
            })}
          </div>
        )}

        {/* Pagination */}
        {historyData && historyData.total > PER_PAGE && (
          <div className="flex items-center justify-between pt-2">
            <Button
              variant="outline"
              size="sm"
              className="rounded-full gap-1"
              disabled={page <= 1 || isPageLoading}
              onClick={() => fetchHistory(page - 1)}
            >
              <ChevronLeft className="w-4 h-4" />
              Previous
            </Button>
            <span className="text-xs text-muted-foreground tabular-nums">
              {isPageLoading ? (
                <Loader2 className="w-4 h-4 animate-spin inline" />
              ) : (
                `Page ${page} of ${totalPages}`
              )}
            </span>
            <Button
              variant="outline"
              size="sm"
              className="rounded-full gap-1"
              disabled={page >= totalPages || isPageLoading}
              onClick={() => fetchHistory(page + 1)}
            >
              Next
              <ChevronRight className="w-4 h-4" />
            </Button>
          </div>
        )}
      </div>
    </div>
  );
}
