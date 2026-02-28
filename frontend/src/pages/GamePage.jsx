import { useState, useEffect, useCallback, useRef } from "react";
import { useNavigate, useParams } from "react-router-dom";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Card, CardContent } from "@/components/ui/card";
import { Clock, Trophy, CheckCircle2, XCircle, AlertCircle, Send, Loader2 } from "lucide-react";
import { toast } from "sonner";
import api from "@/lib/api";

export default function GamePage() {
  const navigate = useNavigate();
  const { code } = useParams();
  const [gameState, setGameState] = useState(null);
  const [answer, setAnswer] = useState("");
  const [isSubmitting, setIsSubmitting] = useState(false);
  const [lastFeedback, setLastFeedback] = useState(null);
  const inputRef = useRef(null);

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

      // Update last feedback
      if (response.data.last_feedback) {
        setLastFeedback(response.data.last_feedback);
      }

      // If game finished, navigate to end page
      if (response.data.status === "finished") {
        navigate(`/end/${code}`);
      }

      // If it's our turn, focus input
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

    // Poll every 2 seconds
    const interval = setInterval(fetchGameState, 2000);
    return () => clearInterval(interval);
  }, [fetchGameState]);

  const handleSubmit = async (e) => {
    e.preventDefault();
    if (!answer.trim() || isSubmitting) return;

    setIsSubmitting(true);
    try {
      const response = await api.post(`/rooms/${code}/turn`, {
        answer: answer.trim()
      });

      const { points, feedback, correct_answer, game_over } = response.data;

      // Show feedback toast
      if (feedback === "correct") {
        toast.success(`Correct! +${points} points`);
      } else if (feedback === "partial") {
        toast.info(`Partial match! +${points} point. Answer was: ${correct_answer}`);
      } else if (feedback === "expired") {
        toast.error(`Time expired! Correct answer: ${correct_answer}`);
      } else {
        toast.error(`Wrong! Correct answer: ${correct_answer}`);
      }

      setAnswer("");

      if (game_over) {
        navigate(`/end/${code}`);
      } else {
        // Refresh state
        await fetchGameState();
      }
    } catch (error) {
      toast.error(error.response?.data?.detail || "Failed to submit answer");
    }
    setIsSubmitting(false);
  };

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
      {/* Header */}
      <div className="max-w-md mx-auto w-full">
        {/* Mode Badge */}
        <div className="flex justify-center mb-4">
          <span className={`px-4 py-1 rounded-full text-sm font-medium ${
            gameState.mode === "challenge" 
              ? "bg-secondary/20 text-secondary-foreground" 
              : "bg-primary/20 text-primary-foreground"
          }`}>
            {gameState.mode === "challenge" ? "Challenge Mode" : "Classic Mode"}
          </span>
        </div>

        {/* Scoreboard */}
        <Card className="rounded-3xl shadow-soft border-0 mb-4" data-testid="scoreboard">
          <CardContent className="p-4">
            <div className="flex items-center justify-between">
              {/* Player 1 (You) */}
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

              {/* VS */}
              <div className="px-4">
                <div className="w-12 h-12 rounded-full bg-muted flex items-center justify-center">
                  <Trophy className="w-5 h-5 text-muted-foreground" />
                </div>
                <p className="text-xs text-center text-muted-foreground mt-1">
                  {gameState.target_score} pts
                </p>
              </div>

              {/* Player 2 (Opponent) */}
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

        {/* Timer (Challenge Mode) */}
        {gameState.mode === "challenge" && gameState.current_turn && (
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
                <p className="text-sm text-muted-foreground mb-2">Translate to English:</p>
                <p className="font-heading text-4xl sm:text-5xl font-bold text-foreground animate-fade-in-up" data-testid="word-display">
                  {gameState.current_turn.word_ua}
                </p>
                <p className="text-xs text-muted-foreground mt-4">
                  Exact answer = +2 pts | Description = +1 pt
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
                placeholder="Type your answer..."
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

        {/* Last Turn Feedback */}
        {lastFeedback && (
          <Card className={`rounded-2xl border-0 mb-4 ${
            lastFeedback.status === "expired" ? "bg-destructive/10" :
            lastFeedback.points === 2 ? "bg-accent/30" :
            lastFeedback.points === 1 ? "bg-primary/10" :
            "bg-destructive/10"
          }`} data-testid="feedback-card">
            <CardContent className="p-4">
              <div className="flex items-start gap-3">
                {lastFeedback.status === "expired" ? (
                  <AlertCircle className="w-5 h-5 text-destructive-foreground flex-shrink-0 mt-0.5" />
                ) : lastFeedback.points === 2 ? (
                  <CheckCircle2 className="w-5 h-5 text-accent-foreground flex-shrink-0 mt-0.5" />
                ) : lastFeedback.points === 1 ? (
                  <AlertCircle className="w-5 h-5 text-primary-foreground flex-shrink-0 mt-0.5" />
                ) : (
                  <XCircle className="w-5 h-5 text-destructive-foreground flex-shrink-0 mt-0.5" />
                )}
                <div className="flex-1 min-w-0">
                  <p className="text-sm font-medium">
                    {lastFeedback.player_nickname}'s turn:
                  </p>
                  <p className="text-sm text-muted-foreground">
                    {lastFeedback.word_ua} → {lastFeedback.correct_en}
                  </p>
                  <p className="text-xs text-muted-foreground mt-1">
                    Answer: "{lastFeedback.answer}" • 
                    {lastFeedback.status === "expired" ? " Time expired" : ` +${lastFeedback.points} pts`}
                  </p>
                </div>
              </div>
            </CardContent>
          </Card>
        )}
      </div>
    </div>
  );
}
