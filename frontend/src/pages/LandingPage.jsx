import { useState } from "react";
import { useNavigate } from "react-router-dom";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Textarea } from "@/components/ui/textarea";
import { Card, CardContent, CardHeader, CardTitle, CardDescription } from "@/components/ui/card";
import { Label } from "@/components/ui/label";
import { RadioGroup, RadioGroupItem } from "@/components/ui/radio-group";
import {
  BookOpen,
  Users,
  Zap,
  Sparkles,
  Search,
  BarChart3,
  UserRound,
  Loader2,
} from "lucide-react";
import { toast } from "sonner";
import api from "@/lib/api";

const FEATURE_TABS = {
  AI: "ai",
  DICTIONARY: "dictionary",
  LEADERBOARD: "leaderboard",
  STATS: "stats",
};

const featureButtons = [
  { id: FEATURE_TABS.AI, label: "AI Generate", icon: Sparkles },
  { id: FEATURE_TABS.DICTIONARY, label: "Dictionary", icon: Search },
  { id: FEATURE_TABS.LEADERBOARD, label: "Leaderboard", icon: BarChart3 },
  { id: FEATURE_TABS.STATS, label: "My Stats", icon: UserRound },
];

export default function LandingPage() {
  const navigate = useNavigate();
  const [nickname, setNickname] = useState(sessionStorage.getItem("nickname") || "");
  const [joinCode, setJoinCode] = useState("");
  const [mode, setMode] = useState("classic");
  const [targetScore, setTargetScore] = useState(10);
  const [isLoading, setIsLoading] = useState(false);
  const [activeTab, setActiveTab] = useState("create");

  const [featureTab, setFeatureTab] = useState(null);
  const [isFeatureLoading, setIsFeatureLoading] = useState(false);
  const [aiPrompt, setAiPrompt] = useState("");
  const [aiResult, setAiResult] = useState("");
  const [dictionaryQuery, setDictionaryQuery] = useState("");
  const [dictionaryResults, setDictionaryResults] = useState([]);
  const [leaderboardRows, setLeaderboardRows] = useState([]);
  const [playerStats, setPlayerStats] = useState(null);

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
      await api.post(`/rooms/${joinCode.toUpperCase()}/join`);
      toast.success("Joined room!");
      navigate(`/game/${joinCode.toUpperCase()}`);
    } catch (error) {
      toast.error(error.response?.data?.detail || "Failed to join room");
    }
    setIsLoading(false);
  };

  const handleGenerateAi = async () => {
    if (!aiPrompt.trim()) {
      toast.error("Enter a prompt first");
      return;
    }

    setIsFeatureLoading(true);
    try {
      const response = await api.post("/ai/generate", { prompt: aiPrompt.trim() });
      setAiResult(response.data.result || "");
    } catch (error) {
      toast.error(error.response?.data?.detail || "AI generation failed");
    }
    setIsFeatureLoading(false);
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
      const response = await api.get("/dictionary/search", {
        params: { q: dictionaryQuery.trim().toLowerCase() },
      });
      setDictionaryResults(response.data || []);
    } catch (error) {
      toast.error(error.response?.data?.detail || "Dictionary search failed");
    }
    setIsFeatureLoading(false);
  };

  const loadLeaderboard = async () => {
    setIsFeatureLoading(true);
    try {
      const response = await api.get("/leaderboard", { params: { limit: 10 } });
      setLeaderboardRows(response.data || []);
    } catch (error) {
      toast.error("Failed to load leaderboard");
    }
    setIsFeatureLoading(false);
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
  };

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
                    <span className="text-xs text-muted-foreground">No time limit</span>
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
          <CardTitle className="text-base font-semibold tracking-wide">New Features</CardTitle>
          <CardDescription>Quick access to the latest backend capabilities</CardDescription>
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

          {featureTab === FEATURE_TABS.AI && (
            <div className="space-y-3 rounded-2xl border border-border bg-background p-3">
              <Label htmlFor="aiPrompt">Prompt</Label>
              <Textarea
                id="aiPrompt"
                placeholder="Generate a short phrase, hint, or explanation..."
                value={aiPrompt}
                onChange={(e) => setAiPrompt(e.target.value)}
                className="min-h-24 resize-none"
                maxLength={1000}
              />
              <Button className="w-full rounded-full" onClick={handleGenerateAi} disabled={isFeatureLoading}>
                {isFeatureLoading ? <Loader2 className="h-4 w-4 animate-spin" /> : "Generate"}
              </Button>
              {aiResult && (
                <div className="rounded-xl bg-muted p-3 text-sm leading-relaxed text-foreground">
                  {aiResult}
                </div>
              )}
            </div>
          )}

          {featureTab === FEATURE_TABS.DICTIONARY && (
            <div className="space-y-3 rounded-2xl border border-border bg-background p-3">
              <Label htmlFor="dictionaryQuery">Find translation</Label>
              <div className="flex gap-2">
                <Input
                  id="dictionaryQuery"
                  placeholder="tree / дерево"
                  value={dictionaryQuery}
                  onChange={(e) => setDictionaryQuery(e.target.value)}
                />
                <Button onClick={handleDictionarySearch} disabled={isFeatureLoading}>
                  {isFeatureLoading ? <Loader2 className="h-4 w-4 animate-spin" /> : "Search"}
                </Button>
              </div>
              <div className="space-y-2 max-h-40 overflow-auto pr-1">
                {dictionaryResults.length === 0 ? (
                  <p className="text-sm text-muted-foreground">No results yet.</p>
                ) : (
                  dictionaryResults.map((entry, idx) => (
                    <div key={`${entry.ua_word}-${entry.en_word}-${idx}`} className="rounded-xl bg-muted p-2 text-sm">
                      <p className="font-medium">{entry.ua_word} → {entry.en_word}</p>
                      <p className="text-xs text-muted-foreground">{entry.part_of_speech || "n/a"} • {entry.source}</p>
                    </div>
                  ))
                )}
              </div>
            </div>
          )}

          {featureTab === FEATURE_TABS.LEADERBOARD && (
            <div className="space-y-3 rounded-2xl border border-border bg-background p-3">
              <Button variant="outline" className="w-full rounded-full" onClick={loadLeaderboard} disabled={isFeatureLoading}>
                {isFeatureLoading ? <Loader2 className="h-4 w-4 animate-spin" /> : "Refresh Leaderboard"}
              </Button>
              <div className="space-y-2 max-h-40 overflow-auto pr-1">
                {leaderboardRows.length === 0 ? (
                  <p className="text-sm text-muted-foreground">Leaderboard is empty.</p>
                ) : (
                  leaderboardRows.map((row, index) => (
                    <div key={row.player_id} className="flex items-center justify-between rounded-xl bg-muted px-3 py-2 text-sm">
                      <p className="font-medium">#{index + 1} {row.nickname}</p>
                      <p className="text-muted-foreground">ELO {row.elo}</p>
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
