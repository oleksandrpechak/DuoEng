import { useState } from "react";
import { useNavigate } from "react-router-dom";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Card, CardContent, CardHeader, CardTitle, CardDescription } from "@/components/ui/card";
import { Label } from "@/components/ui/label";
import { RadioGroup, RadioGroupItem } from "@/components/ui/radio-group";
import { Swords, BookOpen, Users, Zap } from "lucide-react";
import { toast } from "sonner";
import axios from "axios";

const API = `${process.env.REACT_APP_BACKEND_URL}/api`;

export default function LandingPage() {
  const navigate = useNavigate();
  const [nickname, setNickname] = useState("");
  const [joinCode, setJoinCode] = useState("");
  const [mode, setMode] = useState("classic");
  const [targetScore, setTargetScore] = useState(10);
  const [isLoading, setIsLoading] = useState(false);
  const [activeTab, setActiveTab] = useState("create");

  const handleAuth = async () => {
    if (!nickname.trim() || nickname.length < 2) {
      toast.error("Please enter a nickname (2+ characters)");
      return null;
    }

    try {
      const response = await axios.post(`${API}/auth/guest`, {
        nickname: nickname.trim()
      });
      sessionStorage.setItem("userId", response.data.user_id);
      sessionStorage.setItem("nickname", response.data.nickname);
      return response.data.user_id;
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
      const response = await axios.post(`${API}/rooms`, {
        user_id: userId,
        mode: mode,
        target_score: targetScore
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
      await axios.post(`${API}/rooms/${joinCode.toUpperCase()}/join`, {
        user_id: userId
      });
      toast.success("Joined room!");
      navigate(`/game/${joinCode.toUpperCase()}`);
    } catch (error) {
      toast.error(error.response?.data?.detail || "Failed to join room");
    }
    setIsLoading(false);
  };

  return (
    <div className="min-h-screen bg-background flex flex-col items-center justify-center p-4">
      {/* Hero Section */}
      <div className="text-center mb-8 animate-fade-in-up">
        <div className="inline-flex items-center justify-center w-20 h-20 rounded-full bg-primary/20 mb-4">
          <Swords className="w-10 h-10 text-primary-foreground" />
        </div>
        <h1 className="font-heading text-4xl sm:text-5xl font-bold text-foreground mb-2">
          DuoVocab Duel
        </h1>
        <p className="text-muted-foreground text-base sm:text-lg max-w-sm mx-auto">
          Challenge your friends to a Ukrainian-English vocabulary battle!
        </p>
      </div>

      {/* Features */}
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

      {/* Main Card */}
      <Card className="w-full max-w-md rounded-3xl shadow-soft border-0" data-testid="main-card">
        <CardHeader className="text-center pb-2">
          <CardTitle className="font-heading text-2xl">Enter the Arena</CardTitle>
          <CardDescription>Create a new game or join an existing one</CardDescription>
        </CardHeader>
        <CardContent className="space-y-6">
          {/* Nickname Input */}
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

          {/* Tab Switcher */}
          <div className="flex gap-2 p-1 bg-muted rounded-full">
            <button
              data-testid="create-tab"
              className={`flex-1 py-2 px-4 rounded-full text-sm font-medium transition-all ${
                activeTab === "create" 
                  ? "bg-white shadow-sm text-foreground" 
                  : "text-muted-foreground hover:text-foreground"
              }`}
              onClick={() => setActiveTab("create")}
            >
              Create Room
            </button>
            <button
              data-testid="join-tab"
              className={`flex-1 py-2 px-4 rounded-full text-sm font-medium transition-all ${
                activeTab === "join" 
                  ? "bg-white shadow-sm text-foreground" 
                  : "text-muted-foreground hover:text-foreground"
              }`}
              onClick={() => setActiveTab("join")}
            >
              Join Room
            </button>
          </div>

          {/* Create Room Form */}
          {activeTab === "create" && (
            <div className="space-y-4 animate-fade-in-up">
              {/* Game Mode */}
              <div className="space-y-3">
                <Label className="text-sm font-medium">Game Mode</Label>
                <RadioGroup 
                  value={mode} 
                  onValueChange={setMode}
                  className="grid grid-cols-2 gap-3"
                >
                  <Label
                    htmlFor="classic"
                    data-testid="mode-classic"
                    className={`flex flex-col items-center p-4 rounded-2xl border-2 cursor-pointer transition-all ${
                      mode === "classic" 
                        ? "border-primary bg-primary/5" 
                        : "border-border hover:border-primary/50"
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
                      mode === "challenge" 
                        ? "border-primary bg-primary/5" 
                        : "border-border hover:border-primary/50"
                    }`}
                  >
                    <RadioGroupItem value="challenge" id="challenge" className="sr-only" />
                    <Zap className="w-6 h-6 mb-2 text-secondary-foreground" />
                    <span className="font-medium text-sm">Challenge</span>
                    <span className="text-xs text-muted-foreground">30s per turn</span>
                  </Label>
                </RadioGroup>
              </div>

              {/* Target Score */}
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

          {/* Join Room Form */}
          {activeTab === "join" && (
            <div className="space-y-4 animate-fade-in-up">
              <div className="space-y-2">
                <Label htmlFor="roomCode" className="text-sm font-medium">Room Code</Label>
                <Input
                  id="roomCode"
                  data-testid="room-code-input"
                  placeholder="Enter 6-letter code..."
                  value={joinCode}
                  onChange={(e) => setJoinCode(e.target.value.toUpperCase())}
                  className="rounded-full h-12 px-5 text-center text-lg tracking-widest uppercase"
                  maxLength={6}
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

      {/* Footer */}
      <p className="mt-8 text-sm text-muted-foreground">
        Learn Ukrainian vocabulary with friends
      </p>
    </div>
  );
}
