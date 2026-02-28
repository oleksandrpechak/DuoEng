import { useMemo, useState } from "react";
import { useNavigate } from "react-router-dom";
import { Loader2 } from "lucide-react";
import { toast } from "sonner";

import FilterButtons from "@/components/word-levels/FilterButtons";
import WordLevelItem from "@/components/word-levels/WordLevelItem";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Label } from "@/components/ui/label";
import { Textarea } from "@/components/ui/textarea";
import { classifyWordLevels } from "@/lib/wordLevelsApi";

function parseWords(rawText) {
  return rawText
    .split(/[\n,]+/g)
    .map((word) => word.trim())
    .filter(Boolean);
}

export default function WordLevelsPage() {
  const navigate = useNavigate();
  const [wordsInput, setWordsInput] = useState("");
  const [results, setResults] = useState([]);
  const [filter, setFilter] = useState("ALL");
  const [isLoading, setIsLoading] = useState(false);

  const filteredResults = useMemo(() => {
    if (filter === "ALL") {
      return results;
    }
    return results.filter((item) => item.level === filter);
  }, [filter, results]);

  const handleSubmit = async (event) => {
    event.preventDefault();
    const words = parseWords(wordsInput);
    if (words.length === 0) {
      toast.error("Please enter at least one word.");
      return;
    }

    setIsLoading(true);
    try {
      const response = await classifyWordLevels(words);
      setResults(response);
      setFilter("ALL");
    } catch (error) {
      const detail = error?.response?.data?.detail || "Failed to classify word levels.";
      toast.error(detail);
    }
    setIsLoading(false);
  };

  return (
    <div className="min-h-screen bg-background p-4">
      <div className="mx-auto flex w-full max-w-2xl flex-col gap-4">
        <div className="flex items-center justify-between">
          <h1 className="font-heading text-2xl font-bold text-foreground">Word Levels</h1>
          <Button variant="outline" onClick={() => navigate("/")}>
            Back
          </Button>
        </div>

        <Card className="rounded-2xl border border-border/80">
          <CardHeader>
            <CardTitle className="text-lg">Classify CEFR Levels</CardTitle>
            <CardDescription>Submit English words and get CEFR levels from Gemini.</CardDescription>
          </CardHeader>
          <CardContent>
            <form className="space-y-3" onSubmit={handleSubmit}>
              <div className="space-y-2">
                <Label htmlFor="wordsInput">Words (comma or new line separated)</Label>
                <Textarea
                  id="wordsInput"
                  value={wordsInput}
                  onChange={(event) => setWordsInput(event.target.value)}
                  className="min-h-32 resize-y"
                  placeholder={"apple\nanalyze\nmeticulous"}
                />
              </div>
              <Button type="submit" className="w-full rounded-full" disabled={isLoading}>
                {isLoading ? <Loader2 className="h-4 w-4 animate-spin" /> : "Get CEFR Levels"}
              </Button>
            </form>
          </CardContent>
        </Card>

        <Card className="rounded-2xl border border-border/80">
          <CardHeader className="space-y-3">
            <CardTitle className="text-lg">Results</CardTitle>
            <FilterButtons activeFilter={filter} onFilterChange={setFilter} disabled={results.length === 0} />
          </CardHeader>
          <CardContent>
            {filteredResults.length === 0 ? (
              <p className="text-sm text-muted-foreground">
                {results.length === 0
                  ? "No classified words yet."
                  : "No words match the selected level filter."}
              </p>
            ) : (
              <ul className="space-y-2" aria-live="polite">
                {filteredResults.map((item, index) => (
                  <WordLevelItem key={`${item.word}-${item.level}-${index}`} item={item} />
                ))}
              </ul>
            )}
          </CardContent>
        </Card>
      </div>
    </div>
  );
}

