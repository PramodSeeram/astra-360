import { useState, useEffect } from "react";
import { motion, AnimatePresence } from "framer-motion";
import { CreditCard, ChevronRight, Plus, Eye, EyeOff, Wifi, Loader2 } from "lucide-react";
import { api, CardsData, CardItem } from "@/lib/api";

const CardsScreen = () => {
  const [data, setData] = useState<CardsData | null>(null);
  const [loading, setLoading] = useState(true);
  const [activeIndex, setActiveIndex] = useState(0);
  const [showNumber, setShowNumber] = useState(false);

  useEffect(() => {
    const userId = localStorage.getItem("user_id");
    if (!userId) {
      setLoading(false);
      return;
    }

    api.getCards(userId)
      .then((res) => setData(res))
      .catch((err) => console.error("[CardsScreen] API error:", err))
      .finally(() => setLoading(false));
  }, []);

  if (loading) {
    return (
      <div className="min-h-screen flex items-center justify-center">
        <Loader2 size={32} className="text-[#CCFF00] animate-spin" />
      </div>
    );
  }

  const hasData = data?.has_data ?? false;
  const cards = data?.cards ?? [];
  const transactions = data?.transactions ?? [];
  const emptyMessage = data?.message || "No cards available. Link your bank accounts to see your cards here.";

  // Empty state
  if (!hasData || cards.length === 0) {
    return (
      <div className="min-h-screen pb-28 pt-6 px-4 max-w-lg mx-auto">
        {/* Header */}
        <motion.div
          initial={{ opacity: 0, y: 10 }}
          animate={{ opacity: 1, y: 0 }}
          className="flex items-center justify-between mb-6"
        >
          <div>
            <h1 className="font-display text-2xl font-bold text-white">Your Cards</h1>
            <p className="text-sm text-gray-400">0 cards linked</p>
          </div>
          <button className="flex items-center gap-1.5 rounded-full border border-[#CCFF00]/30 bg-[#CCFF00]/10 px-3.5 py-1.5 text-xs font-semibold text-[#CCFF00]">
            <Plus size={14} />
            Add Card
          </button>
        </motion.div>

        {/* Empty state card */}
        <motion.div
          initial={{ opacity: 0, y: 20 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ delay: 0.1 }}
          className="rounded-2xl bg-[#1E1E1E] border border-white/10 p-8 text-center"
        >
          <div className="flex justify-center mb-4">
            <div className="h-16 w-16 rounded-2xl bg-[#CCFF00]/10 flex items-center justify-center">
              <CreditCard size={28} className="text-[#CCFF00]" />
            </div>
          </div>
          <h3 className="font-display text-lg font-bold text-white mb-2">
            No Cards Available
          </h3>
          <p className="text-sm text-gray-400 leading-relaxed">
            {emptyMessage}
          </p>
        </motion.div>
      </div>
    );
  }

  // Data state (for Phase 3+ when cards exist)
  const activeCard = cards[activeIndex] || cards[0];

  return (
    <div className="min-h-screen pb-28 pt-6 px-4 max-w-lg mx-auto">
      {/* Header */}
      <motion.div
        initial={{ opacity: 0, y: 10 }}
        animate={{ opacity: 1, y: 0 }}
        className="flex items-center justify-between mb-6"
      >
        <div>
          <h1 className="font-display text-2xl font-bold text-white">Your Cards</h1>
          <p className="text-sm text-gray-400">{cards.length} cards linked</p>
        </div>
        <button className="flex items-center gap-1.5 rounded-full border border-[#CCFF00]/30 bg-[#CCFF00]/10 px-3.5 py-1.5 text-xs font-semibold text-[#CCFF00]">
          <Plus size={14} />
          Add Card
        </button>
      </motion.div>

      {/* 3D Card Stack */}
      <motion.div
        initial={{ opacity: 0, y: 20 }}
        animate={{ opacity: 1, y: 0 }}
        transition={{ delay: 0.1 }}
        className="relative h-[240px] mb-8"
      >
        <AnimatePresence mode="popLayout">
          {cards.map((card: CardItem, i: number) => {
            const offset = i - activeIndex;
            const isActive = i === activeIndex;
            const isBehind = offset > 0;
            const isGone = offset < 0;

            if (Math.abs(offset) > 2) return null;

            return (
              <motion.div
                key={card.id}
                onClick={() => setActiveIndex(i)}
                className="absolute inset-x-0 cursor-pointer"
                initial={false}
                animate={{
                  y: isBehind ? offset * 18 : 0,
                  scale: isBehind ? 1 - offset * 0.06 : 1,
                  opacity: isGone ? 0 : isBehind ? 1 - offset * 0.2 : 1,
                  rotateX: isActive ? 0 : isBehind ? -5 : 5,
                  zIndex: cards.length - Math.abs(offset),
                }}
                transition={{ type: "spring", stiffness: 300, damping: 30 }}
                style={{
                  perspective: "1200px",
                  transformStyle: "preserve-3d",
                }}
              >
                <div
                  className="rounded-2xl p-5 h-[210px] flex flex-col justify-between border border-white/10 relative overflow-hidden"
                  style={{
                    background: `linear-gradient(135deg, ${card.color1 || "#1a1a2e"}, ${card.color2 || "#16213e"})`,
                    boxShadow: isActive
                      ? "0 20px 40px rgba(0,0,0,0.4), 0 0 20px rgba(204,255,0,0.08)"
                      : "0 10px 20px rgba(0,0,0,0.3)",
                  }}
                >
                  {/* Holographic shine */}
                  <div
                    className="absolute inset-0 opacity-10"
                    style={{
                      background:
                        "linear-gradient(105deg, transparent 30%, rgba(255,255,255,0.2) 45%, transparent 60%)",
                    }}
                  />

                  {/* Card chip + contactless */}
                  <div className="flex items-start justify-between relative z-10">
                    <div>
                      <p className="font-display text-xs font-bold text-white/80">{card.bank}</p>
                      <p className="font-display text-[10px] text-white/40 mt-0.5">{card.type}</p>
                    </div>
                    <div className="flex items-center gap-2">
                      <Wifi size={16} className="text-white/40 rotate-90" />
                      <div className="h-8 w-11 rounded-md bg-gradient-to-br from-amber-300/80 to-amber-600/80 flex items-center justify-center">
                        <div className="grid grid-cols-2 gap-0.5">
                          {[...Array(4)].map((_, j) => (
                            <div key={j} className="h-1.5 w-1.5 rounded-[1px] bg-amber-900/40" />
                          ))}
                        </div>
                      </div>
                    </div>
                  </div>

                  {/* Card number */}
                  <div className="relative z-10">
                    <p className="font-display text-lg font-medium text-white tracking-[4px] mb-1">
                      {showNumber && isActive ? card.number : card.number.replace(/\d/g, "•")}
                    </p>
                    <p className="text-[10px] text-white/30 font-mono">VALID THRU {card.expiry}</p>
                  </div>

                  {/* Cardholder + Network */}
                  <div className="flex items-end justify-between relative z-10">
                    <p className="text-[11px] text-white/50 font-medium tracking-wider uppercase">
                      {card.name}
                    </p>
                    <p className="font-display text-sm font-bold text-white/70">{card.network}</p>
                  </div>
                </div>
              </motion.div>
            );
          })}
        </AnimatePresence>
      </motion.div>

      {/* Card dots indicator */}
      <div className="flex items-center justify-center gap-2 mb-6">
        {cards.map((_: CardItem, i: number) => (
          <button
            key={i}
            onClick={() => setActiveIndex(i)}
            className={`h-1.5 rounded-full transition-all ${
              i === activeIndex
                ? "w-6 bg-[#CCFF00]"
                : "w-1.5 bg-white/20"
            }`}
          />
        ))}
      </div>

      {/* Toggle visibility */}
      <motion.button
        initial={{ opacity: 0 }}
        animate={{ opacity: 1 }}
        transition={{ delay: 0.3 }}
        onClick={() => setShowNumber(!showNumber)}
        className="mx-auto flex items-center gap-2 rounded-full bg-white/5 border border-white/10 px-4 py-2 text-xs text-gray-400 mb-6"
      >
        {showNumber ? <EyeOff size={14} /> : <Eye size={14} />}
        {showNumber ? "Hide Card Details" : "Show Card Details"}
      </motion.button>

      {/* Card Details */}
      <motion.div
        initial={{ opacity: 0, y: 15 }}
        animate={{ opacity: 1, y: 0 }}
        transition={{ delay: 0.2 }}
        className="rounded-2xl bg-[#1E1E1E] border border-white/5 p-5 mb-4"
      >
        <div className="flex items-center justify-between mb-4">
          <h3 className="font-display text-sm font-bold text-white">{activeCard.bank} — {activeCard.type}</h3>
          <span className="text-[10px] text-[#CCFF00] font-semibold bg-[#CCFF00]/10 px-2 py-0.5 rounded-full">
            Active
          </span>
        </div>

        {/* Limit usage bar */}
        {activeCard.limit && (
          <div className="mb-4">
            <div className="flex justify-between text-xs mb-2">
              <span className="text-gray-400">Used: <span className="text-white font-semibold">{activeCard.used}</span></span>
              <span className="text-gray-400">Limit: <span className="text-white font-semibold">{activeCard.limit}</span></span>
            </div>
            <div className="h-2 rounded-full bg-white/5 overflow-hidden">
              <motion.div
                className="h-full rounded-full bg-gradient-to-r from-[#CCFF00] to-[#88cc00]"
                initial={{ width: 0 }}
                animate={{
                  width: `${(parseInt(activeCard.used!.replace(/[₹,]/g, "")) / parseInt(activeCard.limit!.replace(/[₹,]/g, ""))) * 100}%`,
                }}
                transition={{ duration: 1, delay: 0.3, ease: "easeOut" }}
              />
            </div>
          </div>
        )}

        {/* Quick actions */}
        <div className="grid grid-cols-3 gap-2">
          {[
            { label: "Pay Bill", icon: "💳" },
            { label: "View Statement", icon: "📄" },
            { label: "Set Limit", icon: "⚙️" },
          ].map((action, i) => (
            <button
              key={i}
              className="rounded-xl bg-white/5 border border-white/5 py-3 flex flex-col items-center gap-1.5 hover:border-[#CCFF00]/20 transition-colors"
            >
              <span className="text-base">{action.icon}</span>
              <span className="text-[10px] text-gray-400 font-medium">{action.label}</span>
            </button>
          ))}
        </div>
      </motion.div>

      {/* Recent transactions preview */}
      {transactions.length > 0 && (
        <motion.div
          initial={{ opacity: 0, y: 15 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ delay: 0.3 }}
        >
          <div className="flex items-center justify-between mb-3">
            <h3 className="font-display text-xs font-semibold text-gray-400 uppercase tracking-widest">
              Recent on this card
            </h3>
            <button className="text-xs text-[#CCFF00] font-medium">View All</button>
          </div>
          <div className="space-y-2">
            {transactions.map((txn, i) => (
              <motion.div
                key={i}
                initial={{ opacity: 0, x: -10 }}
                animate={{ opacity: 1, x: 0 }}
                transition={{ delay: 0.35 + i * 0.06 }}
                className="rounded-xl bg-[#1E1E1E] border border-white/5 p-3.5 flex items-center gap-3"
              >
                <span className="text-lg">{txn.emoji}</span>
                <div className="flex-1">
                  <p className="text-sm font-semibold text-white">{txn.name}</p>
                  <p className="text-[10px] text-gray-500">{txn.time}</p>
                </div>
                <p className="font-display text-sm font-bold text-white">{txn.amount}</p>
              </motion.div>
            ))}
          </div>
        </motion.div>
      )}
    </div>
  );
};

export default CardsScreen;
