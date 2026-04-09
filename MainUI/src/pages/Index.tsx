import { useState } from "react";
import { AnimatePresence, motion } from "framer-motion";
import OnboardingView from "@/components/OnboardingView";
import HomeScreen from "@/components/HomeScreen";
import ChatView from "@/components/ChatView";
import ProfileScreen from "@/components/ProfileScreen";
import CalendarScreen from "@/components/CalendarScreen";
import CardsScreen from "@/components/CardsScreen";
import BillsScreen from "@/components/BillsScreen";
import CreditScoreDetail from "@/components/CreditScoreDetail";
import BottomNav from "@/components/BottomNav";
import ScamAlertModal from "@/components/ScamAlertModal";

type View = "onboarding" | "home" | "chat" | "profile" | "calendar" | "cards" | "bills" | "credit-score";
type Tab = "home" | "calendar" | "chat" | "cards" | "profile";

const Index = () => {
  const [loggedIn, setLoggedIn] = useState(false);
  const [view, setView] = useState<View>("onboarding");
  const [activeTab, setActiveTab] = useState<Tab>("home");
  const [chatAgent, setChatAgent] = useState<string | undefined>();
  const [chatInitialMessage, setChatInitialMessage] = useState<string | undefined>();
  const [scamOpen, setScamOpen] = useState(false);
  const [prevTab, setPrevTab] = useState<Tab>("home");

  const handleLogin = () => {
    setLoggedIn(true);
    setView("home");
    setActiveTab("home");
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

  const handleAskImprove = () => {
    setChatAgent(undefined);
    setChatInitialMessage("How can I improve my CIBIL credit score? My current score is 780.");
    setView("chat");
    setActiveTab("chat");
  };

  const handleLogout = () => {
    setLoggedIn(false);
    setView("onboarding");
    setActiveTab("home");
  };

  // Should we show the bottom nav? Hide it on chat and credit-score detail views
  const showNav = loggedIn && view !== "chat" && view !== "credit-score";

  return (
    <div className="min-h-screen bg-[#111111]">
      <AnimatePresence mode="wait">
        {!loggedIn ? (
          <motion.div key="onboarding" exit={{ opacity: 0 }} transition={{ duration: 0.3 }}>
            <OnboardingView onComplete={handleLogin} />
          </motion.div>
        ) : view === "home" ? (
          <motion.div key="home" initial={{ opacity: 0 }} animate={{ opacity: 1 }} exit={{ opacity: 0 }} transition={{ duration: 0.3 }}>
            <HomeScreen onAgentClick={handleAgentClick} onNavigate={handleNavigate} />
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
            <CreditScoreDetail onBack={handleCreditScoreBack} onAskImprove={handleAskImprove} />
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
