import "@/App.css";
import { BrowserRouter, Routes, Route } from "react-router-dom";
import { Toaster } from "@/components/ui/sonner";
import { ThemeProvider } from "@/components/theme-provider";
import ThemeToggle from "@/components/theme-toggle";
import LandingPage from "@/pages/LandingPage";
import LobbyPage from "@/pages/LobbyPage";
import GamePage from "@/pages/GamePage";
import EndPage from "@/pages/EndPage";
import WordLevelsPage from "@/pages/WordLevelsPage";

function App() {
  return (
    <ThemeProvider attribute="class" defaultTheme="system" enableSystem disableTransitionOnChange>
      <div className="App min-h-screen bg-background">
        <BrowserRouter>
          <div className="fixed right-4 top-4 z-50">
            <ThemeToggle />
          </div>
          <Routes>
            <Route path="/" element={<LandingPage />} />
            <Route path="/word-levels" element={<WordLevelsPage />} />
            <Route path="/lobby/:code" element={<LobbyPage />} />
            <Route path="/game/:code" element={<GamePage />} />
            <Route path="/end/:code" element={<EndPage />} />
          </Routes>
        </BrowserRouter>
        <Toaster position="top-center" richColors />
      </div>
    </ThemeProvider>
  );
}

export default App;
