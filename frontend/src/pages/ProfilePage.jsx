import { useState, useEffect } from "react";
import { useNavigate } from "react-router-dom";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
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
  Pencil,
  Check,
  X,
  Star,
  Trash2,
  XCircle,
  Plus,
} from "lucide-react";
import { toast } from "sonner";
import api from "@/lib/api";
import CefrBadge from "@/components/CefrBadge";

export default function ProfilePage() {
  const navigate = useNavigate();
  const [stats, setStats] = useState(null);
  const [isLoading, setIsLoading] = useState(true);

  // Nickname editing
  const [isEditingNickname, setIsEditingNickname] = useState(false);
  const [nicknameInput, setNicknameInput] = useState("");
  const [isNicknameSaving, setIsNicknameSaving] = useState(false);
  const [currentNickname, setCurrentNickname] = useState(
    sessionStorage.getItem("nickname") || "Player"
  );

  // Favourites
  const [favourites, setFavourites] = useState([]);
  const [isFavouritesLoading, setIsFavouritesLoading] = useState(false);
  const [showFavourites, setShowFavourites] = useState(false);

  const accessToken = sessionStorage.getItem("accessToken");
  const userId = sessionStorage.getItem("userId");
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

  // ── Nickname editing ──
  const handleStartEditNickname = () => {
    setNicknameInput(currentNickname);
    setIsEditingNickname(true);
  };

  const handleCancelEditNickname = () => {
    setIsEditingNickname(false);
    setNicknameInput("");
  };

  const handleSaveNickname = async () => {
    const trimmed = nicknameInput.trim();
    if (trimmed.length < 2) {
      toast.error("Nickname must be at least 2 characters");
      return;
    }
    if (trimmed.length > 20) {
      toast.error("Nickname must be at most 20 characters");
      return;
    }

    setIsNicknameSaving(true);
    try {
      const response = await api.patch("/players/me/nickname", {
        nickname: trimmed,
      });
      const { nickname: newNickname, access_token } = response.data;
      // Update sessionStorage
      sessionStorage.setItem("nickname", newNickname);
      sessionStorage.setItem("accessToken", access_token);
      setCurrentNickname(newNickname);
      setIsEditingNickname(false);
      toast.success("Nickname updated!");
    } catch (error) {
      const detail = error.response?.data?.detail || "Failed to change nickname";
      toast.error(detail);
    }
    setIsNicknameSaving(false);
  };

  // ── Favourites ──
  const loadFavourites = async () => {
    setIsFavouritesLoading(true);
    try {
      const response = await api.get("/players/me/favourites");
      setFavourites(response.data || []);
    } catch (error) {
      toast.error("Failed to load favourites");
    }
    setIsFavouritesLoading(false);
  };

  const handleToggleFavourites = async () => {
    if (showFavourites) {
      setShowFavourites(false);
      return;
    }
    setShowFavourites(true);
    if (favourites.length === 0) {
      await loadFavourites();
    }
  };

  const handleRemoveFavourite = async (wordId) => {
    try {
      await api.delete(`/players/me/favourites/${wordId}`);
      setFavourites((prev) => prev.filter((f) => f.word_id !== wordId));
      toast.success("Removed from favourites");
    } catch (error) {
      toast.error("Failed to remove favourite");
    }
  };

  if (!accessToken || !userId) return null;

  const avatarLetter = (currentNickname || "P")[0].toUpperCase();

  return (
    <div className="min-h-screen bg-background flex flex-col items-center p-4 pt-8">
      <div className="w-full max-w-md lg:max-w-2xl space-y-6 animate-fade-in-up">

        {/* ─── Avatar + Identity ─── */}
        <div className="text-center">
          <div className="w-24 h-24 mx-auto rounded-full bg-primary flex items-center justify-center text-primary-foreground text-4xl font-bold shadow-lg mb-4">
            {avatarLetter}
          </div>

          {/* Nickname with inline edit */}
          {isEditingNickname ? (
            <div className="flex items-center justify-center gap-2 mb-1">
              <div className="relative">
                <Input
                  autoFocus
                  value={nicknameInput}
                  onChange={(e) => setNicknameInput(e.target.value)}
                  onKeyDown={(e) => {
                    if (e.key === "Enter") handleSaveNickname();
                    if (e.key === "Escape") handleCancelEditNickname();
                  }}
                  className="rounded-full h-10 px-4 text-center text-lg font-bold w-52"
                  maxLength={20}
                  disabled={isNicknameSaving}
                />
                <span className={`absolute right-3 top-1/2 -translate-y-1/2 text-xs ${
                  nicknameInput.trim().length < 2 ? "text-destructive" : "text-muted-foreground"
                }`}>
                  {nicknameInput.trim().length}/20
                </span>
              </div>
              <Button
                size="icon"
                variant="ghost"
                className="rounded-full h-10 w-10 text-accent-foreground hover:bg-accent/20"
                onClick={handleSaveNickname}
                disabled={isNicknameSaving || nicknameInput.trim().length < 2}
              >
                {isNicknameSaving ? (
                  <Loader2 className="w-4 h-4 animate-spin" />
                ) : (
                  <Check className="w-4 h-4" />
                )}
              </Button>
              <Button
                size="icon"
                variant="ghost"
                className="rounded-full h-10 w-10 text-destructive hover:bg-destructive/10"
                onClick={handleCancelEditNickname}
                disabled={isNicknameSaving}
              >
                <X className="w-4 h-4" />
              </Button>
            </div>
          ) : (
            <div className="flex items-center justify-center gap-2 mb-1">
              <h1 className="font-heading text-3xl font-bold text-foreground">{currentNickname}</h1>
              <Button
                size="icon"
                variant="ghost"
                className="rounded-full h-8 w-8 text-muted-foreground hover:text-foreground"
                onClick={handleStartEditNickname}
                title="Edit nickname"
              >
                <Pencil className="w-4 h-4" />
              </Button>
            </div>
          )}

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
          <div className="grid grid-cols-3 lg:grid-cols-6 gap-3">
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

          <div className="grid grid-cols-2 gap-3">
            <Button
              variant="outline"
              className="rounded-2xl h-12 text-sm font-medium flex items-center gap-2"
              onClick={() => navigate("/my-words")}
            >
              <Plus className="w-4 h-4" />
              My Words
            </Button>
            <Button
              variant="outline"
              className="rounded-2xl h-12 text-sm font-medium flex items-center gap-2"
              onClick={() => navigate("/wrong-words")}
            >
              <XCircle className="w-4 h-4" />
              Wrong Words
            </Button>
          </div>

          <Button
            variant="outline"
            className="w-full rounded-2xl h-12 text-sm font-medium flex items-center justify-center gap-2"
            onClick={handleToggleFavourites}
          >
            <Star className="w-4 h-4" />
            My Favourite Words
          </Button>
        </div>

        {/* ─── Favourites Section ─── */}
        {showFavourites && (
          <Card className="rounded-2xl border-0 shadow-soft animate-fade-in-up">
            <CardContent className="p-4">
              <div className="flex items-center justify-between mb-3">
                <h3 className="font-heading text-lg font-bold">⭐ My Words</h3>
                <Button
                  variant="ghost"
                  size="sm"
                  className="rounded-full text-xs"
                  onClick={loadFavourites}
                  disabled={isFavouritesLoading}
                >
                  {isFavouritesLoading ? <Loader2 className="w-3 h-3 animate-spin" /> : "Refresh"}
                </Button>
              </div>

              {isFavouritesLoading ? (
                <div className="flex justify-center py-4">
                  <Loader2 className="w-6 h-6 animate-spin text-primary" />
                </div>
              ) : favourites.length === 0 ? (
                <p className="text-sm text-muted-foreground text-center py-4">
                  No favourite words yet. Star words in the dictionary to save them!
                </p>
              ) : (
                <div className="space-y-2 max-h-60 overflow-auto pr-1">
                  {favourites.map((fav) => (
                    <div
                      key={fav.word_id}
                      className="flex flex-col rounded-xl bg-muted px-3 py-2 text-sm gap-1"
                    >
                      <div className="flex items-center justify-between">
                        <div className="flex items-center gap-2 min-w-0">
                          <Star className="w-4 h-4 text-yellow-500 fill-yellow-500 flex-shrink-0" />
                          <span className="font-medium truncate">{fav.ua}</span>
                          <span className="text-muted-foreground">→</span>
                          <span className="truncate">{fav.en}</span>
                          <CefrBadge level={fav.level} short className="ml-1 text-[10px] px-1.5 py-0 flex-shrink-0" />
                        </div>
                        <Button
                          size="icon"
                          variant="ghost"
                          className="rounded-full h-7 w-7 text-destructive hover:bg-destructive/10 flex-shrink-0"
                          onClick={() => handleRemoveFavourite(fav.word_id)}
                          title="Remove from favourites"
                        >
                          <Trash2 className="w-3.5 h-3.5" />
                        </Button>
                      </div>
                      {fav.definition && (
                        <p className="text-xs text-muted-foreground pl-6 italic">{fav.definition}</p>
                      )}
                    </div>
                  ))}
                </div>
              )}
            </CardContent>
          </Card>
        )}

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
