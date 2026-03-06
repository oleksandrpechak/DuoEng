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
  Gamepad2,
  Star,
  Bot,
  Swords,
  Trophy,
} from "lucide-react";
import { toast } from "sonner";
import api from "@/lib/api";
import { getCefrColor } from "@/components/CefrBadge";
import useCountUp from "@/hooks/useCountUp";

export default function LandingPage() {
  const navigate = useNavigate();
  const [searchParams] = useSearchParams();
  const [nickname, setNickname] = useState(localStorage.getItem("nickname") || "");
  const [joinCode, setJoinCode] = useState("");
  const [mode, setMode] = useState("classic");
  const [targetScore, setTargetScore] = useState(10);
  const [wordLevel, setWordLevel] = useState("B1");
  const [useFavourites, setUseFavourites] = useState(false);
  const [useCustomWords, setUseCustomWords] = useState(false);
  const [aiDifficulty, setAiDifficulty] = useState("medium");
  const [isLoading, setIsLoading] = useState(false);
  const [activeTab, setActiveTab] = useState("create");

  const [platformStats, setPlatformStats] = useState(null);
  const [myGamesCount, setMyGamesCount] = useState(null);
  const [isSignedIn, setIsSignedIn] = useState(() => !!localStorage.getItem("accessToken"));

  const loginAsGuest = async (nickname) => {
    if (!nickname || nickname.trim().length < 2) {
      alert('Please enter a nickname (2+ characters)')
      return
    }
    const trimmed = nickname.trim()
    try {
      const res = await fetch(`${API_URL}/api/auth/guest`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ nickname: trimmed })
      })
      console.log('Guest login status:', res.status)
      const data = await res.json()
      console.log('Guest login response:', data)
      if (!res.ok) {
        console.error('Guest login failed:', data)
        alert('Login failed: ' + (data.detail || 'Unknown error'))
        return
      }
      const token = data.access_token || data.token
      const playerId = data.player_id || data.id
      const playerNickname = data.nickname || trimmed
      if (!token) {
        console.error('No token in response:', data)
        return
      }
      localStorage.setItem('token', token)
      localStorage.setItem('access_token', token)
      localStorage.setItem('player_id', playerId)
      localStorage.setItem('nickname', playerNickname)
      localStorage.setItem('accessToken', token)
      localStorage.setItem('userId', playerId)
      localStorage.setItem('nickname', playerNickname)
      localStorage.setItem('authType', 'guest')
      setIsSignedIn(true)
      if (setAuth) setAuth({ token, playerId, nickname: playerNickname })
      navigate('/')
    } catch (err) {
      console.error('Guest login error:', err)
    }
  }

  const handleGuestLogin = async () => {
    if (!nickname.trim()) {
      alert('Please enter a nickname')
      return
    }

    const res = await fetch(
      `${API_URL}/api/auth/guest`,
      {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ nickname: nickname.trim() })
      }
    )

    const data = await res.json()

    // Save to localStorage (persists across tabs/refreshes)
    localStorage.setItem('token', data.access_token)
    localStorage.setItem('access_token', data.access_token)
    localStorage.setItem('player_id', data.player_id)
    localStorage.setItem('nickname', data.nickname)

    // Remove from localStorage if it was there before
    localStorage.removeItem('nickname')
    localStorage.removeItem('accessToken')
    localStorage.removeItem('userId')
    localStorage.removeItem('authType')

    navigate('/') // or wherever after login
  }

  // Navigation guard: redirect to /me if already signed in
  useEffect(() => {
    const hasOAuthParams = searchParams.get("access_token") && searchParams.get("user_id");
    if (hasOAuthParams) return;

    const wantsToPlay = searchParams.get("action") === "play";
    if (wantsToPlay) return;

    const savedToken = localStorage.getItem("accessToken");
    const savedUser = localStorage.getItem("userId");
    if (savedToken && savedUser) {
      navigate("/me", { replace: true });
    }
  }, []); // eslint-disable-line react-hooks/exhaustive-deps

  // Fetch public stats (no auth needed) with localStorage cache
  useEffect(() => {
    const cacheKey = "duoeng_platform_stats";
    const cached = localStorage.getItem(cacheKey);
    if (cached) {
      try {
        const parsed = JSON.parse(cached);
        if (parsed._cachedAt && Date.now() - parsed._cachedAt < 60000) {
          setPlatformStats(parsed);
          return;
        }
      } catch { /* ignore */ }
    }

    api.get("/stats")
      .then((res) => {
        const data = { ...res.data, _cachedAt: Date.now() };
        setPlatformStats(data);
        localStorage.setItem(cacheKey, JSON.stringify(data));
      })
      .catch(() => {});
  }, []);

  // Fetch "My Games" count for signed-in users
  useEffect(() => {
    const userId = localStorage.getItem("userId");
    const token = localStorage.getItem("accessToken");
    if (!userId || !token) return;

    api.get(`/players/${userId}/stats`)
      .then((res) => {
        setMyGamesCount(res.data?.total_games ?? null);
      })
      .catch(() => {});
  }, [isSignedIn]);

  const animatedWords = useCountUp(platformStats?.total_words || 0);
  const animatedGames = useCountUp(platformStats?.total_games_played || 0);
  const animatedMyGames = useCountUp(myGamesCount || 0);

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
      localStorage.setItem("accessToken", token);
      localStorage.setItem("userId", userId);
      localStorage.setItem("nickname", nick);
      localStorage.setItem("authType", "google");
      setNickname(nick);
      setIsSignedIn(true);
      toast.success(`Signed in as ${nick}`);
      window.history.replaceState({}, document.title, "/");
      navigate("/me");
    }
  }, [searchParams]); // eslint-disable-line react-hooks/exhaustive-deps

  const handleAuth = async () => {
    if (!nickname || nickname.trim().length < 2) {
      toast.error("Please enter a nickname (2+ characters)");
      return null;
    }
    const trimmed = nickname.trim();
    try {
      const response = await api.post("/auth/guest", { nickname: trimmed });
      const data = response.data;
      const token = data.access_token || data.token;
      const playerId = data.player_id || data.id;
      const playerNickname = data.nickname || trimmed;
      if (!token) {
        toast.error("No token in response");
        return null;
      }
      localStorage.setItem('token', token);
      localStorage.setItem('access_token', token);
      localStorage.setItem('player_id', playerId);
      localStorage.setItem('nickname', playerNickname);
      localStorage.setItem("accessToken", token);
      localStorage.setItem("userId", playerId);
      localStorage.setItem("nickname", playerNickname);
      localStorage.setItem("authType", "guest");
      setIsSignedIn(true);
      if (setAuth) setAuth({ token, playerId, nickname: playerNickname });
      return playerId;
    } catch (error) {
      toast.error("Failed to create user");
      return null;
    }
  };

  const handleCreateRoom = async () => {
    setIsLoading(true);
    const userId = await handleAuth();
    if (!userId) {
      setIsLoading(false);
      return;
    }

    try {
      const body = {
        mode,
        target_score: targetScore,
        word_level: wordLevel,
        use_favourites: useFavourites,
        use_custom_words: useCustomWords,
      };
      if (mode === "vs_ai") {
        body.ai_difficulty = aiDifficulty;
      }
      console.log("Creating room with body:", body);
      const response = await api.post("/rooms", body);
      console.log("Room creation response:", response);
      toast.success("Room created!");
      if (mode === "vs_ai") {
        console.log("Navigating to /game/" + response.data.code, response.data);
        navigate(`/game/${response.data.code}`);
      } else {
        console.log("Navigating to /lobby/" + response.data.code, response.data);
        navigate(`/lobby/${response.data.code}`);
      }
    } catch (error) {
      console.error("Room creation error:", error, error?.response?.data);
      toast.error(error.response?.data?.detail || "Failed to create room");
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

      {/* ── Stats Counters ── */}
      <div className="flex flex-wrap justify-center gap-4 mb-8 text-sm text-muted-foreground">
        {platformStats ? (
          <>
            <div className="flex items-center gap-1.5">
              <BookOpen className="w-4 h-4" />
              <span className="tabular-nums font-medium">{animatedWords.toLocaleString()}</span>
              <span>Words</span>
            </div>
            <div className="flex items-center gap-1.5">
              <Gamepad2 className="w-4 h-4" />
              <span className="tabular-nums font-medium">{animatedGames.toLocaleString()}</span>
              <span>Games Played</span>
            </div>
            {isSignedIn && myGamesCount !== null && (
              <div className="flex items-center gap-1.5">
                <Trophy className="w-4 h-4" />
                <span className="tabular-nums font-medium">{animatedMyGames.toLocaleString()}</span>
                <span>My Games</span>
              </div>
            )}
          </>
        ) : (
          <>
            <div className="flex items-center gap-1">
              <BookOpen className="w-4 h-4" />
              <div className="h-4 w-16 bg-muted rounded animate-pulse" />
            </div>
            <div className="flex items-center gap-1">
              <Gamepad2 className="w-4 h-4" />
              <div className="h-4 w-20 bg-muted rounded animate-pulse" />
            </div>
          </>
        )}
      </div>

      {/* CEFR Level Breakdown */}
      {platformStats?.words_by_level && Object.keys(platformStats.words_by_level).length > 0 && (
        <div className="flex flex-wrap justify-center gap-2 mb-6">
          {["A1", "A2", "B1", "B2", "C1", "C2"].map((level) => {
            const count = platformStats.words_by_level[level];
            if (!count) return null;
            return (
              <span
                key={level}
                className={`inline-flex items-center gap-1 px-2.5 py-1 rounded-full text-xs font-medium border ${getCefrColor(level)}`}
              >
                {level} <span className="text-muted-foreground">• {count}</span>
              </span>
            );
          })}
        </div>
      )}

      <Card className="w-full max-w-md lg:max-w-lg rounded-3xl shadow-soft border-0" data-testid="main-card">
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
              Signed in as <span className="font-semibold text-foreground">{localStorage.getItem("nickname")}</span>
              <span className="mx-1">•</span>
              <button
                className="text-primary hover:underline font-medium"
                onClick={() => navigate("/me")}
              >
                My Profile
              </button>
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

          <div className="flex gap-1 p-1 bg-muted rounded-full">
            <button
              data-testid="create-tab"
              className={`flex-1 py-2 px-3 rounded-full text-sm font-medium transition-all ${
                activeTab === "create" ? "bg-white shadow-sm text-black" : "text-muted-foreground hover:text-foreground"
              }`}
              onClick={() => { setActiveTab("create"); setMode("classic"); }}
            >
              <Users className="w-3.5 h-3.5 inline mr-1 -mt-0.5" />
              PvP
            </button>
            <button
              data-testid="ai-tab"
              className={`flex-1 py-2 px-3 rounded-full text-sm font-medium transition-all ${
                activeTab === "ai" ? "bg-white shadow-sm text-black" : "text-muted-foreground hover:text-foreground"
              }`}
              onClick={() => { setActiveTab("ai"); setMode("vs_ai"); }}
            >
              <Bot className="w-3.5 h-3.5 inline mr-1 -mt-0.5" />
              vs AI
            </button>
            <button
              data-testid="join-tab"
              className={`flex-1 py-2 px-3 rounded-full text-sm font-medium transition-all ${
                activeTab === "join" ? "bg-white shadow-sm text-black" : "text-muted-foreground hover:text-foreground"
              }`}
              onClick={() => setActiveTab("join")}
            >
              <Swords className="w-3.5 h-3.5 inline mr-1 -mt-0.5" />
              Join
            </button>
          </div>

          {(activeTab === "create" || activeTab === "ai") && (
            <div className="space-y-4 animate-fade-in-up">
              {activeTab === "create" && (
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
              )}

              {activeTab === "ai" && (
                <div className="text-center p-3 rounded-2xl bg-primary/5 border border-primary/20">
                  <Bot className="w-8 h-8 mx-auto text-primary mb-1" />
                  <p className="font-heading text-lg font-bold">Play vs AI</p>
                  <p className="text-xs text-muted-foreground">Challenge the bot and practice your vocabulary</p>
                </div>
              )}

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

              {/* Use Favourite Words toggle */}
              {isSignedIn && (
                <div className="flex items-center justify-between p-3 rounded-2xl border border-border bg-background">
                  <div className="flex items-center gap-2">
                    <Star className={`w-5 h-5 ${useFavourites ? "text-yellow-500 fill-yellow-500" : "text-muted-foreground"}`} />
                    <div>
                      <p className="text-sm font-medium">Play with my favourite words</p>
                      <p className="text-xs text-muted-foreground">Use words you've saved ⭐</p>
                    </div>
                  </div>
                  <button
                    type="button"
                    role="switch"
                    aria-checked={useFavourites}
                    className={`relative inline-flex h-6 w-11 items-center rounded-full transition-colors ${
                      useFavourites ? "bg-primary" : "bg-muted"
                    }`}
                    onClick={() => setUseFavourites(!useFavourites)}
                  >
                    <span
                      className={`inline-block h-4 w-4 transform rounded-full bg-white transition-transform ${
                        useFavourites ? "translate-x-6" : "translate-x-1"
                      }`}
                    />
                  </button>
                </div>
              )}

              {/* Custom Words toggle */}
              {isSignedIn && (
                <div className="flex items-center justify-between p-3 rounded-2xl border border-border bg-background">
                  <div className="flex items-center gap-2">
                    <BookOpen className={`w-5 h-5 ${useCustomWords ? "text-primary" : "text-muted-foreground"}`} />
                    <div>
                      <p className="text-sm font-medium">Include my custom words</p>
                      <p className="text-xs text-muted-foreground">Mix in words you added ✏️</p>
                    </div>
                  </div>
                  <button
                    type="button"
                    role="switch"
                    aria-checked={useCustomWords}
                    className={`relative inline-flex h-6 w-11 items-center rounded-full transition-colors ${
                      useCustomWords ? "bg-primary" : "bg-muted"
                    }`}
                    onClick={() => setUseCustomWords(!useCustomWords)}
                  >
                    <span
                      className={`inline-block h-4 w-4 transform rounded-full bg-white transition-transform ${
                        useCustomWords ? "translate-x-6" : "translate-x-1"
                      }`}
                    />
                  </button>
                </div>
              )}

              {/* AI Difficulty (for VS AI mode) */}
              {activeTab === "ai" && (
                <div className="space-y-2">
                  <Label className="text-sm font-medium">AI Difficulty</Label>
                  <RadioGroup value={aiDifficulty} onValueChange={setAiDifficulty} className="grid grid-cols-3 gap-3">
                    <Label
                      htmlFor="easy"
                      data-testid="ai-difficulty-easy"
                      className={`flex flex-col items-center p-4 rounded-2xl border-2 cursor-pointer transition-all ${
                        aiDifficulty === "easy" ? "border-primary bg-primary/5" : "border-border hover:border-primary/50"
                      }`}
                    >
                      <RadioGroupItem value="easy" id="easy" className="sr-only" />
                      <Users className="w-6 h-6 mb-2 text-primary-foreground" />
                      <span className="font-medium text-sm">Easy</span>
                      <span className="text-xs text-muted-foreground">For practice</span>
                    </Label>
                    <Label
                      htmlFor="medium"
                      data-testid="ai-difficulty-medium"
                      className={`flex flex-col items-center p-4 rounded-2xl border-2 cursor-pointer transition-all ${
                        aiDifficulty === "medium" ? "border-primary bg-primary/5" : "border-border hover:border-primary/50"
                      }`}
                    >
                      <RadioGroupItem value="medium" id="medium" className="sr-only" />
                      <Bot className="w-6 h-6 mb-2 text-accent-foreground" />
                      <span className="font-medium text-sm">Medium</span>
                      <span className="text-xs text-muted-foreground">Balanced challenge</span>
                    </Label>
                    <Label
                      htmlFor="hard"
                      data-testid="ai-difficulty-hard"
                      className={`flex flex-col items-center p-4 rounded-2xl border-2 cursor-pointer transition-all ${
                        aiDifficulty === "hard" ? "border-primary bg-primary/5" : "border-border hover:border-primary/50"
                      }`}
                    >
                      <RadioGroupItem value="hard" id="hard" className="sr-only" />
                      <Trophy className="w-6 h-6 mb-2 text-yellow-500" />
                      <span className="font-medium text-sm">Hard</span>
                      <span className="text-xs text-muted-foreground">For experts</span>
                    </Label>
                  </RadioGroup>
                </div>
              )}

              <Button
                data-testid="create-room-btn"
                className="w-full rounded-full h-12 text-base font-bold bg-primary hover:bg-primary/90"
                onClick={handleCreateRoom}
                disabled={isLoading}
              >
                {isLoading ? "Creating..." : activeTab === "ai" ? "Start vs AI" : "Create Room"}
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

      <Button
        variant="outline"
        className="w-full max-w-md lg:max-w-lg mt-3 rounded-full"
        onClick={() => navigate("/word-levels")}
      >
        Open Word Levels
      </Button>

      <p className="mt-8 text-sm text-muted-foreground">Learn Ukrainian vocabulary with friends</p>
    </div>
  );
}
