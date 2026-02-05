import { useState, useEffect, useCallback } from "react";
import { useNavigate, useParams } from "react-router-dom";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle, CardDescription } from "@/components/ui/card";
import { Trophy, Medal, RotateCcw, Home, Loader2 } from "lucide-react";
import axios from "axios";

const API = `${process.env.REACT_APP_BACKEND_URL}/api`;

export default function EndPage() {
  const navigate = useNavigate();
  const { code } = useParams();
  const [gameState, setGameState] = useState(null);
  const [isLoading, setIsLoading] = useState(true);

  const userId = sessionStorage.getItem("userId");

  const fetchGameState = useCallback(async () => {
    if (!userId) {
      navigate("/");
      return;
    }

    try {
      const response = await axios.get(`${API}/rooms/${code}/state`, {
        params: { user_id: userId }
      });
      setGameState(response.data);
    } catch (error) {
      console.error("Failed to fetch game state");
    }
    setIsLoading(false);
  }, [code, userId, navigate]);

  useEffect(() => {
    fetchGameState();
  }, [fetchGameState]);

  if (isLoading || !gameState) {
    return (
      <div className="min-h-screen bg-background flex items-center justify-center">
        <Loader2 className="w-8 h-8 animate-spin text-primary" />
      </div>
    );
  }

  const myPlayer = gameState.players.find(p => p.user_id === userId);
  const opponent = gameState.players.find(p => p.user_id !== userId);
  const isWinner = gameState.winner?.user_id === userId;

  return (
    <div className="min-h-screen bg-background flex flex-col items-center justify-center p-4" data-testid="end-page">
      {/* Celebration */}
      <div className="text-center mb-8 animate-fade-in-up">
        <div className={`inline-flex items-center justify-center w-24 h-24 rounded-full mb-4 ${
          isWinner ? "bg-accent" : "bg-secondary/30"
        }`}>
          {isWinner ? (
            <Trophy className="w-12 h-12 text-accent-foreground" />
          ) : (
            <Medal className="w-12 h-12 text-secondary-foreground" />
          )}
        </div>
        <h1 className="font-heading text-4xl sm:text-5xl font-bold text-foreground mb-2">
          {isWinner ? "Victory!" : "Game Over"}
        </h1>
        <p className="text-muted-foreground text-lg">
          {isWinner 
            ? "Congratulations, you won the duel!" 
            : `${gameState.winner?.nickname} won this round`
          }
        </p>
      </div>

      {/* Final Scores */}
      <Card className="w-full max-w-md rounded-3xl shadow-soft border-0 mb-6" data-testid="final-scores">
        <CardHeader className="text-center pb-2">
          <CardTitle className="font-heading text-xl">Final Scores</CardTitle>
          <CardDescription>Target was {gameState.target_score} points</CardDescription>
        </CardHeader>
        <CardContent className="p-6">
          <div className="flex items-center justify-around">
            {/* Winner */}
            <div className={`text-center p-4 rounded-2xl ${
              myPlayer?.score >= (opponent?.score || 0) ? "bg-accent/20" : ""
            }`}>
              <div className={`w-16 h-16 mx-auto rounded-full flex items-center justify-center text-xl font-bold mb-2 ${
                myPlayer?.score >= (opponent?.score || 0)
                  ? "bg-accent text-accent-foreground ring-4 ring-accent/30"
                  : "bg-muted text-muted-foreground"
              }`}>
                {myPlayer?.nickname[0].toUpperCase()}
              </div>
              <p className="font-medium">{myPlayer?.nickname}</p>
              <p className="text-xs text-muted-foreground mb-2">You</p>
              <p className="font-heading text-4xl font-bold" data-testid="final-my-score">
                {myPlayer?.score}
              </p>
              {isWinner && (
                <span className="inline-block mt-2 text-xs bg-accent text-accent-foreground px-2 py-1 rounded-full">
                  Winner
                </span>
              )}
            </div>

            {/* Divider */}
            <div className="text-2xl font-heading text-muted-foreground">vs</div>

            {/* Opponent */}
            <div className={`text-center p-4 rounded-2xl ${
              (opponent?.score || 0) > (myPlayer?.score || 0) ? "bg-secondary/20" : ""
            }`}>
              <div className={`w-16 h-16 mx-auto rounded-full flex items-center justify-center text-xl font-bold mb-2 ${
                (opponent?.score || 0) > (myPlayer?.score || 0)
                  ? "bg-secondary text-secondary-foreground ring-4 ring-secondary/30"
                  : "bg-muted text-muted-foreground"
              }`}>
                {opponent?.nickname[0].toUpperCase() || "?"}
              </div>
              <p className="font-medium">{opponent?.nickname || "Opponent"}</p>
              <p className="text-xs text-muted-foreground mb-2">Opponent</p>
              <p className="font-heading text-4xl font-bold" data-testid="final-opponent-score">
                {opponent?.score || 0}
              </p>
              {!isWinner && (
                <span className="inline-block mt-2 text-xs bg-secondary text-secondary-foreground px-2 py-1 rounded-full">
                  Winner
                </span>
              )}
            </div>
          </div>
        </CardContent>
      </Card>

      {/* Actions */}
      <div className="w-full max-w-md space-y-3">
        <Button
          data-testid="play-again-btn"
          className="w-full rounded-full h-12 text-base font-bold bg-primary hover:bg-primary/90"
          onClick={() => navigate("/")}
        >
          <RotateCcw className="w-5 h-5 mr-2" />
          Play Again
        </Button>
        <Button
          variant="outline"
          data-testid="home-btn"
          className="w-full rounded-full h-12 text-base"
          onClick={() => navigate("/")}
        >
          <Home className="w-5 h-5 mr-2" />
          Back to Home
        </Button>
      </div>

      {/* Game Mode Badge */}
      <p className="mt-8 text-sm text-muted-foreground">
        {gameState.mode === "challenge" ? "Challenge Mode" : "Classic Mode"} • Room {code}
      </p>
    </div>
  );
}
