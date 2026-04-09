import { Home, Calendar, MessageCircle, CreditCard, User, Receipt } from "lucide-react";
import { motion } from "framer-motion";

type Tab = "home" | "calendar" | "bills" | "chat" | "cards" | "profile";

interface Props {
  active: Tab;
  onChange: (tab: Tab) => void;
}

const tabs: { id: Tab; icon: typeof Home; label: string }[] = [
  { id: "home", icon: Home, label: "Home" },
  { id: "calendar", icon: Calendar, label: "Calendar" },
  { id: "bills", icon: Receipt, label: "Bills" },
  { id: "cards", icon: CreditCard, label: "Cards" },
  { id: "profile", icon: User, label: "Profile" },
];

const BottomNav = ({ active, onChange }: Props) => (
  <>
    {/* Floating AI Chat Orb — FAB (Bottom Right) */}
    <div className="fixed bottom-24 right-5 z-[60]">
      <motion.button
        onClick={() => onChange("chat")}
        whileTap={{ scale: 0.9 }}
        className={`h-14 w-14 rounded-full flex items-center justify-center shadow-[0_0_25px_rgba(204,255,0,0.4)] transition-all ${
          active === "chat"
            ? "bg-[#CCFF00] shadow-[0_0_35px_rgba(204,255,0,0.6)]"
            : "bg-[#CCFF00]"
        }`}
      >
        <motion.div
           // "Start chat" icon animation
          animate={
            active !== "chat"
              ? { scale: [1, 1.05, 1] }
              : {}
          }
          transition={{
            duration: 2,
            repeat: Infinity,
            ease: "easeInOut",
          }}
        >
          <MessageCircle
            size={22}
            className="text-black"
            strokeWidth={2.5}
          />
        </motion.div>
      </motion.button>
      {/* Glow ring — decorative only, no click intercept */}
      <motion.div
        className="absolute inset-0 rounded-full border-2 border-[#CCFF00]/30 pointer-events-none"
        animate={{ scale: [1, 1.3, 1], opacity: [0.5, 0, 0.5] }}
        transition={{ duration: 2.5, repeat: Infinity, ease: "easeInOut" }}
      />
    </div>

    {/* Nav bar */}
    <nav className="fixed bottom-0 left-0 right-0 z-50 bg-[#1A1A1A]/95 backdrop-blur-xl border-t border-white/5 pb-safe">
      <div className="mx-auto flex max-w-lg items-center justify-between px-4 py-2">
        {tabs.map(({ id, icon: Icon, label }) => {
          const isActive = active === id;
          return (
            <button
              key={id}
              onClick={() => onChange(id)}
              className="relative flex flex-col items-center gap-1 py-1.5 transition-colors w-16"
            >
              {isActive && (
                <motion.div
                  layoutId="nav-indicator"
                  className="absolute -top-2 h-0.5 w-6 rounded-full bg-[#CCFF00]"
                  transition={{ type: "spring", stiffness: 400, damping: 30 }}
                />
              )}
              <motion.div
                animate={isActive ? { y: [0, -4, -1, 0] } : {}}
                transition={{ duration: 0.4, ease: [0.34, 1.56, 0.64, 1] }}
              >
                <Icon
                  size={20}
                  strokeWidth={isActive ? 2 : 1.5}
                  className={
                    isActive ? "text-[#CCFF00]" : "text-gray-500"
                  }
                />
              </motion.div>
              <span
                className={`text-[10px] font-medium ${
                  isActive ? "text-[#CCFF00]" : "text-gray-500"
                }`}
              >
                {label}
              </span>
            </button>
          );
        })}
      </div>
    </nav>
  </>
);

export default BottomNav;
