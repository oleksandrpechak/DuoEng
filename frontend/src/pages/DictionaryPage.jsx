import { useState, useEffect, useCallback, useRef } from "react";
import { useNavigate } from "react-router-dom";
import { Input } from "@/components/ui/input";
import { Button } from "@/components/ui/button";
import { Skeleton } from "@/components/ui/skeleton";
import {
  Search,
  Star,
  BookOpen,
  ChevronDown,
  ChevronUp,
  Loader2,
  Filter,
} from "lucide-react";
import { toast } from "sonner";
import api from "@/lib/api";
import CefrBadge from "@/components/CefrBadge";

const POS_OPTIONS = ["noun", "verb", "adjective", "adverb"];
const CEFR_LEVELS = ["A1", "A2", "B1", "B2", "C1", "C2"];
const PAGE_SIZE = 20;

export default function DictionaryPage() {
  const navigate = useNavigate();
  const [query, setQuery] = useState("");
  const [results, setResults] = useState([]);
  const [totalHint, setTotalHint] = useState(0);
  const [offset, setOffset] = useState(0);
  const [hasMore, setHasMore] = useState(false);
  const [isLoading, setIsLoading] = useState(false);
  const [isLoadingMore, setIsLoadingMore] = useState(false);
  const [expandedIdx, setExpandedIdx] = useState(null);

  // Filters
  const [levelFilter, setLevelFilter] = useState([]);
  const [posFilter, setPosFilter] = useState([]);
  const [showFilters, setShowFilters] = useState(false);

  // Favourites
  const [favouriteIds, setFavouriteIds] = useState(new Set());
  const [favLoading, setFavLoading] = useState(new Set());

  const debounceRef = useRef(null);
  const accessToken = sessionStorage.getItem("accessToken");
  const userId = sessionStorage.getItem("userId");

  useEffect(() => {
    document.title = "Dictionary — DuoEng";
    if (!accessToken || !userId) navigate("/", { replace: true });
  }, [accessToken, userId, navigate]);

  // Load favourites on mount
  useEffect(() => {
    if (!accessToken) return;
    api
      .get("/players/me/favourites")
      .then((res) => {
        const ids = new Set((res.data || []).map((f) => f.word_id));
        setFavouriteIds(ids);
      })
      .catch(() => {});
  }, [accessToken]);

  const doSearch = useCallback(
    async (q, levels, newSearch = true) => {
      if (!q.trim()) {
        if (newSearch) {
          setResults([]);
          setTotalHint(0);
          setHasMore(false);
        }
        return;
      }

      if (newSearch) {
        setIsLoading(true);
        setOffset(0);
      } else {
        setIsLoadingMore(true);
      }

      try {
        const params = {
          q: q.trim().toLowerCase(),
          limit: PAGE_SIZE,
          offset: newSearch ? 0 : offset,
        };
        if (levels && levels.length === 1) {
          params.level = levels[0];
        }
        const res = await api.get("/dictionary/search", { params });
        const data = res.data || [];

        if (newSearch) {
          setResults(data);
          setOffset(data.length);
          setTotalHint(data.length >= PAGE_SIZE ? data.length + 1 : data.length);
        } else {
          setResults((prev) => [...prev, ...data]);
          setOffset((prev) => prev + data.length);
        }
        setHasMore(data.length >= PAGE_SIZE);
      } catch (err) {
        toast.error(err.response?.data?.detail || "Search failed");
      }

      setIsLoading(false);
      setIsLoadingMore(false);
    },
    [offset],
  );

  // Debounced search on query or filter change
  useEffect(() => {
    if (debounceRef.current) clearTimeout(debounceRef.current);
    debounceRef.current = setTimeout(() => {
      if (query.trim()) doSearch(query, levelFilter, true);
    }, 400);
    return () => clearTimeout(debounceRef.current);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [query, levelFilter]);

  const handleLoadMore = () => {
    doSearch(query, levelFilter, false);
  };

  const toggleLevel = (lvl) => {
    setLevelFilter((prev) =>
      prev.includes(lvl) ? prev.filter((l) => l !== lvl) : [...prev, lvl],
    );
  };

  const togglePos = (pos) => {
    setPosFilter((prev) =>
      prev.includes(pos) ? prev.filter((p) => p !== pos) : [...prev, pos],
    );
  };

  const handleToggleFavourite = async (entry) => {
    const wordId = entry.en_word
      .toLowerCase()
      .replace(/ /g, "_")
      .replace(/'/g, "")
      .slice(0, 64);

    setFavLoading((prev) => new Set(prev).add(wordId));
    try {
      if (favouriteIds.has(wordId)) {
        await api.delete(`/players/me/favourites/${wordId}`);
        setFavouriteIds((prev) => {
          const next = new Set(prev);
          next.delete(wordId);
          return next;
        });
        toast.success("Removed from favourites");
      } else {
        await api.post("/players/me/favourites", { word_id: wordId });
        setFavouriteIds((prev) => new Set(prev).add(wordId));
        toast.success("Added to favourites ⭐");
      }
    } catch (err) {
      toast.error(err.response?.data?.detail || "Failed to update favourite");
    }
    setFavLoading((prev) => {
      const next = new Set(prev);
      next.delete(wordId);
      return next;
    });
  };

  // Client-side POS filter
  const filtered = posFilter.length
    ? results.filter((r) =>
        posFilter.some(
          (p) => (r.part_of_speech || "").toLowerCase() === p.toLowerCase(),
        ),
      )
    : results;

  return (
    <div className="min-h-screen bg-background">
      <div className="max-w-6xl mx-auto px-4 py-6">
        {/* Header */}
        <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-4 mb-6">
          <div className="flex items-center gap-3">
            <BookOpen className="w-7 h-7 text-primary" />
            <h1 className="font-heading text-2xl sm:text-3xl font-bold">Dictionary</h1>
          </div>
          <div className="relative w-full sm:w-80">
            <Search className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-muted-foreground" />
            <Input
              placeholder="Search Ukrainian or English…"
              value={query}
              onChange={(e) => setQuery(e.target.value)}
              className="pl-10 rounded-full h-11"
            />
          </div>
        </div>

        <div className="flex flex-col lg:flex-row gap-6">
          {/* ── Filters (desktop sidebar / mobile toggle) ── */}
          <div className="lg:w-56 flex-shrink-0">
            {/* Mobile filter toggle */}
            <button
              className="lg:hidden flex items-center gap-2 text-sm font-medium text-muted-foreground mb-3"
              onClick={() => setShowFilters(!showFilters)}
            >
              <Filter className="w-4 h-4" />
              Filters
              {showFilters ? <ChevronUp className="w-4 h-4" /> : <ChevronDown className="w-4 h-4" />}
            </button>

            <div className={`space-y-5 ${showFilters ? "block" : "hidden lg:block"}`}>
              {/* CEFR Level */}
              <div>
                <p className="text-xs font-semibold text-muted-foreground uppercase tracking-wider mb-2">
                  CEFR Level
                </p>
                <div className="flex flex-wrap gap-1.5">
                  {CEFR_LEVELS.map((lvl) => {
                    const active = levelFilter.includes(lvl);
                    return (
                      <button
                        key={lvl}
                        onClick={() => toggleLevel(lvl)}
                        className={`px-2.5 py-1 rounded-full text-xs font-medium border transition-all ${
                          active
                            ? "bg-primary text-primary-foreground border-primary"
                            : "bg-muted text-muted-foreground border-border hover:border-primary/40"
                        }`}
                      >
                        {lvl}
                      </button>
                    );
                  })}
                </div>
              </div>

              {/* Part of speech */}
              <div>
                <p className="text-xs font-semibold text-muted-foreground uppercase tracking-wider mb-2">
                  Part of Speech
                </p>
                <div className="flex flex-wrap gap-1.5">
                  {POS_OPTIONS.map((pos) => {
                    const active = posFilter.includes(pos);
                    return (
                      <button
                        key={pos}
                        onClick={() => togglePos(pos)}
                        className={`px-2.5 py-1 rounded-full text-xs font-medium border capitalize transition-all ${
                          active
                            ? "bg-primary text-primary-foreground border-primary"
                            : "bg-muted text-muted-foreground border-border hover:border-primary/40"
                        }`}
                      >
                        {pos}
                      </button>
                    );
                  })}
                </div>
              </div>

              {(levelFilter.length > 0 || posFilter.length > 0) && (
                <button
                  className="text-xs text-primary hover:underline"
                  onClick={() => {
                    setLevelFilter([]);
                    setPosFilter([]);
                  }}
                >
                  Clear all filters
                </button>
              )}
            </div>
          </div>

          {/* ── Results ── */}
          <div className="flex-1 min-w-0">
            {/* Results count */}
            {!isLoading && query.trim() && (
              <p className="text-sm text-muted-foreground mb-3">
                {filtered.length === 0
                  ? `No results for "${query}"`
                  : `Showing ${filtered.length}${hasMore ? "+" : ""} result${filtered.length !== 1 ? "s" : ""}`}
              </p>
            )}

            {/* Loading skeleton */}
            {isLoading && (
              <div className="space-y-3">
                {Array.from({ length: 5 }).map((_, i) => (
                  <div
                    key={i}
                    className="rounded-2xl border border-border bg-card p-4 space-y-2"
                  >
                    <Skeleton className="h-5 w-3/4" />
                    <Skeleton className="h-4 w-1/3" />
                  </div>
                ))}
              </div>
            )}

            {/* Results list */}
            {!isLoading && (
              <div className="space-y-3">
                {filtered.map((entry, idx) => {
                  const wordId = entry.en_word
                    .toLowerCase()
                    .replace(/ /g, "_")
                    .replace(/'/g, "")
                    .slice(0, 64);
                  const isFav = favouriteIds.has(wordId);
                  const isFavLoading = favLoading.has(wordId);
                  const isExpanded = expandedIdx === idx;
                  const hasMeta = entry.definition || entry.example;

                  return (
                    <div
                      key={`${entry.ua_word}-${entry.en_word}-${idx}`}
                      className="rounded-2xl border border-border bg-card p-4 transition-all hover:shadow-soft"
                    >
                      <div className="flex items-start justify-between gap-3">
                        <div className="flex-1 min-w-0">
                          <p className="text-base font-medium">
                            <span className="text-muted-foreground mr-1">🇺🇦</span>
                            {entry.ua_word}
                            <span className="mx-2 text-muted-foreground">→</span>
                            <span className="text-muted-foreground mr-1">🇬🇧</span>
                            {entry.en_word}
                          </p>
                          <div className="flex flex-wrap items-center gap-2 mt-1.5">
                            {entry.part_of_speech && (
                              <span className="px-2 py-0.5 rounded-full text-[11px] font-medium bg-muted text-muted-foreground">
                                {entry.part_of_speech}
                              </span>
                            )}
                            {entry.level && (
                              <CefrBadge level={entry.level} short className="text-[11px] px-2 py-0" />
                            )}
                            {entry.source === "ai_generated" && (
                              <span className="px-2 py-0.5 rounded-full text-[11px] font-medium bg-purple-100 text-purple-800 dark:bg-purple-900/40 dark:text-purple-300">
                                AI suggestion
                              </span>
                            )}
                          </div>
                        </div>
                        <div className="flex items-center gap-1 flex-shrink-0">
                          {hasMeta && (
                            <button
                              onClick={() => setExpandedIdx(isExpanded ? null : idx)}
                              className="p-1.5 rounded-full hover:bg-muted transition-colors"
                              title={isExpanded ? "Collapse" : "Show details"}
                            >
                              {isExpanded ? (
                                <ChevronUp className="w-4 h-4 text-muted-foreground" />
                              ) : (
                                <ChevronDown className="w-4 h-4 text-muted-foreground" />
                              )}
                            </button>
                          )}
                          <button
                            onClick={() => handleToggleFavourite(entry)}
                            disabled={isFavLoading}
                            className="p-1.5 rounded-full hover:bg-muted transition-colors disabled:opacity-50"
                            title={isFav ? "Remove from favourites" : "Save to favourites"}
                          >
                            <Star
                              className={`w-4 h-4 ${
                                isFav
                                  ? "text-yellow-500 fill-yellow-500"
                                  : "text-muted-foreground"
                              }`}
                            />
                          </button>
                        </div>
                      </div>

                      {/* Expandable definition/example */}
                      {isExpanded && hasMeta && (
                        <div className="mt-3 pt-3 border-t border-border space-y-1 animate-fade-in-up">
                          {entry.definition && (
                            <p className="text-sm text-muted-foreground">
                              <span className="font-medium text-foreground">Definition:</span>{" "}
                              {entry.definition}
                            </p>
                          )}
                          {entry.example && (
                            <p className="text-sm text-muted-foreground italic">
                              "{entry.example}"
                            </p>
                          )}
                        </div>
                      )}
                    </div>
                  );
                })}
              </div>
            )}

            {/* Empty state */}
            {!isLoading && query.trim() && filtered.length === 0 && (
              <div className="text-center py-12">
                <Search className="w-12 h-12 mx-auto text-muted-foreground/40 mb-3" />
                <p className="text-muted-foreground">
                  No results for "<span className="font-medium text-foreground">{query}</span>"
                </p>
                <p className="text-sm text-muted-foreground mt-1">
                  Try a different spelling or search in the other language
                </p>
              </div>
            )}

            {/* Empty state — no query */}
            {!isLoading && !query.trim() && results.length === 0 && (
              <div className="text-center py-16">
                <BookOpen className="w-14 h-14 mx-auto text-muted-foreground/30 mb-4" />
                <p className="text-lg font-medium text-muted-foreground">
                  Search the Ukrainian-English dictionary
                </p>
                <p className="text-sm text-muted-foreground mt-1">
                  Type a word in Ukrainian or English above
                </p>
              </div>
            )}

            {/* Load more */}
            {!isLoading && hasMore && filtered.length > 0 && (
              <div className="flex justify-center mt-6">
                <Button
                  variant="outline"
                  className="rounded-full"
                  onClick={handleLoadMore}
                  disabled={isLoadingMore}
                >
                  {isLoadingMore ? (
                    <Loader2 className="w-4 h-4 mr-2 animate-spin" />
                  ) : null}
                  Load more
                </Button>
              </div>
            )}
          </div>
        </div>
      </div>
    </div>
  );
}
