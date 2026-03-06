import { useState, useEffect, useCallback } from "react";
import { useNavigate, useParams } from "react-router-dom";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle, CardDescription } from "@/components/ui/card";
import { Copy, Users, Clock, Target, Loader2, Share2, Link2, BookOpen } from "lucide-react";
import { toast } from "sonner";
import api from "@/lib/api";
import CefrBadge from "@/components/CefrBadge";

export default function LobbyPage() {
  const navigate = useNavigate();
  const { code } = useParams();
  const [gameState, setGameState] = useState(null);
  const [isLoading, setIsLoading] = useState(true);
  const [copied, setCopied] = useState(false);

  const userId = localStorage.getItem("userId");
  const accessToken = localStorage.getItem("accessToken");
  const nickname = localStorage.getItem("nickname") || "a friend";

  const roomLink = `${process.env.REACT_APP_FRONTEND_URL || window.location.origin}/join/${code}`;

  const fetchGameState = useCallback(async () => {
    if (!userId || !accessToken) {
      navigate("/");
      return;
    }

    try {
      const response = await api.get(`/rooms/${code}/state`);
      setGameState(response.data);

      if (response.data.status === "playing") {
        navigate(`/game/${code}`);
      }
      if (response.data.status === "finished") {
        navigate(`/end/${code}`);
      }
    } catch (error) {
      toast.error("Failed to fetch room state");
      navigate("/");
    }
    setIsLoading(false);
  }, [accessToken, code, userId, navigate]);

  useEffect(() => {
    fetchGameState();
    const interval = setInterval(fetchGameState, 2000);
    return () => clearInterval(interval);
  }, [fetchGameState]);

  const copyCode = () => {
    navigator.clipboard.writeText(code);
    toast.success("Room code copied!");
  };

  const copyLink = async () => {
    const roomLink = `${window.location.origin}/join/${code}`;
    try {
      await navigator.clipboard.writeText(roomLink);
      setCopied(true);
      setTimeout(() => setCopied(false), 2000);
      toast.success("Room link copied!");
    } catch (err) {
      // Fallback for browsers that block clipboard API
      const textarea = document.createElement('textarea');
      textarea.value = roomLink;
      textarea.style.position = 'fixed';
      textarea.style.opacity = '0';
      document.body.appendChild(textarea);
      textarea.select();
      document.execCommand('copy');
      document.body.removeChild(textarea);
      setCopied(true);
      setTimeout(() => setCopied(false), 2000);
      toast.success("Room link copied!");
    }
  };

  const shareRoom = async () => {
    if (navigator.share) {
      try {
        await navigator.share({
          title: "DuoEng Vocabulary Duel",
          text: `Wanna duel ${nickname}? I dare you! 🎯`,
          url: roomLink,
        });
      } catch {
        // User cancelled
      }
    } else {
      copyLink();
    }
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
          <CardDescription>Share the room code or link with your friend</CardDescription>
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
            <p className="text-xs text-muted-foreground mt-2">Click to copy code</p>
          </div>

          {/* Room Link Display and Copy */}
          <div className="flex items-center gap-2 p-3 bg-gray-100 rounded-lg mt-4">
            <span className="text-sm text-gray-600 truncate flex-1">
              {window.location.origin}/join/{code}
            </span>
            <button
              onClick={() => copyLink()}
              className="shrink-0 px-3 py-1 bg-blue-500 text-white rounded text-sm"
            >
              {copied ? '✓ Copied!' : 'Copy'}
            </button>
          </div>

          {/* Share Buttons */}
          <div className="flex gap-2">
            <Button
              variant="outline"
              className="flex-1 rounded-full h-10 text-sm"
              onClick={copyLink}
            >
              <Link2 className="w-4 h-4 mr-2" />
              Copy Link
            </Button>
            <Button
              className="flex-1 rounded-full h-10 text-sm bg-primary hover:bg-primary/90"
              onClick={shareRoom}
            >
              <Share2 className="w-4 h-4 mr-2" />
              Share
            </Button>
          </div>

          {/* Game Settings */}
          {gameState && (
            <div className="grid grid-cols-3 gap-3">
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
              <div className="flex items-center gap-3 p-4 bg-muted rounded-2xl">
                <BookOpen className="w-5 h-5 text-muted-foreground" />
                <div>
                  <p className="text-xs text-muted-foreground">Level</p>
                  <CefrBadge level={gameState.word_level || "B1"} short />
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
