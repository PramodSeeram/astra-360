import { Home, MessageSquare, Bell, User } from "lucide-react";
import { motion } from "framer-motion";

type Tab = "home" | "chat" | "alerts" | "profile";

interface Props {
  active: Tab;
  onChange: (tab: Tab) => void;
}

const tabs: { id: Tab; icon: typeof Home; label: string }[] = [
  { id: "home", icon: Home, label: "Home" },
  { id: "chat", icon: MessageSquare, label: "Chat" },
  { id: "alerts", icon: Bell, label: "Alerts" },
  { id: "profile", icon: User, label: "Profile" },
];

const BottomNav = ({ active, onChange }: Props) => (
  <nav className="fixed bottom-0 left-0 right-0 z-50 glass border-t border-border/30">
    <div className="mx-auto flex max-w-lg items-center justify-around px-2 py-2">
      {tabs.map(({ id, icon: Icon, label }) => {
        const isActive = active === id;
        return (
          <button
            key={id}
            onClick={() => onChange(id)}
            className="relative flex flex-col items-center gap-0.5 px-4 py-1.5 transition-colors"
          >
            {isActive && (
              <motion.div
                layoutId="nav-indicator"
                className="absolute -top-2 h-0.5 w-6 rounded-full bg-primary"
                transition={{ type: "spring", stiffness: 400, damping: 30 }}
              />
            )}
            <motion.div
              animate={isActive ? { y: [0, -5, -2, 0] } : {}}
              transition={{ duration: 0.4, ease: [0.34, 1.56, 0.64, 1] }}
            >
              <Icon
                size={20}
                className={isActive ? "text-primary" : "text-muted-foreground"}
              />
            </motion.div>
            <span
              className={`text-[10px] font-medium ${
                isActive ? "text-primary" : "text-muted-foreground"
              }`}
            >
              {label}
            </span>
          </button>
        );
      })}
    </div>
  </nav>
);

export default BottomNav;
