import { useState, useEffect } from "react";
import { useNavigate, useSearchParams } from "react-router-dom";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Card, CardContent, CardHeader, CardTitle, CardDescription } from "@/components/ui/card";
import { Label } from "@/components/ui/label";
import { RadioGroup, RadioGroupItem } from "@/components/ui/radio-group";
import {
  BookOpen,
  Users,
  Zap,
  Search,
  BarChart3,
  UserRound,
  Loader2,
  History,
  ChevronLeft,
  ChevronRight,
  Trophy,
  XCircle,
} from "lucide-react";
import { toast } from "sonner";
import api from "@/lib/api";
import CefrBadge, { getCefrColor } from "@/components/CefrBadge";

const FEATURE_TABS = {
  DICTIONARY: "dictionary",
  LEADERBOARD: "leaderboard",
  STATS: "stats",
  HISTORY: "history",
};

const featureButtons = [
  { id: FEATURE_TABS.DICTIONARY, label: "Dictionary", icon: Search },
  { id: FEATURE_TABS.LEADERBOARD, label: "Leaderboard", icon: BarChart3 },
  { id: FEATURE_TABS.STATS, label: "My Stats", icon: UserRound },
  { id: FEATURE_TABS.HISTORY, label: "History", icon: History },
];

export default function LandingPage() {
  const navigate = useNavigate();
  const [searchParams] = useSearchParams();
  const [nickname, setNickname] = useState(sessionStorage.getItem("nickname") || "");
  const [joinCode, setJoinCode] = useState("");
  const [mode, setMode] = useState("classic");
  const [targetScore, setTargetScore] = useState(10);
  const [wordLevel, setWordLevel] = useState("B1");
  const [isLoading, setIsLoading] = useState(false);
  const [activeTab, setActiveTab] = useState("create");

  const [featureTab, setFeatureTab] = useState(null);
  const [isFeatureLoading, setIsFeatureLoading] = useState(false);
  const [dictionaryQuery, setDictionaryQuery] = useState("");
  const [dictionaryResults, setDictionaryResults] = useState([]);
  const [dictionaryLevel, setDictionaryLevel] = useState("");
  const [leaderboardRows, setLeaderboardRows] = useState([]);
  const [leaderboardPeriod, setLeaderboardPeriod] = useState("all");
  const [playerStats, setPlayerStats] = useState(null);
  const [historyData, setHistoryData] = useState(null);
  const [historyPage, setHistoryPage] = useState(1);

  // Handle Google OAuth callback params
  useEffect(() => {
    const token = searchParams.get("access_token");
    const userId = searchParams.get("user_id");
    const nick = searchParams.get("nickname");
    const authError = searchParams.get("auth_error");

    if (authError) {
      toast.error(`Google sign-in failed: ${authError}`);
      return;
    }

    if (token && userId && nick) {
      sessionStorage.setItem("accessToken", token);
      sessionStorage.setItem("userId", userId);
      sessionStorage.setItem("nickname", nick);
      setNickname(nick);
      toast.success(`Signed in as ${nick}`);
      // Clean URL
      window.history.replaceState({}, document.title, "/");
    }
  }, [searchParams]);

  const handleAuth = async () => {
    if (!nickname.trim() || nickname.length < 2) {
      toast.error("Please enter a nickname (2+ characters)");
      return null;
    }

    try {
      const response = await api.post("/auth/guest", {
        nickname: nickname.trim(),
      });
      sessionStorage.setItem("userId", response.data.user_id);
      sessionStorage.setItem("nickname", response.data.nickname);
      sessionStorage.setItem("accessToken", response.data.access_token);
      return response.data.user_id;
    } catch (error) {
      toast.error("Failed to create user");
      return null;
    }
  };

  const ensureAuth = async () => {
    const savedToken = sessionStorage.getItem("accessToken");
    const savedUserId = sessionStorage.getItem("userId");
    if (savedToken && savedUserId) {
      return savedUserId;
    }
    return handleAuth();
  };

  const handleCreateRoom = async () => {
    setIsLoading(true);
    const userId = await handleAuth();
    if (!userId) {
      setIsLoading(false);
      return;
    }

    try {
      const response = await api.post("/rooms", {
        mode,
        target_score: targetScore,
        word_level: wordLevel,
      });
      toast.success("Room created!");
      navigate(`/lobby/${response.data.code}`);
    } catch (error) {
      toast.error("Failed to create room");
    }
    setIsLoading(false);
  };

  const handleJoinRoom = async () => {
    if (!joinCode.trim()) {
      toast.error("Please enter a room code");
      return;
    }

    setIsLoading(true);
    const userId = await handleAuth();
    if (!userId) {
      setIsLoading(false);
      return;
    }

    try {
      const response = await api.post(`/rooms/${joinCode.toUpperCase()}/join`);
      toast.success("Joined room!");
      const status = response.data.status;
      if (status === "playing" || status === "finished") {
        navigate(`/game/${joinCode.toUpperCase()}`);
      } else {
        navigate(`/lobby/${joinCode.toUpperCase()}`);
      }
    } catch (error) {
      toast.error(error.response?.data?.detail || "Failed to join room");
    }
    setIsLoading(false);
  };

  const handleGoogleSignIn = () => {
    const backendUrl = api.defaults.baseURL.replace("/api", "");
    window.location.href = `${backendUrl}/api/auth/google`;
  };

  const handleDictionarySearch = async () => {
    if (!dictionaryQuery.trim()) {
      toast.error("Enter a word to search");
      return;
    }

    const authed = await ensureAuth();
    if (!authed) {
      return;
    }

    setIsFeatureLoading(true);
    try {
      const params = { q: dictionaryQuery.trim().toLowerCase() };
      if (dictionaryLevel) {
        params.level = dictionaryLevel;
      }
      const response = await api.get("/dictionary/search", { params });
      setDictionaryResults(response.data || []);
    } catch (error) {
      toast.error(error.response?.data?.detail || "Dictionary search failed");
    }
    setIsFeatureLoading(false);
  };

  const loadLeaderboard = async (period) => {
    setIsFeatureLoading(true);
    try {
      const response = await api.get("/leaderboard", { params: { limit: 10, period: period || leaderboardPeriod } });
      setLeaderboardRows(response.data || []);
    } catch (error) {
      toast.error("Failed to load leaderboard");
    }
    setIsFeatureLoading(false);
  };

  const handlePeriodChange = async (p) => {
    setLeaderboardPeriod(p);
    await loadLeaderboard(p);
  };

  const loadMyStats = async () => {
    const userId = await ensureAuth();
    if (!userId) {
      return;
    }

    setIsFeatureLoading(true);
    try {
      const response = await api.get(`/players/${userId}/stats`);
      setPlayerStats(response.data);
    } catch (error) {
      toast.error("Failed to load player stats");
    }
    setIsFeatureLoading(false);
  };

  const loadHistory = async (page = 1) => {
    const userId = await ensureAuth();
    if (!userId) return;

    setIsFeatureLoading(true);
    try {
      const response = await api.get(`/players/${userId}/history`, { params: { page, per_page: 5 } });
      setHistoryData(response.data);
      setHistoryPage(page);
    } catch (error) {
      toast.error("Failed to load match history");
    }
    setIsFeatureLoading(false);
  };

  const handleFeatureToggle = async (tabId) => {
    if (featureTab === tabId) {
      setFeatureTab(null);
      return;
    }

    setFeatureTab(tabId);

    if (tabId === FEATURE_TABS.LEADERBOARD && leaderboardRows.length === 0) {
      await loadLeaderboard();
    }

    if (tabId === FEATURE_TABS.STATS && !playerStats) {
      await loadMyStats();
    }

    if (tabId === FEATURE_TABS.HISTORY && !historyData) {
      await loadHistory(1);
    }
  };

  const isSignedIn = !!sessionStorage.getItem("accessToken");

  return (
    <div className="min-h-screen bg-background flex flex-col items-center justify-center p-4">
      <div className="text-center mb-8 animate-fade-in-up">
        <img
          src="/logo.svg"
          alt="DuoEng logo"
          className="mx-auto mb-4 h-20 w-20 rounded-full shadow-soft"
        />
        <h1 className="font-heading text-4xl sm:text-5xl font-bold text-foreground mb-2">DuoVocab Duel</h1>
        <p className="text-muted-foreground text-base sm:text-lg max-w-sm mx-auto">
          Challenge your friends to a Ukrainian-English vocabulary battle!
        </p>
      </div>

      <div className="flex gap-4 mb-8 text-sm text-muted-foreground">
        <div className="flex items-center gap-1">
          <Users className="w-4 h-4" />
          <span>2 Players</span>
        </div>
        <div className="flex items-center gap-1">
          <BookOpen className="w-4 h-4" />
          <span>5000+ Words</span>
        </div>
        <div className="flex items-center gap-1">
          <Zap className="w-4 h-4" />
          <span>Instant Play</span>
        </div>
      </div>

      <Card className="w-full max-w-md rounded-3xl shadow-soft border-0" data-testid="main-card">
        <CardHeader className="text-center pb-2">
          <CardTitle className="font-heading text-2xl">Enter the Arena</CardTitle>
          <CardDescription>Create a new game or join an existing one</CardDescription>
        </CardHeader>
        <CardContent className="space-y-6">
          {/* Google Sign-In */}
          {!isSignedIn && (
            <Button
              variant="outline"
              className="w-full rounded-full h-12 text-base font-medium flex items-center gap-3"
              onClick={handleGoogleSignIn}
            >
              <svg viewBox="0 0 24 24" className="w-5 h-5" xmlns="http://www.w3.org/2000/svg">
                <path d="M22.56 12.25c0-.78-.07-1.53-.2-2.25H12v4.26h5.92a5.06 5.06 0 01-2.2 3.32v2.77h3.57c2.08-1.92 3.28-4.74 3.28-8.1z" fill="#4285F4"/>
                <path d="M12 23c2.97 0 5.46-.98 7.28-2.66l-3.57-2.77c-.98.66-2.23 1.06-3.71 1.06-2.86 0-5.29-1.93-6.16-4.53H2.18v2.84C3.99 20.53 7.7 23 12 23z" fill="#34A853"/>
                <path d="M5.84 14.09c-.22-.66-.35-1.36-.35-2.09s.13-1.43.35-2.09V7.07H2.18C1.43 8.55 1 10.22 1 12s.43 3.45 1.18 4.93l2.85-2.22.81-.62z" fill="#FBBC05"/>
                <path d="M12 5.38c1.62 0 3.06.56 4.21 1.64l3.15-3.15C17.45 2.09 14.97 1 12 1 7.7 1 3.99 3.47 2.18 7.07l3.66 2.84c.87-2.6 3.3-4.53 6.16-4.53z" fill="#EA4335"/>
              </svg>
              Sign in with Google
            </Button>
          )}

          {isSignedIn && (
            <div className="text-center text-sm text-muted-foreground">
              Signed in as <span className="font-semibold text-foreground">{sessionStorage.getItem("nickname")}</span>
            </div>
          )}

          <div className="space-y-2">
            <Label htmlFor="nickname" className="text-sm font-medium">Your Nickname</Label>
            <Input
              id="nickname"
              data-testid="nickname-input"
              placeholder="Enter your name..."
              value={nickname}
              onChange={(e) => setNickname(e.target.value)}
              className="rounded-full h-12 px-5"
              maxLength={20}
            />
          </div>

          <div className="flex gap-2 p-1 bg-muted rounded-full">
            <button
              data-testid="create-tab"
              className={`flex-1 py-2 px-4 rounded-full text-sm font-medium transition-all ${
                activeTab === "create" ? "bg-white shadow-sm text-black" : "text-muted-foreground hover:text-foreground"
              }`}
              onClick={() => setActiveTab("create")}
            >
              Create Room
            </button>
            <button
              data-testid="join-tab"
              className={`flex-1 py-2 px-4 rounded-full text-sm font-medium transition-all ${
                activeTab === "join" ? "bg-white shadow-sm text-black" : "text-muted-foreground hover:text-foreground"
              }`}
              onClick={() => setActiveTab("join")}
            >
              Join Room
            </button>
          </div>

          {activeTab === "create" && (
            <div className="space-y-4 animate-fade-in-up">
              <div className="space-y-3">
                <Label className="text-sm font-medium">Game Mode</Label>
                <RadioGroup value={mode} onValueChange={setMode} className="grid grid-cols-2 gap-3">
                  <Label
                    htmlFor="classic"
                    data-testid="mode-classic"
                    className={`flex flex-col items-center p-4 rounded-2xl border-2 cursor-pointer transition-all ${
                      mode === "classic" ? "border-primary bg-primary/5" : "border-border hover:border-primary/50"
                    }`}
                  >
                    <RadioGroupItem value="classic" id="classic" className="sr-only" />
                    <BookOpen className="w-6 h-6 mb-2 text-primary-foreground" />
                    <span className="font-medium text-sm">Classic</span>
                    <span className="text-xs text-muted-foreground">Relaxed pace</span>
                  </Label>
                  <Label
                    htmlFor="challenge"
                    data-testid="mode-challenge"
                    className={`flex flex-col items-center p-4 rounded-2xl border-2 cursor-pointer transition-all ${
                      mode === "challenge" ? "border-primary bg-primary/5" : "border-border hover:border-primary/50"
                    }`}
                  >
                    <RadioGroupItem value="challenge" id="challenge" className="sr-only" />
                    <Zap className="w-6 h-6 mb-2 text-secondary-foreground" />
                    <span className="font-medium text-sm">Challenge</span>
                    <span className="text-xs text-muted-foreground">30s per turn</span>
                  </Label>
                </RadioGroup>
              </div>

              <div className="space-y-2">
                <Label className="text-sm font-medium">Target Score</Label>
                <div className="flex gap-2">
                  {[5, 10, 15, 20].map((score) => (
                    <button
                      key={score}
                      data-testid={`score-${score}`}
                      className={`flex-1 py-2 rounded-full text-sm font-medium transition-all ${
                        targetScore === score
                          ? "bg-primary text-primary-foreground"
                          : "bg-muted text-muted-foreground hover:bg-muted/80"
                      }`}
                      onClick={() => setTargetScore(score)}
                    >
                      {score}
                    </button>
                  ))}
                </div>
              </div>

              {/* Word Difficulty (CEFR Level) */}
              <div className="space-y-3">
                <Label className="text-sm font-medium">Word Difficulty</Label>
                <div className="grid grid-cols-3 gap-2">
                  {[
                    { level: "A1", label: "Beginner", desc: "Basic everyday words", color: "border-green-400 bg-green-50 dark:bg-green-950/30" },
                    { level: "A2", label: "Elementary", desc: "Simple phrases & vocab", color: "border-green-500 bg-green-50 dark:bg-green-950/30" },
                    { level: "B1", label: "Intermediate", desc: "Common topics & ideas", color: "border-yellow-400 bg-yellow-50 dark:bg-yellow-950/30" },
                    { level: "B2", label: "Upper Inter.", desc: "Abstract & detailed", color: "border-orange-400 bg-orange-50 dark:bg-orange-950/30" },
                    { level: "C1", label: "Advanced", desc: "Complex & nuanced", color: "border-red-400 bg-red-50 dark:bg-red-950/30" },
                    { level: "C2", label: "Mastery", desc: "Rare & specialized", color: "border-red-600 bg-red-50 dark:bg-red-950/30" },
                  ].map((item) => (
                    <button
                      key={item.level}
                      data-testid={`level-${item.level}`}
                      className={`flex flex-col items-center p-3 rounded-2xl border-2 cursor-pointer transition-all text-center ${
                        wordLevel === item.level
                          ? `${item.color} ring-2 ring-offset-1 ring-primary/40`
                          : "border-border hover:border-primary/40 bg-background"
                      }`}
                      onClick={() => setWordLevel(item.level)}
                    >
                      <span className="font-heading text-lg font-bold">{item.level}</span>
                      <span className="text-xs font-medium mt-0.5">{item.label}</span>
                      <span className="text-[10px] text-muted-foreground mt-0.5 leading-tight">{item.desc}</span>
                    </button>
                  ))}
                </div>
              </div>

              <Button
                data-testid="create-room-btn"
                className="w-full rounded-full h-12 text-base font-bold bg-primary hover:bg-primary/90"
                onClick={handleCreateRoom}
                disabled={isLoading}
              >
                {isLoading ? "Creating..." : "Create Room"}
              </Button>
            </div>
          )}

          {activeTab === "join" && (
            <div className="space-y-4 animate-fade-in-up">
              <div className="space-y-2">
                <Label htmlFor="roomCode" className="text-sm font-medium">Room Code</Label>
                <Input
                  id="roomCode"
                  data-testid="room-code-input"
                  placeholder="Enter 8-char code..."
                  value={joinCode}
                  onChange={(e) => setJoinCode(e.target.value.toUpperCase())}
                  className="rounded-full h-12 px-5 text-center text-lg tracking-widest uppercase"
                  maxLength={8}
                />
              </div>

              <Button
                data-testid="join-room-btn"
                className="w-full rounded-full h-12 text-base font-bold bg-secondary hover:bg-secondary/90 text-secondary-foreground"
                onClick={handleJoinRoom}
                disabled={isLoading}
              >
                {isLoading ? "Joining..." : "Join Room"}
              </Button>
            </div>
          )}
        </CardContent>
      </Card>

      <Card className="w-full max-w-md mt-4 rounded-3xl border border-border/70 bg-card/90 backdrop-blur" data-testid="feature-tools">
        <CardHeader className="pb-2">
          <CardTitle className="text-base font-semibold tracking-wide">Features</CardTitle>
          <CardDescription>Dictionary, leaderboard, stats &amp; history</CardDescription>
        </CardHeader>
        <CardContent className="space-y-3">
          <div className="grid grid-cols-2 gap-2">
            {featureButtons.map((item) => {
              const Icon = item.icon;
              const isActive = featureTab === item.id;
              return (
                <button
                  key={item.id}
                  type="button"
                  className={`flex items-center gap-2 rounded-xl border px-3 py-2 text-sm font-medium transition-all ${
                    isActive
                      ? "border-primary/60 bg-primary/10 text-foreground"
                      : "border-border bg-background hover:border-primary/30 hover:bg-primary/5"
                  }`}
                  onClick={() => {
                    void handleFeatureToggle(item.id);
                  }}
                >
                  <Icon className="h-4 w-4" />
                  <span>{item.label}</span>
                </button>
              );
            })}
          </div>

          {featureTab === FEATURE_TABS.DICTIONARY && (
            <div className="space-y-3 rounded-2xl border border-border bg-background p-3">
              <Label htmlFor="dictionaryQuery">Find translation</Label>
              <div className="flex gap-2">
                <Input
                  id="dictionaryQuery"
                  placeholder="tree / дерево"
                  value={dictionaryQuery}
                  onChange={(e) => setDictionaryQuery(e.target.value)}
                  onKeyDown={(e) => e.key === "Enter" && handleDictionarySearch()}
                />
                <Button onClick={handleDictionarySearch} disabled={isFeatureLoading}>
                  {isFeatureLoading ? <Loader2 className="h-4 w-4 animate-spin" /> : "Search"}
                </Button>
              </div>

              {/* CEFR Level Filter */}
              <div className="flex flex-wrap gap-1">
                <button
                  type="button"
                  className={`px-2.5 py-1 rounded-full text-xs font-medium border transition-all ${
                    dictionaryLevel === ""
                      ? "bg-foreground text-background border-foreground"
                      : "bg-muted text-muted-foreground border-border hover:border-primary/40"
                  }`}
                  onClick={() => setDictionaryLevel("")}
                >
                  All
                </button>
                {["A1", "A2", "B1", "B2", "C1", "C2"].map((lvl) => (
                  <button
                    key={lvl}
                    type="button"
                    className={`px-2.5 py-1 rounded-full text-xs font-medium border transition-all ${
                      dictionaryLevel === lvl
                        ? `${getCefrColor(lvl)} ring-1 ring-primary/30`
                        : "bg-muted text-muted-foreground border-border hover:border-primary/40"
                    }`}
                    onClick={() => setDictionaryLevel(lvl)}
                  >
                    {lvl}
                  </button>
                ))}
              </div>

              <div className="space-y-2 max-h-40 overflow-auto pr-1">
                {dictionaryResults.length === 0 ? (
                  <p className="text-sm text-muted-foreground">No results yet.</p>
                ) : (
                  dictionaryResults.map((entry, idx) => (
                    <div key={`${entry.ua_word}-${entry.en_word}-${idx}`} className="rounded-xl bg-muted p-2 text-sm">
                      <div className="flex items-center justify-between">
                        <p className="font-medium">{entry.ua_word} → {entry.en_word}</p>
                        {entry.level && <CefrBadge level={entry.level} short className="ml-2 text-[10px] px-1.5 py-0" />}
                      </div>
                      <p className="text-xs text-muted-foreground">{entry.part_of_speech || "n/a"} • {entry.source}</p>
                    </div>
                  ))
                )}
              </div>
            </div>
          )}

          {featureTab === FEATURE_TABS.LEADERBOARD && (
            <div className="space-y-3 rounded-2xl border border-border bg-background p-3">
              {/* Period tabs */}
              <div className="flex gap-1 p-1 bg-muted rounded-full">
                {[
                  { value: "today", label: "Today" },
                  { value: "week", label: "This Week" },
                  { value: "all", label: "All Time" },
                ].map((p) => (
                  <button
                    key={p.value}
                    className={`flex-1 py-1.5 rounded-full text-xs font-medium transition-all ${
                      leaderboardPeriod === p.value
                        ? "bg-white shadow-sm text-black"
                        : "text-muted-foreground hover:text-foreground"
                    }`}
                    onClick={() => handlePeriodChange(p.value)}
                    disabled={isFeatureLoading}
                  >
                    {p.label}
                  </button>
                ))}
              </div>
              <Button variant="outline" className="w-full rounded-full" onClick={() => loadLeaderboard()} disabled={isFeatureLoading}>
                {isFeatureLoading ? <Loader2 className="h-4 w-4 animate-spin" /> : "Refresh"}
              </Button>
              <div className="space-y-2 max-h-48 overflow-auto pr-1">
                {leaderboardRows.length === 0 ? (
                  <p className="text-sm text-muted-foreground">Leaderboard is empty.</p>
                ) : (
                  leaderboardRows.map((row, index) => (
                    <div key={row.player_id} className="flex items-center justify-between rounded-xl bg-muted px-3 py-2 text-sm">
                      <div className="flex items-center gap-2">
                        {index < 3 ? (
                          <Trophy className={`w-4 h-4 ${index === 0 ? "text-yellow-500" : index === 1 ? "text-gray-400" : "text-amber-700"}`} />
                        ) : (
                          <span className="w-4 text-center text-muted-foreground">#{index + 1}</span>
                        )}
                        <p className="font-medium">{row.nickname}</p>
                      </div>
                      <div className="flex items-center gap-3">
                        <span className="text-xs text-muted-foreground">{row.wins}W/{row.losses}L</span>
                        <span className="font-semibold">ELO {row.elo}</span>
                      </div>
                    </div>
                  ))
                )}
              </div>
            </div>
          )}

          {featureTab === FEATURE_TABS.STATS && (
            <div className="space-y-3 rounded-2xl border border-border bg-background p-3">
              <Button variant="outline" className="w-full rounded-full" onClick={loadMyStats} disabled={isFeatureLoading}>
                {isFeatureLoading ? <Loader2 className="h-4 w-4 animate-spin" /> : "Load My Stats"}
              </Button>
              {playerStats ? (
                <div className="grid grid-cols-2 gap-2 text-sm">
                  <div className="rounded-xl bg-muted px-3 py-2">
                    <p className="text-xs text-muted-foreground">ELO</p>
                    <p className="font-semibold">{playerStats.elo}</p>
                  </div>
                  <div className="rounded-xl bg-muted px-3 py-2">
                    <p className="text-xs text-muted-foreground">Win rate</p>
                    <p className="font-semibold">{playerStats.win_rate}%</p>
                  </div>
                  <div className="rounded-xl bg-muted px-3 py-2">
                    <p className="text-xs text-muted-foreground">Games</p>
                    <p className="font-semibold">{playerStats.total_games}</p>
                  </div>
                  <div className="rounded-xl bg-muted px-3 py-2">
                    <p className="text-xs text-muted-foreground">Avg response</p>
                    <p className="font-semibold">{playerStats.avg_response_time}s</p>
                  </div>
                </div>
              ) : (
                <p className="text-sm text-muted-foreground">No stats loaded yet.</p>
              )}
            </div>
          )}

          {featureTab === FEATURE_TABS.HISTORY && (
            <div className="space-y-3 rounded-2xl border border-border bg-background p-3">
              <Button variant="outline" className="w-full rounded-full" onClick={() => loadHistory(1)} disabled={isFeatureLoading}>
                {isFeatureLoading ? <Loader2 className="h-4 w-4 animate-spin" /> : "Refresh History"}
              </Button>
              {historyData && historyData.matches.length > 0 ? (
                <>
                  <div className="space-y-2 max-h-64 overflow-auto pr-1">
                    {historyData.matches.map((m) => (
                      <div
                        key={m.match_id}
                        className={`rounded-xl p-3 text-sm border ${
                          m.won ? "bg-accent/20 border-accent/40" : "bg-destructive/10 border-destructive/20"
                        }`}
                      >
                        <div className="flex items-center justify-between mb-1">
                          <div className="flex items-center gap-2">
                            {m.won ? (
                              <Trophy className="w-4 h-4 text-accent-foreground" />
                            ) : (
                              <XCircle className="w-4 h-4 text-destructive-foreground" />
                            )}
                            <span className="font-medium">{m.won ? "Victory" : "Defeat"}</span>
                          </div>
                          <span className="text-xs text-muted-foreground">
                            {m.started_at ? new Date(m.started_at).toLocaleDateString() : "—"}
                          </span>
                        </div>
                        <div className="flex items-center justify-between">
                          <span className="text-muted-foreground">vs {m.opponent_nickname}</span>
                          <span className="font-semibold">{m.my_score} – {m.opponent_score}</span>
                        </div>
                        <Button
                          variant="ghost"
                          size="sm"
                          className="w-full mt-2 rounded-full text-xs h-7"
                          onClick={() => navigate(`/lobby/${m.room_code}`)}
                        >
                          Play again in {m.room_code}
                        </Button>
                      </div>
                    ))}
                  </div>
                  {/* Pagination */}
                  <div className="flex items-center justify-between">
                    <Button
                      variant="outline"
                      size="sm"
                      className="rounded-full"
                      disabled={historyPage <= 1 || isFeatureLoading}
                      onClick={() => loadHistory(historyPage - 1)}
                    >
                      <ChevronLeft className="w-4 h-4" />
                    </Button>
                    <span className="text-xs text-muted-foreground">
                      Page {historyPage} of {Math.ceil((historyData.total || 1) / (historyData.per_page || 5))}
                    </span>
                    <Button
                      variant="outline"
                      size="sm"
                      className="rounded-full"
                      disabled={historyPage >= Math.ceil((historyData.total || 1) / (historyData.per_page || 5)) || isFeatureLoading}
                      onClick={() => loadHistory(historyPage + 1)}
                    >
                      <ChevronRight className="w-4 h-4" />
                    </Button>
                  </div>
                </>
              ) : (
                <p className="text-sm text-muted-foreground">No match history yet. Play a game!</p>
              )}
            </div>
          )}
        </CardContent>
      </Card>

      <Button
        variant="outline"
        className="w-full max-w-md mt-3 rounded-full"
        onClick={() => navigate("/word-levels")}
      >
        Open Word Levels
      </Button>

      <p className="mt-8 text-sm text-muted-foreground">Learn Ukrainian vocabulary with friends</p>
    </div>
  );
}
