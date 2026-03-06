import { useState, useEffect, useCallback, useRef } from "react";
import { useNavigate, useParams } from "react-router-dom";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Card, CardContent } from "@/components/ui/card";
import { Clock, Trophy, CheckCircle2, XCircle, AlertCircle, Send, Loader2, Pause, Play, LogOut, Zap } from "lucide-react";
import {
  AlertDialog,
  AlertDialogAction,
  AlertDialogCancel,
  AlertDialogContent,
  AlertDialogDescription,
  AlertDialogFooter,
  AlertDialogHeader,
  AlertDialogTitle,
  AlertDialogTrigger,
} from "@/components/ui/alert-dialog";
import { toast } from "sonner";
import api from "@/lib/api";
import CefrBadge from "@/components/CefrBadge";

export default function GamePage() {
  const navigate = useNavigate();
  const { code } = useParams();
  const [gameState, setGameState] = useState(null);
  const [answer, setAnswer] = useState('');
  const [isSubmitting, setIsSubmitting] = useState(false);
  const [lastFeedback, setLastFeedback] = useState(null);
  const [isPaused, setIsPaused] = useState(false);
  const [pausedBy, setPausedBy] = useState(null);
  const [scoringSourceMsg, setScoringSourceMsg] = useState(null);
  const [secondChance, setSecondChance] = useState(null); // { word_ua, word_en, expires_in }
  const [secondChanceAnswer, setSecondChanceAnswer] = useState("");
  const [isSecondChanceSubmitting, setIsSecondChanceSubmitting] = useState(false);
  const inputRef = useRef(null);
  const wsRef = useRef(null);

  const userId = sessionStorage.getItem("userId");
  const accessToken = sessionStorage.getItem("accessToken");

  const fetchGameState = useCallback(async () => {
    if (!userId || !accessToken) {
      navigate("/");
      return;
    }

    try {
      const response = await api.get(`/rooms/${code}/state`);
      setGameState(response.data);

      if (response.data.last_feedback) {
        setLastFeedback(response.data.last_feedback);
      }

      if (response.data.status === "finished") {
        navigate(`/end/${code}`);
      }

      if (response.data.status === "waiting") {
        navigate(`/lobby/${code}`);
      }

      const myPlayer = response.data.players.find(p => p.user_id === userId);
      if (myPlayer?.is_current_turn && inputRef.current) {
        inputRef.current.focus();
      }
    } catch (error) {
      console.error("Failed to fetch game state", error);
    }
  }, [accessToken, code, userId, navigate]);

  useEffect(() => {
    fetchGameState();
    const interval = setInterval(fetchGameState, 2000);
    return () => clearInterval(interval);
  }, [fetchGameState]);

  // WebSocket connection for real-time pause/resume/leave
  useEffect(() => {
    if (!accessToken || !code) return;

    const backendUrl = (process.env.REACT_APP_BACKEND_URL || "http://localhost:8000").replace(/^http/, "ws");
    const wsUrl = `${backendUrl}/ws/rooms/${code}?token=${accessToken}`;

    const ws = new WebSocket(wsUrl);
    wsRef.current = ws;

    ws.onmessage = (event) => {
      try {
        const msg = JSON.parse(event.data);
        if (msg.type === "game_paused") {
          setIsPaused(true);
          setPausedBy(msg.paused_by);
          toast.info(`Game paused by ${msg.paused_by}`);
        } else if (msg.type === "game_resumed") {
          setIsPaused(false);
          setPausedBy(null);
          toast.success("Game resumed!");
        } else if (msg.type === "opponent_left") {
          toast.success(msg.message || "Your opponent left. You win!");
          setTimeout(() => navigate(`/end/${code}`), 1500);
        } else if (msg.type === "game_state") {
          setGameState(msg.data);
          if (msg.data?.last_feedback) setLastFeedback(msg.data.last_feedback);
          if (msg.data?.status === "finished") navigate(`/end/${code}`);
        } else if (msg.type === "second_chance") {
          // Opponent answered wrong – you get a 10s steal opportunity
          setSecondChance({
            word_ua: msg.word_ua,
            word_en: msg.word_en,
            expires_in: msg.expires_in || 10,
          });
          setSecondChanceAnswer("");
          toast.info("⚡ Steal opportunity! Answer before time runs out!");
        } else if (msg.type === "second_chance_expired") {
          setSecondChance(null);
          setSecondChanceAnswer("");
        } else if (msg.type === "second_chance") {
          setSecondChance(msg.data);
          toast.info("You have a second chance to answer!");
        }
      } catch {
        // ignore parse errors
      }
    };

    ws.onerror = () => {};
    ws.onclose = () => {};

    return () => {
      ws.close();
      wsRef.current = null;
    };
  }, [accessToken, code, navigate]);

  const handlePauseResume = () => {
    const ws = wsRef.current;
    if (!ws || ws.readyState !== WebSocket.OPEN) {
      toast.error("Not connected");
      return;
    }
    if (isPaused) {
      ws.send(JSON.stringify({ type: "resume" }));
    } else {
      ws.send(JSON.stringify({ type: "pause" }));
    }
  };

  const handleLeave = async () => {
    try {
      await api.post(`/rooms/${code}/leave`);
      toast.info("You left the match");
      navigate("/");
    } catch (error) {
      toast.error(error.response?.data?.detail || "Failed to leave");
    }
  };

  const handleSecondChanceSubmit = async (e) => {
    e.preventDefault();
    if (!secondChanceAnswer.trim() || isSecondChanceSubmitting) return;
    setIsSecondChanceSubmitting(true);
    try {
      const response = await api.post(`/rooms/${code}/second-chance`, {
        answer: secondChanceAnswer.trim(),
      });
      const { points, feedback } = response.data;
      if (points > 0) {
        toast.success(`⚡ Steal! +${points} point${points > 1 ? "s" : ""}`);
      } else {
        toast.error("Steal missed!");
      }
      setSecondChance(null);
      setSecondChanceAnswer("");
      await fetchGameState();
    } catch (error) {
      toast.error(error.response?.data?.detail || "Failed to submit steal");
    }
    setIsSecondChanceSubmitting(false);
  };

  const handleSubmit = async (e) => {
    e.preventDefault();
    if (!answer.trim() || isSubmitting) return;
    // Clear input immediately
    setAnswer('');
    if (inputRef.current) {
      inputRef.current.value = '';
      inputRef.current.focus();
    }
    setIsSubmitting(true);
    try {
      const response = await api.post(`/rooms/${code}/turn`, {
        answer: answer.trim()
      });

      const { points, feedback, correct_answer, game_over, scoring_source } = response.data;

      // Show scoring source feedback for 2.5 seconds
      const source = (scoring_source || "").toLowerCase();
      if (feedback === "exact" || points >= 2) {
        setScoringSourceMsg({
          text: `🎯 +${points} · exact translation!`,
          color: "bg-emerald-100 text-emerald-800 dark:bg-emerald-900/40 dark:text-emerald-300",
        });
        toast.success(`Perfect translation! +${points} points`);
      } else if (feedback === "correct" || points === 1) {
        const isDictionary = source.includes("dictionary");
        setScoringSourceMsg({
          text: isDictionary ? `✓ +${points} · similar match` : `✓ +${points} · AI accepted`,
          color: isDictionary ? "bg-green-100 text-green-800 dark:bg-green-900/40 dark:text-green-300"
                              : "bg-blue-100 text-blue-800 dark:bg-blue-900/40 dark:text-blue-300",
        });
        toast.success(`Good description! +${points} point`);
      } else if (feedback === "expired") {
        setScoringSourceMsg(null);
        toast.error(`Time expired! The word was: ${correct_answer}`);
      } else {
        const isDictionary = source.includes("dictionary");
        setScoringSourceMsg({
          text: isDictionary ? `✗ 0 · dictionary: no match` : `✗ 0 · AI: incorrect`,
          color: isDictionary ? "bg-red-100 text-red-800 dark:bg-red-900/40 dark:text-red-300"
                              : "bg-orange-100 text-orange-800 dark:bg-orange-900/40 dark:text-orange-300",
        });
        toast.error(`Not accepted. The word was: ${correct_answer}`);
      }

      // Auto-clear scoring source message after 2.5s
      setTimeout(() => setScoringSourceMsg(null), 2500);

      setAnswer("");

      if (game_over) {
        navigate(`/end/${code}`);
      } else {
        await fetchGameState();
      }
    } catch (error) {
      toast.error(error.response?.data?.detail || "Failed to submit answer");
    }
    setIsSubmitting(false);
  };

  useEffect(() => {
    if (gameState?.current_turn) {
      setAnswer('');
      if (inputRef.current) {
        inputRef.current.value = '';
        inputRef.current.focus();
      }
    }
  }, [gameState?.current_turn]);

  if (!gameState) {
    return (
      <div className="min-h-screen bg-background flex items-center justify-center">
        <Loader2 className="w-8 h-8 animate-spin text-primary" />
      </div>
    );
  }

  const myPlayer = gameState.players.find(p => p.user_id === userId);
  const opponent = gameState.players.find(p => p.user_id !== userId);
  const isMyTurn = myPlayer?.is_current_turn;

  return (
    <div className="min-h-screen bg-background flex flex-col p-4" data-testid="game-page">
      <div className="max-w-md lg:max-w-lg mx-auto w-full">
        {/* Mode & Level Badges */}
        <div className="flex justify-center gap-2 mb-4">
          <span className={`px-4 py-1 rounded-full text-sm font-medium ${
            gameState.mode === "challenge" 
              ? "bg-secondary/20 text-secondary-foreground"
              : gameState.mode === "vs_ai"
              ? "bg-purple-100 text-purple-800 dark:bg-purple-900/30 dark:text-purple-300"
              : "bg-primary/20 text-primary-foreground"
          }`}>
            {gameState.mode === "challenge" ? "Challenge Mode" : gameState.mode === "vs_ai" ? "vs AI" : "Classic Mode"}
          </span>
          <CefrBadge level={gameState.word_level || "B1"} className="text-sm px-4 py-1" />
        </div>

        {/* Scoreboard */}
        <Card className="rounded-3xl shadow-soft border-0 mb-4" data-testid="scoreboard">
          <CardContent className="p-4">
            <div className="flex items-center justify-between">
              <div className={`flex-1 text-center p-3 rounded-2xl transition-all ${
                isMyTurn ? "bg-primary/10" : ""
              }`}>
                <div className={`w-12 h-12 mx-auto rounded-full flex items-center justify-center text-lg font-bold mb-2 ${
                  isMyTurn ? "bg-primary text-primary-foreground ring-4 ring-primary/30" : "bg-muted text-muted-foreground"
                }`}>
                  {myPlayer?.nickname[0].toUpperCase()}
                </div>
                <p className="text-sm font-medium truncate">{myPlayer?.nickname}</p>
                <p className="text-xs text-muted-foreground">You</p>
                <p className="font-heading text-3xl font-bold mt-1" data-testid="my-score">
                  {myPlayer?.score}
                </p>
              </div>

              <div className="px-4">
                <div className="w-12 h-12 rounded-full bg-muted flex items-center justify-center">
                  <Trophy className="w-5 h-5 text-muted-foreground" />
                </div>
                <p className="text-xs text-center text-muted-foreground mt-1">
                  {gameState.target_score} pts
                </p>
              </div>

              <div className={`flex-1 text-center p-3 rounded-2xl transition-all ${
                opponent?.is_current_turn ? "bg-secondary/10" : ""
              }`}>
                <div className={`w-12 h-12 mx-auto rounded-full flex items-center justify-center text-lg font-bold mb-2 ${
                  opponent?.is_current_turn ? "bg-secondary text-secondary-foreground ring-4 ring-secondary/30" : "bg-muted text-muted-foreground"
                }`}>
                  {opponent?.nickname[0].toUpperCase() || "?"}
                </div>
                <p className="text-sm font-medium truncate">{opponent?.nickname || "Waiting..."}</p>
                <p className="text-xs text-muted-foreground">Opponent</p>
                <p className="font-heading text-3xl font-bold mt-1" data-testid="opponent-score">
                  {opponent?.score || 0}
                </p>
              </div>
            </div>
          </CardContent>
        </Card>

        {/* Timer */}
        {gameState.current_turn && gameState.current_turn.time_remaining != null && (
          <div className="text-center mb-4" data-testid="timer">
            <div className={`inline-flex items-center gap-2 px-4 py-2 rounded-full ${
              gameState.current_turn.time_remaining <= 10 
                ? "bg-destructive/20 text-destructive-foreground animate-pulse" 
                : "bg-muted text-muted-foreground"
            }`}>
              <Clock className="w-5 h-5" />
              <span className="font-heading text-2xl font-bold">
                {gameState.current_turn.time_remaining || 0}s
              </span>
            </div>
          </div>
        )}

        {/* Word Card */}
        <Card className="rounded-3xl shadow-soft border-0 mb-4" data-testid="word-card">
          <CardContent className="p-8 text-center">
            {isMyTurn && gameState.current_turn ? (
              <>
                <p className="text-sm text-muted-foreground mb-2">🇺🇦 Translate or describe this word in English:</p>
                <p className="font-heading text-4xl sm:text-5xl font-bold text-foreground animate-fade-in-up" data-testid="word-display">
                  {gameState.current_turn.word_ua || gameState.current_turn.word_en}
                </p>
                <p className="text-xs text-muted-foreground mt-4">
                  Exact translation → +2 pts • Description / similar → +1 pt
                </p>
              </>
            ) : (
              <div className="py-8">
                <Loader2 className="w-8 h-8 mx-auto animate-spin text-muted-foreground mb-4" />
                <p className="text-muted-foreground">
                  {opponent?.nickname || "Opponent"}'s turn...
                </p>
              </div>
            )}
          </CardContent>
        </Card>

        {/* Answer Input */}
        {isMyTurn && gameState.current_turn && (
          <form onSubmit={handleSubmit} className="mb-4 animate-fade-in-up">
            <div className="flex gap-2">
              <Input
                ref={inputRef}
                data-testid="answer-input"
                placeholder="Your English answer..."
                value={answer}
                onChange={(e) => setAnswer(e.target.value)}
                className="rounded-full h-14 px-6 text-lg flex-1"
                disabled={isSubmitting}
                autoComplete="off"
              />
              <Button
                type="submit"
                data-testid="submit-btn"
                className="rounded-full h-14 w-14 p-0 bg-primary hover:bg-primary/90"
                disabled={isSubmitting || !answer.trim()}
              >
                {isSubmitting ? (
                  <Loader2 className="w-5 h-5 animate-spin" />
                ) : (
                  <Send className="w-5 h-5" />
                )}
              </Button>
            </div>
          </form>
        )}

        {/* Scoring Source Badge */}
        {scoringSourceMsg && (
          <div className="mb-3 flex justify-center animate-fade-in-up" data-testid="scoring-source">
            <span className={`inline-flex items-center gap-1.5 px-4 py-2 rounded-full text-sm font-medium transition-opacity ${scoringSourceMsg.color}`}>
              {scoringSourceMsg.text}
            </span>
          </div>
        )}

        {/* Last Turn Feedback */}
        {lastFeedback && (
          <Card className={`rounded-2xl border-0 mb-4 ${
            lastFeedback.status === "expired" ? "bg-destructive/10" :
            lastFeedback.points >= 2 ? "bg-emerald-100/50 dark:bg-emerald-900/20" :
            lastFeedback.points >= 1 ? "bg-accent/30" :
            "bg-destructive/10"
          }`} data-testid="feedback-card">
            <CardContent className="p-4">
              <div className="flex items-start gap-3">
                {lastFeedback.status === "expired" ? (
                  <AlertCircle className="w-5 h-5 text-destructive-foreground flex-shrink-0 mt-0.5" />
                ) : lastFeedback.points >= 1 ? (
                  <CheckCircle2 className="w-5 h-5 text-accent-foreground flex-shrink-0 mt-0.5" />
                ) : (
                  <XCircle className="w-5 h-5 text-destructive-foreground flex-shrink-0 mt-0.5" />
                )}
                <div className="flex-1 min-w-0">
                  <p className="text-sm font-medium">
                    {lastFeedback.player_nickname}'s turn:
                  </p>
                  <p className="text-sm text-muted-foreground">
                    🇺🇦 {lastFeedback.word_ua || lastFeedback.correct_en} → 🇬🇧 {lastFeedback.correct_en}
                  </p>
                  <p className="text-xs text-muted-foreground mt-1">
                    Answer: "{lastFeedback.answer}" • 
                    {lastFeedback.status === "expired" ? " Time expired" : ` +${lastFeedback.points} pts`}
                    {lastFeedback.scoring_source && lastFeedback.status !== "expired" && (
                      <span className={`ml-1 ${
                        lastFeedback.scoring_source.includes("dictionary") ? "text-green-600 dark:text-green-400" :
                        lastFeedback.scoring_source.includes("llm") ? "text-blue-600 dark:text-blue-400" :
                        ""
                      }`}>
                        · {lastFeedback.scoring_source.includes("dictionary") ? "dictionary" : lastFeedback.scoring_source.includes("llm") ? "AI" : lastFeedback.scoring_source}
                      </span>
                    )}
                  </p>
                </div>
              </div>
            </CardContent>
          </Card>
        )}

        {/* Pause & Leave Buttons */}
        <div className="flex gap-2 mb-4">
          <Button
            variant="outline"
            className={`flex-1 rounded-full h-10 text-sm font-medium ${
              isPaused
                ? "bg-accent/20 border-accent text-accent-foreground hover:bg-accent/30"
                : "bg-amber-500/10 border-amber-500/30 text-amber-600 hover:bg-amber-500/20"
            }`}
            onClick={handlePauseResume}
            data-testid="pause-btn"
          >
            {isPaused ? (
              <>
                <Play className="w-4 h-4 mr-2" />
                Resume
              </>
            ) : (
              <>
                <Pause className="w-4 h-4 mr-2" />
                Pause
              </>
            )}
          </Button>

          <AlertDialog>
            <AlertDialogTrigger asChild>
              <Button
                variant="outline"
                className="flex-1 rounded-full h-10 text-sm font-medium bg-destructive/10 border-destructive/30 text-destructive hover:bg-destructive/20"
                data-testid="leave-btn"
              >
                <LogOut className="w-4 h-4 mr-2" />
                Leave
              </Button>
            </AlertDialogTrigger>
            <AlertDialogContent className="rounded-2xl">
              <AlertDialogHeader>
                <AlertDialogTitle>Leave the match?</AlertDialogTitle>
                <AlertDialogDescription>
                  Are you sure you want to leave? You will forfeit the match and your opponent will win.
                </AlertDialogDescription>
              </AlertDialogHeader>
              <AlertDialogFooter>
                <AlertDialogCancel className="rounded-full">Cancel</AlertDialogCancel>
                <AlertDialogAction
                  className="rounded-full bg-destructive text-destructive-foreground hover:bg-destructive/90"
                  onClick={handleLeave}
                >
                  Leave Match
                </AlertDialogAction>
              </AlertDialogFooter>
            </AlertDialogContent>
          </AlertDialog>
        </div>
      </div>

      {/* PAUSED Overlay */}
      {isPaused && (
        <div className="fixed inset-0 z-40 bg-black/60 flex items-center justify-center" data-testid="paused-overlay">
          <div className="text-center animate-fade-in-up">
            <div className="bg-card rounded-3xl p-8 shadow-lg max-w-sm mx-4">
              <Pause className="w-16 h-16 mx-auto text-amber-500 mb-4" />
              <h2 className="font-heading text-3xl font-bold text-foreground mb-2">PAUSED</h2>
              <p className="text-muted-foreground mb-6">
                {pausedBy ? `Paused by ${pausedBy}` : "Game is paused"}
              </p>
              <Button
                className="rounded-full px-8 h-12 text-base bg-accent hover:bg-accent/90"
                onClick={handlePauseResume}
              >
                <Play className="w-5 h-5 mr-2" />
                Resume Game
              </Button>
            </div>
          </div>
        </div>
      )}

      {/* SECOND CHANCE (Steal) Overlay */}
      {secondChance && (
        <div className="fixed inset-0 z-50 bg-black/60 flex items-center justify-center" data-testid="second-chance-overlay">
          <div className="bg-card rounded-3xl p-8 shadow-lg max-w-sm mx-4 animate-fade-in-up">
            <Zap className="w-16 h-16 mx-auto text-yellow-500 mb-4 animate-pulse" />
            <h2 className="font-heading text-2xl font-bold text-foreground mb-1 text-center">⚡ Steal Opportunity!</h2>
            <p className="text-sm text-muted-foreground mb-4 text-center">
              Your opponent got it wrong. Can you translate this word?
            </p>
            <p className="font-heading text-4xl text-center mb-6">
              🇺🇦 {secondChance.word_ua}
            </p>
            <form onSubmit={handleSecondChanceSubmit} className="mb-4">
              <div className="flex gap-2">
                <Input
                  placeholder="Your English answer..."
                  value={secondChanceAnswer}
                  onChange={(e) => setSecondChanceAnswer(e.target.value)}
                  className="rounded-full h-14 px-6 text-lg flex-1"
                  disabled={isSecondChanceSubmitting}
                  autoComplete="off"
                  autoFocus
                />
                <Button
                  type="submit"
                  className="rounded-full h-14 w-14 p-0 bg-yellow-500 hover:bg-yellow-600 text-white"
                  disabled={isSecondChanceSubmitting || !secondChanceAnswer.trim()}
                >
                  {isSecondChanceSubmitting ? (
                    <Loader2 className="w-5 h-5 animate-spin" />
                  ) : (
                    <Send className="w-5 h-5" />
                  )}
                </Button>
              </div>
            </form>
            <div className="flex items-center justify-center gap-2 text-sm text-muted-foreground">
              <Clock className="w-4 h-4" />
              <span>~{secondChance.expires_in}s remaining</span>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
