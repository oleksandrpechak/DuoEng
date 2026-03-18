import { useState, useEffect } from "react";
import { useNavigate } from "react-router-dom";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle, CardDescription } from "@/components/ui/card";
import {
  ArrowLeft,
  Loader2,
  Star,
  Gamepad2,
  XCircle,
  Bot,
  Users,
  Trophy,
} from "lucide-react";
import { toast } from "sonner";
import api from "@/lib/api";

export default function WrongWordsPage() {
  const navigate = useNavigate();
  const [wrongWords, setWrongWords] = useState([]);
  const [isLoading, setIsLoading] = useState(true);
  const [favouriteLoading, setFavouriteLoading] = useState(new Set());
  const [aiDifficulty, setAiDifficulty] = useState("medium");
  const [isPracticeLoading, setIsPracticeLoading] = useState(false);
  const [isAiPracticeLoading, setIsAiPracticeLoading] = useState(false);

  const accessToken = localStorage.getItem("accessToken");
  const userId = localStorage.getItem("userId");

  useEffect(() => {
    if (!accessToken || !userId) {
      navigate("/", { replace: true });
      return;
    }
    loadWrongWords();
  }, [accessToken, userId]); // eslint-disable-line react-hooks/exhaustive-deps

  const loadWrongWords = async () => {
    setIsLoading(true);
    try {
      const response = await api.get("/players/me/wrong-words", { params: { limit: 50 } });
      setWrongWords(response.data || []);
    } catch (error) {
      toast.error("Failed to load wrong words");
    }
    setIsLoading(false);
  };

  const handleAddToFavourites = async (word) => {
    const wordId = word.correct_answer.toLowerCase().replace(/ /g, "_").replace(/'/g, "").slice(0, 64);
    setFavouriteLoading((prev) => new Set(prev).add(wordId));
    try {
      await api.post("/players/me/favourites", { word_id: wordId });
      toast.success("Added to favourites ⭐");
    } catch (error) {
      const detail = error.response?.data?.detail || "Failed to add to favourites";
      toast.error(detail);
    }
    setFavouriteLoading((prev) => {
      const next = new Set(prev);
      next.delete(wordId);
      return next;
    });
  };

  const handlePractice = async () => {
    setIsPracticeLoading(true);
    // Collect unique correct_answer word IDs
    const wordIds = [...new Set(wrongWords.map(w =>
      w.correct_answer.toLowerCase().replace(/ /g, "_").replace(/'/g, "").slice(0, 64)
    ))].slice(0, 50);

    try {
      const response = await api.post("/rooms", {
        mode: "classic",
        target_score: Math.min(wrongWords.length, 10),
        word_level: "B1",
        word_ids: wordIds,
      });
      toast.success("Practice room created!");
      navigate(`/lobby/${response.data.code}`);
    } catch (error) {
      toast.error("Failed to create practice room");
    }
    setIsPracticeLoading(false);
  };

  const handlePracticeWithAI = async () => {
    setIsAiPracticeLoading(true);
    const wordIds = [...new Set(wrongWords.map(w =>
      w.correct_answer.toLowerCase().replace(/ /g, "_").replace(/'/g, "").slice(0, 64)
    ))].slice(0, 50);

    try {
      const response = await api.post("/rooms", {
        mode: "vs_ai",
        target_score: Math.min(wrongWords.length, 10),
        word_level: "B1",
        word_ids: wordIds,
        ai_difficulty: aiDifficulty,
      });
      toast.success("AI practice room created! 🤖");
      navigate(`/game/${response.data.code}`);
    } catch (error) {
      toast.error("Failed to create AI practice room");
    }
    setIsAiPracticeLoading(false);
  };

  const getColorClass = (timesWrong) => {
    if (timesWrong >= 3) return "border-red-400 bg-red-50 dark:bg-red-950/30";
    if (timesWrong >= 2) return "border-orange-400 bg-orange-50 dark:bg-orange-950/30";
    return "border-yellow-400 bg-yellow-50 dark:bg-yellow-950/30";
  };

  if (!accessToken || !userId) return null;

  return (
    <div className="min-h-screen bg-background flex flex-col items-center p-4 pt-8">
      <div className="w-full max-w-md lg:max-w-2xl space-y-6 animate-fade-in-up">
        {/* Header */}
        <div className="flex items-center gap-3">
          <Button
            variant="ghost"
            size="icon"
            className="rounded-full"
            onClick={() => navigate("/me")}
          >
            <ArrowLeft className="w-5 h-5" />
          </Button>
          <div>
            <h1 className="font-heading text-2xl font-bold">❌ Words I Got Wrong</h1>
            <p className="text-sm text-muted-foreground">
              Practice your most challenging words
            </p>
          </div>
        </div>

        {/* Practice Buttons */}
        {wrongWords.length > 0 && (
          <div className="space-y-3">
            {/* Practice with AI Section */}
            <Card className="rounded-2xl border-2 border-purple-200 dark:border-purple-800 bg-purple-50/50 dark:bg-purple-950/20">
              <CardContent className="p-4 space-y-3">
                <div className="flex items-center gap-2 mb-1">
                  <Bot className="w-5 h-5 text-purple-600 dark:text-purple-400" />
                  <span className="font-heading text-base font-bold text-purple-800 dark:text-purple-200">
                    Train with AI
                  </span>
                </div>
                <p className="text-xs text-muted-foreground">
                  Practice your wrong words against the AI bot. Choose a difficulty:
                </p>

                {/* AI Difficulty Selector */}
                <div className="grid grid-cols-3 gap-2">
                  {[
                    { value: "easy", label: "Easy", desc: "For practice", icon: Users, color: "border-green-400 bg-green-50 dark:bg-green-950/30" },
                    { value: "medium", label: "Medium", desc: "Balanced", icon: Bot, color: "border-yellow-400 bg-yellow-50 dark:bg-yellow-950/30" },
                    { value: "hard", label: "Hard", desc: "Expert", icon: Trophy, color: "border-red-400 bg-red-50 dark:bg-red-950/30" },
                  ].map((item) => (
                    <button
                      key={item.value}
                      className={`flex flex-col items-center p-2.5 rounded-xl border-2 cursor-pointer transition-all text-center ${
                        aiDifficulty === item.value
                          ? `${item.color} ring-2 ring-offset-1 ring-purple-400/40`
                          : "border-border hover:border-purple-300 bg-background"
                      }`}
                      onClick={() => setAiDifficulty(item.value)}
                    >
                      <item.icon className="w-4 h-4 mb-1" />
                      <span className="text-xs font-bold">{item.label}</span>
                      <span className="text-[10px] text-muted-foreground">{item.desc}</span>
                    </button>
                  ))}
                </div>

                <Button
                  className="w-full rounded-2xl h-11 text-base font-bold bg-purple-600 hover:bg-purple-700 text-white flex items-center justify-center gap-2"
                  onClick={handlePracticeWithAI}
                  disabled={isAiPracticeLoading}
                >
                  {isAiPracticeLoading ? (
                    <Loader2 className="w-5 h-5 animate-spin" />
                  ) : (
                    <Bot className="w-5 h-5" />
                  )}
                  {isAiPracticeLoading ? "Creating..." : "Start AI Practice"}
                </Button>
              </CardContent>
            </Card>

            {/* Practice PvP Button */}
            <Button
              variant="outline"
              className="w-full rounded-2xl h-11 text-base font-bold flex items-center justify-center gap-2"
              onClick={handlePractice}
              disabled={isPracticeLoading}
            >
              {isPracticeLoading ? (
                <Loader2 className="w-5 h-5 animate-spin" />
              ) : (
                <Gamepad2 className="w-5 h-5" />
              )}
              {isPracticeLoading ? "Creating..." : "Practice with a Friend (PvP)"}
            </Button>
          </div>
        )}

        {/* Wrong Words List */}
        {isLoading ? (
          <div className="flex justify-center py-12">
            <Loader2 className="w-8 h-8 animate-spin text-primary" />
          </div>
        ) : wrongWords.length === 0 ? (
          <Card className="rounded-2xl border-0 shadow-soft">
            <CardContent className="p-8 text-center">
              <XCircle className="w-12 h-12 mx-auto text-muted-foreground mb-4" />
              <p className="text-lg font-medium mb-2">No wrong answers yet!</p>
              <p className="text-sm text-muted-foreground">
                Play some games and your missed words will appear here.
              </p>
            </CardContent>
          </Card>
        ) : (
          <div className="space-y-3">
            {wrongWords.map((word, idx) => {
              const wordId = word.correct_answer.toLowerCase().replace(/ /g, "_").replace(/'/g, "").slice(0, 64);
              const isFavLoading = favouriteLoading.has(wordId);

              return (
                <Card
                  key={`${word.ua_word}-${word.correct_answer}-${idx}`}
                  className={`rounded-2xl border-2 ${getColorClass(word.times_wrong)}`}
                >
                  <CardContent className="p-4">
                    <div className="flex items-start justify-between">
                      <div className="flex-1 min-w-0">
                        <div className="flex items-center gap-2 mb-1">
                          <span className="text-lg font-bold">🇺🇦 {word.ua_word}</span>
                          <span className="text-muted-foreground">→</span>
                          <span className="text-lg font-semibold text-green-600 dark:text-green-400">
                            🇬🇧 {word.correct_answer}
                          </span>
                        </div>
                        {word.user_answer && (
                          <p className="text-sm text-destructive">
                            Your answer: "{word.user_answer}"
                          </p>
                        )}
                        <div className="flex items-center gap-3 mt-2">
                          <span className={`inline-flex items-center px-2 py-0.5 rounded-full text-xs font-medium ${
                            word.times_wrong >= 3
                              ? "bg-red-200 text-red-800 dark:bg-red-900/50 dark:text-red-300"
                              : word.times_wrong >= 2
                              ? "bg-orange-200 text-orange-800 dark:bg-orange-900/50 dark:text-orange-300"
                              : "bg-yellow-200 text-yellow-800 dark:bg-yellow-900/50 dark:text-yellow-300"
                          }`}>
                            Missed {word.times_wrong}×
                          </span>
                        </div>
                      </div>
                      <Button
                        size="icon"
                        variant="ghost"
                        className="rounded-full h-9 w-9 flex-shrink-0"
                        onClick={() => handleAddToFavourites(word)}
                        disabled={isFavLoading}
                        title="Add to favourites"
                      >
                        <Star className="w-4 h-4 text-muted-foreground hover:text-yellow-500" />
                      </Button>
                    </div>
                  </CardContent>
                </Card>
              );
            })}
          </div>
        )}
      </div>
    </div>
  );
}
