import { useState, useEffect, useCallback } from "react";
import { useNavigate, useParams } from "react-router-dom";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle, CardDescription } from "@/components/ui/card";
import { Copy, Users, Clock, Target, Loader2 } from "lucide-react";
import { toast } from "sonner";
import axios from "axios";

const API = `${process.env.REACT_APP_BACKEND_URL}/api`;

export default function LobbyPage() {
  const navigate = useNavigate();
  const { code } = useParams();
  const [gameState, setGameState] = useState(null);
  const [isLoading, setIsLoading] = useState(true);

  const userId = sessionStorage.getItem("userId");
  const nickname = sessionStorage.getItem("nickname");

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

      // If game has started, navigate to game page
      if (response.data.status === "playing") {
        navigate(`/game/${code}`);
      }
    } catch (error) {
      toast.error("Failed to fetch room state");
      navigate("/");
    }
    setIsLoading(false);
  }, [code, userId, navigate]);

  useEffect(() => {
    fetchGameState();

    // Poll every 2 seconds
    const interval = setInterval(fetchGameState, 2000);
    return () => clearInterval(interval);
  }, [fetchGameState]);

  const copyCode = () => {
    navigator.clipboard.writeText(code);
    toast.success("Room code copied!");
  };

  if (isLoading) {
    return (
      <div className="min-h-screen bg-background flex items-center justify-center">
        <Loader2 className="w-8 h-8 animate-spin text-primary" />
      </div>
    );
  }

  return (
    <div className="min-h-screen bg-background flex flex-col items-center justify-center p-4">
      <Card className="w-full max-w-md rounded-3xl shadow-soft border-0" data-testid="lobby-card">
        <CardHeader className="text-center">
          <CardTitle className="font-heading text-2xl">Waiting for Opponent</CardTitle>
          <CardDescription>Share the room code with your friend</CardDescription>
        </CardHeader>
        <CardContent className="space-y-6">
          {/* Room Code Display */}
          <div className="text-center">
            <p className="text-sm text-muted-foreground mb-2">Room Code</p>
            <div 
              className="inline-flex items-center gap-3 bg-muted px-6 py-4 rounded-2xl cursor-pointer hover:bg-muted/80 transition-all"
              onClick={copyCode}
              data-testid="room-code-display"
            >
              <span className="font-heading text-3xl tracking-widest font-bold">{code}</span>
              <Copy className="w-5 h-5 text-muted-foreground" />
            </div>
            <p className="text-xs text-muted-foreground mt-2">Click to copy</p>
          </div>

          {/* Game Settings */}
          {gameState && (
            <div className="grid grid-cols-2 gap-4">
              <div className="flex items-center gap-3 p-4 bg-primary/10 rounded-2xl">
                <Clock className="w-5 h-5 text-primary-foreground" />
                <div>
                  <p className="text-xs text-muted-foreground">Mode</p>
                  <p className="font-medium capitalize">{gameState.mode}</p>
                </div>
              </div>
              <div className="flex items-center gap-3 p-4 bg-secondary/20 rounded-2xl">
                <Target className="w-5 h-5 text-secondary-foreground" />
                <div>
                  <p className="text-xs text-muted-foreground">Target</p>
                  <p className="font-medium">{gameState.target_score} pts</p>
                </div>
              </div>
            </div>
          )}

          {/* Players */}
          <div className="space-y-3">
            <div className="flex items-center gap-2 text-sm text-muted-foreground">
              <Users className="w-4 h-4" />
              <span>Players ({gameState?.players?.length || 0}/2)</span>
            </div>
            
            <div className="space-y-2">
              {gameState?.players?.map((player, index) => (
                <div 
                  key={player.user_id}
                  className="flex items-center gap-3 p-4 bg-card rounded-2xl border border-border"
                  data-testid={`player-${index}`}
                >
                  <div className="w-10 h-10 rounded-full bg-primary flex items-center justify-center text-primary-foreground font-bold">
                    {player.nickname[0].toUpperCase()}
                  </div>
                  <div className="flex-1">
                    <p className="font-medium">{player.nickname}</p>
                    {player.user_id === userId && (
                      <p className="text-xs text-primary">You</p>
                    )}
                  </div>
                  <span className="text-sm text-accent-foreground bg-accent px-3 py-1 rounded-full">
                    Ready
                  </span>
                </div>
              ))}

              {/* Waiting slot */}
              {gameState?.players?.length === 1 && (
                <div className="flex items-center gap-3 p-4 bg-muted/50 rounded-2xl border border-dashed border-border animate-pulse-soft">
                  <div className="w-10 h-10 rounded-full bg-muted flex items-center justify-center">
                    <Loader2 className="w-5 h-5 text-muted-foreground animate-spin" />
                  </div>
                  <p className="text-muted-foreground">Waiting for player...</p>
                </div>
              )}
            </div>
          </div>

          {/* Back Button */}
          <Button
            variant="outline"
            className="w-full rounded-full"
            onClick={() => navigate("/")}
            data-testid="back-btn"
          >
            Leave Lobby
          </Button>
        </CardContent>
      </Card>
    </div>
  );
}
