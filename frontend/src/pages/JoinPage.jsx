import { useState, useEffect } from "react";
import { useNavigate, useParams } from "react-router-dom";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Card, CardContent, CardHeader, CardTitle, CardDescription } from "@/components/ui/card";
import { Label } from "@/components/ui/label";
import { Loader2 } from "lucide-react";
import { toast } from "sonner";
import api from "@/lib/api";

export default function JoinPage() {
  const navigate = useNavigate();
  const { roomCode } = useParams();
  const [nickname, setNickname] = useState(localStorage.getItem("nickname") || "");
  const [isLoading, setIsLoading] = useState(false);
  const [autoJoining, setAutoJoining] = useState(false);

  const isSignedIn = !!localStorage.getItem("accessToken");

  // Auto-join if already signed in
  useEffect(() => {
    if (isSignedIn && roomCode && !autoJoining) {
      setAutoJoining(true);
      handleJoin();
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [isSignedIn, roomCode]);

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
      return playerId;
    } catch (error) {
      toast.error("Failed to create user");
      return null;
    }
  };

  const handleJoin = async () => {
    setIsLoading(true);

    let userId = localStorage.getItem("userId");
    if (!userId || !localStorage.getItem("accessToken")) {
      userId = await handleAuth();
      if (!userId) {
        setIsLoading(false);
        setAutoJoining(false);
        return;
      }
    }

    try {
      const response = await api.post(`/rooms/${roomCode.toUpperCase()}/join`);
      toast.success("Joined room!");
      const status = response.data.status;
      if (status === "playing" || status === "finished") {
        navigate(`/game/${roomCode.toUpperCase()}`);
      } else {
        navigate(`/lobby/${roomCode.toUpperCase()}`);
      }
    } catch (error) {
      toast.error(error.response?.data?.detail || "Failed to join room");
      setAutoJoining(false);
    }
    setIsLoading(false);
  };

  if (autoJoining && isSignedIn) {
    return (
      <div className="min-h-screen bg-background flex flex-col items-center justify-center p-4">
        <Loader2 className="w-8 h-8 animate-spin text-primary mb-4" />
        <p className="text-muted-foreground">Joining room {roomCode}...</p>
      </div>
    );
  }

  return (
    <div className="min-h-screen bg-background flex flex-col items-center justify-center p-4">
      <Card className="w-full max-w-md rounded-3xl shadow-soft border-0">
        <CardHeader className="text-center">
          <CardTitle className="font-heading text-2xl">Join Game</CardTitle>
          <CardDescription>You've been invited to room <span className="font-mono font-bold">{roomCode}</span></CardDescription>
        </CardHeader>
        <CardContent className="space-y-4">
          <div className="space-y-2">
            <Label htmlFor="nickname" className="text-sm font-medium">Your Nickname</Label>
            <Input
              id="nickname"
              placeholder="Enter your name..."
              value={nickname}
              onChange={(e) => setNickname(e.target.value)}
              className="rounded-full h-12 px-5"
              maxLength={20}
            />
          </div>
          <Button
            className="w-full rounded-full h-12 text-base font-bold bg-primary hover:bg-primary/90"
            onClick={handleJoin}
            disabled={isLoading}
          >
            {isLoading ? (
              <>
                <Loader2 className="w-4 h-4 animate-spin mr-2" />
                Joining...
              </>
            ) : (
              "Join Room"
            )}
          </Button>
          <Button
            variant="outline"
            className="w-full rounded-full"
            onClick={() => navigate("/")}
          >
            Back to Home
          </Button>
        </CardContent>
      </Card>
    </div>
  );
}
