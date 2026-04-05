import { useState } from "react";
import { AnimatePresence, motion } from "framer-motion";
import OnboardingView from "@/UI/OnboardingView";
import DashboardView from "@/UI/DashboardView";
import ChatView from "@/UI/ChatView";
import AlertsView from "@/UI/AlertsView";
import ProfileView from "@/UI/ProfileView";
import BottomNav from "@/UI/BottomNav";
import ScamAlertModal from "@/UI/ScamAlertModal";

type View = "onboarding" | "dashboard" | "chat" | "alerts" | "profile";
type Tab = "home" | "chat" | "alerts" | "profile";

const Index = () => {
  const [loggedIn, setLoggedIn] = useState(false);
  const [view, setView] = useState<View>("onboarding");
  const [activeTab, setActiveTab] = useState<Tab>("home");
  const [chatAgent, setChatAgent] = useState<string | undefined>();
  const [scamOpen, setScamOpen] = useState(false);

  const handleLogin = () => {
    setLoggedIn(true);
    setView("dashboard");
    setActiveTab("home");
  };

  const handleAgentClick = (agent: string) => {
    setChatAgent(agent);
    setView("chat");
    setActiveTab("chat");
  };

  const handleTabChange = (tab: Tab) => {
    setActiveTab(tab);
    if (tab === "home") setView("dashboard");
    else if (tab === "chat") {
      setChatAgent(undefined);
      setView("chat");
    } else setView(tab);
  };

  const handleChatBack = () => {
    setView("dashboard");
    setActiveTab("home");
  };

  const handleLogout = () => {
    setLoggedIn(false);
    setView("onboarding");
    setActiveTab("home");
  };

  return (
    <div className="min-h-screen bg-background">
      <AnimatePresence mode="wait">
        {!loggedIn ? (
          <motion.div key="onboarding" exit={{ opacity: 0 }} transition={{ duration: 0.3 }}>
            <OnboardingView onComplete={handleLogin} />
          </motion.div>
        ) : view === "dashboard" ? (
          <motion.div
            key="dashboard"
            initial={{ opacity: 0 }}
            animate={{ opacity: 1 }}
            exit={{ opacity: 0 }}
            transition={{ duration: 0.3 }}
          >
            <DashboardView
              onAgentClick={handleAgentClick}
              onTriggerScam={() => setScamOpen(true)}
            />
          </motion.div>
        ) : view === "chat" ? (
          <motion.div
            key="chat"
            initial={{ opacity: 0, x: 20 }}
            animate={{ opacity: 1, x: 0 }}
            exit={{ opacity: 0, x: -20 }}
            transition={{ duration: 0.25 }}
          >
            <ChatView initialAgent={chatAgent} onBack={handleChatBack} />
          </motion.div>
        ) : view === "alerts" ? (
          <motion.div
            key="alerts"
            initial={{ opacity: 0 }}
            animate={{ opacity: 1 }}
            exit={{ opacity: 0 }}
            transition={{ duration: 0.3 }}
          >
            <AlertsView />
          </motion.div>
        ) : (
          <motion.div
            key="profile"
            initial={{ opacity: 0 }}
            animate={{ opacity: 1 }}
            exit={{ opacity: 0 }}
            transition={{ duration: 0.3 }}
          >
            <ProfileView onLogout={handleLogout} />
          </motion.div>
        )}
      </AnimatePresence>

      {loggedIn && <BottomNav active={activeTab} onChange={handleTabChange} />}

      <ScamAlertModal open={scamOpen} onClose={() => setScamOpen(false)} />
    </div>
  );
};

export default Index;
