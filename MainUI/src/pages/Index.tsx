import { useState, useEffect } from "react";
import { AnimatePresence, motion } from "framer-motion";
import OnboardingView from "@/components/OnboardingView";
import HomeScreen from "@/components/HomeScreen";
import ChatView from "@/components/ChatView";
import ProfileScreen from "@/components/ProfileScreen";
import CalendarScreen from "@/components/CalendarScreen";
import CardsScreen from "@/components/CardsScreen";
import BillsScreen from "@/components/BillsScreen";
import CreditScoreDetail from "@/components/CreditScoreDetail";
import AlertsView from "@/components/AlertsView";
import BottomNav from "@/components/BottomNav";
import ScamAlertModal from "@/components/ScamAlertModal";

type View = "onboarding" | "home" | "chat" | "profile" | "calendar" | "cards" | "bills" | "credit-score" | "alerts";
type Tab = "home" | "calendar" | "bills" | "chat" | "cards" | "profile";

const Index = () => {
  const [loggedIn, setLoggedIn] = useState(false);
  const [view, setView] = useState<View>("onboarding");
  const [activeTab, setActiveTab] = useState<Tab>("home");
  const [chatAgent, setChatAgent] = useState<string | undefined>();
  const [chatInitialMessage, setChatInitialMessage] = useState<string | undefined>();
  const [scamOpen, setScamOpen] = useState(false);
  const [prevTab, setPrevTab] = useState<Tab>("home");
  const [userId, setUserId] = useState<string>("");
  const [isNewUser, setIsNewUser] = useState(true);

  useEffect(() => {
    // 1. Clean up old keys if present
    localStorage.removeItem("astra_user_id");
    localStorage.removeItem("astra_phone");

    // 2. Check for new standardized keys
    const storedUserId = localStorage.getItem("user_id");
    if (storedUserId) {
      setUserId(storedUserId);
      setLoggedIn(true);
      setView("home");
      setIsNewUser(false);
    }
  }, []);

  const handleLogin = (newUserId: string, name: string) => {
    localStorage.setItem("user_id", newUserId);
    localStorage.setItem("user_name", name);
    
    setUserId(newUserId);
    setLoggedIn(true);
    setView("home");
    setActiveTab("home");
    setIsNewUser(false);
  };

  const handleAgentClick = (agent: string) => {
    setChatAgent(agent);
    setChatInitialMessage(undefined);
    setView("chat");
    setActiveTab("chat");
  };

  const handleNavigate = (target: string) => {
    if (target === "credit-score") {
      setView("credit-score");
    } else if (target === "bills") {
      setView("bills");
    } else if (target === "alerts") {
      setView("alerts");
    }
  };

  const handleTabChange = (tab: Tab) => {
    setPrevTab(activeTab);
    setActiveTab(tab);
    if (tab === "home") setView("home");
    else if (tab === "calendar") setView("calendar");
    else if (tab === "bills") setView("bills");
    else if (tab === "chat") {
      setChatAgent(undefined);
      setChatInitialMessage(undefined);
      setView("chat");
    }
    else if (tab === "cards") setView("cards");
    else if (tab === "profile") setView("profile");
  };

  const handleChatBack = () => {
    setView("home");
    setActiveTab("home");
  };

  const handleCreditScoreBack = () => {
    setView("home");
    setActiveTab("home");
  };

  const handleAskImprove = (score: number) => {
    setChatAgent(undefined);
    setChatInitialMessage(`How can I improve my CIBIL credit score? My current score is ${score}.`);
    setView("chat");
    setActiveTab("chat");
  };

  const handleLogout = () => {
    localStorage.removeItem("user_id");
    localStorage.removeItem("user_name");
    setLoggedIn(false);
    setUserId("");
    setView("onboarding");
    setActiveTab("home");
    setIsNewUser(true);
  };

  // Should we show the bottom nav? Hide it on chat and credit-score detail views
  const showNav = loggedIn && view !== "chat" && view !== "credit-score";

  return (
    <div className="min-h-screen bg-[#111111]">
      <AnimatePresence mode="wait">
        {!loggedIn ? (
          <motion.div key="onboarding" exit={{ opacity: 0 }} transition={{ duration: 0.3 }}>
            <OnboardingView onLogin={handleLogin} />
          </motion.div>
        ) : view === "home" ? (
          <motion.div key="home" initial={{ opacity: 0 }} animate={{ opacity: 1 }} exit={{ opacity: 0 }} transition={{ duration: 0.3 }}>
            <HomeScreen onAgentClick={handleAgentClick} onNavigate={handleNavigate} isEmpty={isNewUser} />
          </motion.div>
        ) : view === "calendar" ? (
          <motion.div key="calendar" initial={{ opacity: 0 }} animate={{ opacity: 1 }} exit={{ opacity: 0 }} transition={{ duration: 0.3 }}>
            <CalendarScreen />
          </motion.div>
        ) : view === "chat" ? (
          <motion.div key="chat" initial={{ opacity: 0, x: 20 }} animate={{ opacity: 1, x: 0 }} exit={{ opacity: 0, x: -20 }} transition={{ duration: 0.25 }}>
            <ChatView initialAgent={chatAgent} initialMessage={chatInitialMessage} onBack={handleChatBack} />
          </motion.div>
        ) : view === "cards" ? (
          <motion.div key="cards" initial={{ opacity: 0 }} animate={{ opacity: 1 }} exit={{ opacity: 0 }} transition={{ duration: 0.3 }}>
            <CardsScreen />
          </motion.div>
        ) : view === "bills" ? (
          <motion.div key="bills" initial={{ opacity: 0 }} animate={{ opacity: 1 }} exit={{ opacity: 0 }} transition={{ duration: 0.3 }}>
            <BillsScreen />
          </motion.div>
        ) : view === "credit-score" ? (
          <motion.div key="credit-score" initial={{ opacity: 0, y: 20 }} animate={{ opacity: 1, y: 0 }} exit={{ opacity: 0 }} transition={{ duration: 0.3 }}>
            <CreditScoreDetail onBack={handleCreditScoreBack} onAskImprove={(s) => handleAskImprove(s)} />
          </motion.div>
        ) : view === "alerts" ? (
          <motion.div key="alerts" initial={{ opacity: 0, x: -20 }} animate={{ opacity: 1, x: 0 }} exit={{ opacity: 0, x: 20 }} transition={{ duration: 0.25 }}>
            <AlertsView onBack={() => setView("home")} />
          </motion.div>
        ) : (
          <motion.div key="profile" initial={{ opacity: 0 }} animate={{ opacity: 1 }} exit={{ opacity: 0 }} transition={{ duration: 0.3 }}>
            <ProfileScreen onLogout={handleLogout} />
          </motion.div>
        )}
      </AnimatePresence>

      {showNav && <BottomNav active={activeTab} onChange={handleTabChange} />}

      <ScamAlertModal open={scamOpen} onClose={() => setScamOpen(false)} />
    </div>
  );
};

export default Index;
