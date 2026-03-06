import { useState, useEffect } from "react";
import { useNavigate } from "react-router-dom";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Card, CardContent } from "@/components/ui/card";
import { Label } from "@/components/ui/label";
import {
  ArrowLeft,
  Loader2,
  Plus,
  Trash2,
  BookOpen,
  X,
} from "lucide-react";
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

export default function MyWordsPage() {
  const navigate = useNavigate();
  const [words, setWords] = useState([]);
  const [isLoading, setIsLoading] = useState(true);
  const [showAddModal, setShowAddModal] = useState(false);
  const [uaInput, setUaInput] = useState("");
  const [enInput, setEnInput] = useState("");
  const [isAdding, setIsAdding] = useState(false);

  const accessToken = localStorage.getItem("accessToken");
  const userId = localStorage.getItem("userId");

  useEffect(() => {
    if (!accessToken || !userId) {
      navigate("/", { replace: true });
      return;
    }
    loadWords();
  }, [accessToken, userId]); // eslint-disable-line react-hooks/exhaustive-deps

  const loadWords = async () => {
    setIsLoading(true);
    try {
      const response = await api.get("/players/me/words");
      setWords(response.data || []);
    } catch (error) {
      toast.error("Failed to load custom words");
    }
    setIsLoading(false);
  };

  const handleAdd = async () => {
    const ua = uaInput.trim();
    const en = enInput.trim();

    if (!ua || !en) {
      toast.error("Both fields are required");
      return;
    }
    if (ua.includes(" ") && !ua.startsWith("не ")) {
      toast.error("Ukrainian word must be a single word");
      return;
    }
    if (en.includes(" ")) {
      toast.error("English word must be a single word");
      return;
    }

    setIsAdding(true);
    try {
      const response = await api.post("/players/me/words", { ua_word: ua, en_word: en });
      setWords((prev) => [response.data, ...prev]);
      setUaInput("");
      setEnInput("");
      setShowAddModal(false);
      toast.success("Word added!");
    } catch (error) {
      const detail = error.response?.data?.detail || "Failed to add word";
      toast.error(detail);
    }
    setIsAdding(false);
  };

  const handleDelete = async (wordId) => {
    try {
      await api.delete(`/players/me/words/${wordId}`);
      setWords((prev) => prev.filter((w) => w.id !== wordId));
      toast.success("Word deleted");
    } catch (error) {
      toast.error("Failed to delete word");
    }
  };

  if (!accessToken || !userId) return null;

  return (
    <div className="min-h-screen bg-background flex flex-col items-center p-4 pt-8">
      <div className="w-full max-w-md lg:max-w-2xl space-y-6 animate-fade-in-up">
        {/* Header */}
        <div className="flex items-center justify-between">
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
              <h1 className="font-heading text-2xl font-bold">➕ My Words</h1>
              <p className="text-sm text-muted-foreground">
                Add your own vocabulary pairs
              </p>
            </div>
          </div>
          <Button
            className="rounded-full"
            onClick={() => setShowAddModal(true)}
          >
            <Plus className="w-4 h-4 mr-2" />
            Add Word
          </Button>
        </div>

        {/* Add Word Modal */}
        {showAddModal && (
          <Card className="rounded-2xl border-2 border-primary/30 shadow-soft animate-fade-in-up">
            <CardContent className="p-5 space-y-4">
              <div className="flex items-center justify-between">
                <h3 className="font-heading text-lg font-bold">Add New Word</h3>
                <Button
                  size="icon"
                  variant="ghost"
                  className="rounded-full h-8 w-8"
                  onClick={() => setShowAddModal(false)}
                >
                  <X className="w-4 h-4" />
                </Button>
              </div>
              <div className="space-y-3">
                <div>
                  <Label htmlFor="ua-word" className="text-sm font-medium">
                    🇺🇦 Ukrainian Word
                  </Label>
                  <Input
                    id="ua-word"
                    placeholder="e.g. кіт"
                    value={uaInput}
                    onChange={(e) => setUaInput(e.target.value)}
                    onKeyDown={(e) => e.key === "Enter" && handleAdd()}
                    className="rounded-full h-11 mt-1"
                    maxLength={100}
                    autoFocus
                  />
                </div>
                <div>
                  <Label htmlFor="en-word" className="text-sm font-medium">
                    🇬🇧 English Translation
                  </Label>
                  <Input
                    id="en-word"
                    placeholder="e.g. cat"
                    value={enInput}
                    onChange={(e) => setEnInput(e.target.value)}
                    onKeyDown={(e) => e.key === "Enter" && handleAdd()}
                    className="rounded-full h-11 mt-1"
                    maxLength={100}
                  />
                </div>
                <Button
                  className="w-full rounded-full h-11"
                  onClick={handleAdd}
                  disabled={isAdding || !uaInput.trim() || !enInput.trim()}
                >
                  {isAdding ? (
                    <Loader2 className="w-4 h-4 animate-spin mr-2" />
                  ) : (
                    <Plus className="w-4 h-4 mr-2" />
                  )}
                  Add Word
                </Button>
              </div>
            </CardContent>
          </Card>
        )}

        {/* Words Table */}
        {isLoading ? (
          <div className="flex justify-center py-12">
            <Loader2 className="w-8 h-8 animate-spin text-primary" />
          </div>
        ) : words.length === 0 ? (
          <Card className="rounded-2xl border-0 shadow-soft">
            <CardContent className="p-8 text-center">
              <BookOpen className="w-12 h-12 mx-auto text-muted-foreground mb-4" />
              <p className="text-lg font-medium mb-2">No custom words yet</p>
              <p className="text-sm text-muted-foreground">
                Add your own Ukrainian-English word pairs to practice!
              </p>
              <Button
                className="mt-4 rounded-full"
                onClick={() => setShowAddModal(true)}
              >
                <Plus className="w-4 h-4 mr-2" />
                Add Your First Word
              </Button>
            </CardContent>
          </Card>
        ) : (
          <div className="space-y-2">
            {/* Table header for desktop */}
            <div className="hidden lg:grid grid-cols-5 gap-4 px-4 py-2 text-xs font-medium text-muted-foreground uppercase tracking-wider">
              <span>Ukrainian</span>
              <span>English</span>
              <span>Level</span>
              <span>Status</span>
              <span className="text-right">Actions</span>
            </div>

            {words.map((word) => (
              <Card key={word.id} className="rounded-2xl border shadow-soft">
                <CardContent className="p-4">
                  <div className="flex items-center justify-between lg:grid lg:grid-cols-5 lg:gap-4">
                    <div className="flex items-center gap-2 min-w-0 lg:col-span-1">
                      <span className="font-medium truncate">🇺🇦 {word.ua_word}</span>
                    </div>
                    <div className="hidden lg:flex items-center gap-2 lg:col-span-1">
                      <span className="truncate">🇬🇧 {word.en_word}</span>
                    </div>
                    <span className="lg:hidden text-muted-foreground mx-1">→</span>
                    <span className="lg:hidden truncate">{word.en_word}</span>
                    <div className="hidden lg:flex items-center lg:col-span-1">
                      <CefrBadge level={word.level} short className="text-xs" />
                    </div>
                    <div className="hidden lg:flex items-center lg:col-span-1">
                      <span className={`text-xs px-2 py-0.5 rounded-full ${
                        word.approved
                          ? "bg-green-100 text-green-700 dark:bg-green-900/30 dark:text-green-400"
                          : "bg-yellow-100 text-yellow-700 dark:bg-yellow-900/30 dark:text-yellow-400"
                      }`}>
                        {word.approved ? "Active" : "Pending"}
                      </span>
                    </div>
                    <div className="flex items-center gap-2 flex-shrink-0 ml-2 lg:justify-end lg:col-span-1">
                      <CefrBadge level={word.level} short className="text-[10px] px-1.5 py-0 lg:hidden" />
                      <AlertDialog>
                        <AlertDialogTrigger asChild>
                          <Button
                            size="icon"
                            variant="ghost"
                            className="rounded-full h-8 w-8 text-destructive hover:bg-destructive/10"
                            title="Delete word"
                          >
                            <Trash2 className="w-4 h-4" />
                          </Button>
                        </AlertDialogTrigger>
                        <AlertDialogContent className="rounded-2xl max-w-sm">
                          <AlertDialogHeader>
                            <AlertDialogTitle>Delete word?</AlertDialogTitle>
                            <AlertDialogDescription>
                              Remove "{word.ua_word} → {word.en_word}" from your custom words?
                            </AlertDialogDescription>
                          </AlertDialogHeader>
                          <AlertDialogFooter>
                            <AlertDialogCancel className="rounded-full">Cancel</AlertDialogCancel>
                            <AlertDialogAction
                              className="rounded-full bg-destructive text-destructive-foreground"
                              onClick={() => handleDelete(word.id)}
                            >
                              Delete
                            </AlertDialogAction>
                          </AlertDialogFooter>
                        </AlertDialogContent>
                      </AlertDialog>
                    </div>
                  </div>
                </CardContent>
              </Card>
            ))}
          </div>
        )}
      </div>
    </div>
  );
}
