import { useState, useEffect } from "react";
import { motion } from "framer-motion";
import {
  Wifi,
  Tv,
  Music,
  Gamepad2,
  Zap,
  Droplets,
  Home as HomeIcon,
  Phone,
  ChevronRight,
  Flame,
  ArrowRight,
  Sparkles,
  FileText,
  Loader2,
} from "lucide-react";
import { api, BillsData } from "@/lib/api";

const statusStyle = {
  "due-soon": {
    badge: "Due Soon",
    badgeBg: "bg-[#FF4D4D]/10",
    badgeText: "text-[#FF4D4D]",
    border: "border-[#FF4D4D]/15",
  },
  upcoming: {
    badge: "Upcoming",
    badgeBg: "bg-white/5",
    badgeText: "text-gray-400",
    border: "border-white/5",
  },
};

/* Icon mapping for subscription/bill types from backend */
const iconMap: Record<string, typeof Tv> = {
  Tv, Music, Flame, Gamepad2, Zap, Droplets, HomeIcon, Phone, Wifi,
};

const colorMap: Record<string, string> = {
  "bg-red-600": "bg-red-600",
  "bg-cyan-600": "bg-cyan-600",
  "bg-green-600": "bg-green-600",
  "bg-emerald-700": "bg-emerald-700",
  "bg-amber-600": "bg-amber-600",
  "bg-blue-600": "bg-blue-600",
  "bg-purple-600": "bg-purple-600",
  "bg-teal-600": "bg-teal-600",
  "bg-blue-500": "bg-blue-500",
};

const BillsScreen = () => {
  const [data, setData] = useState<BillsData | null>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    const userId = localStorage.getItem("astra_user_id");
    if (!userId) {
      setLoading(false);
      return;
    }

    api.getBills(userId)
      .then((res) => setData(res))
      .catch((err) => console.error("[BillsScreen] API error:", err))
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
  const subscriptions = data?.subscriptions ?? [];
  const utilities = data?.utilities ?? [];
  const totalMonthly = data?.total_monthly ?? 0;
  const dueThisWeek = data?.due_this_week ?? 0;
  const emptyMessage = data?.message || "No bills yet. Upload your bank statements to auto-detect subscriptions and bills.";

  // Empty state
  if (!hasData) {
    return (
      <div className="min-h-screen pb-28 pt-6 px-4 max-w-lg mx-auto">
        <motion.div
          initial={{ opacity: 0, y: 10 }}
          animate={{ opacity: 1, y: 0 }}
          className="mb-6"
        >
          <h1 className="font-display text-2xl font-bold text-white">Bills & Subscriptions</h1>
          <p className="text-sm text-gray-400">
            Auto-detected from your bank statements
          </p>
        </motion.div>

        {/* Monthly Overview - Zero State */}
        <motion.div
          initial={{ opacity: 0, y: 20 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ delay: 0.1 }}
          className="rounded-2xl bg-[#1E1E1E] border border-white/5 p-5 mb-6 relative overflow-hidden"
        >
          <div
            className="absolute inset-0 opacity-10 pointer-events-none"
            style={{
              background:
                "radial-gradient(ellipse at 80% 20%, rgba(204,255,0,0.2) 0%, transparent 50%)",
            }}
          />
          <div className="relative z-10 flex items-center justify-between">
            <div>
              <p className="text-[10px] text-gray-500 uppercase tracking-widest mb-1">
                Est. Monthly Outflow
              </p>
              <p className="font-display text-3xl font-extrabold text-white">
                ₹0
              </p>
            </div>
            <div className="text-right">
              <p className="text-[10px] text-gray-500 mb-1">Due this week</p>
              <p className="font-display text-lg font-bold text-gray-500">₹0</p>
            </div>
          </div>
        </motion.div>

        {/* Empty state card */}
        <motion.div
          initial={{ opacity: 0, y: 15 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ delay: 0.2 }}
          className="rounded-2xl bg-[#1E1E1E] border border-white/10 p-8 text-center"
        >
          <div className="flex justify-center mb-4">
            <div className="h-16 w-16 rounded-2xl bg-[#CCFF00]/10 flex items-center justify-center">
              <FileText size={28} className="text-[#CCFF00]" />
            </div>
          </div>
          <h3 className="font-display text-lg font-bold text-white mb-2">
            No Bills Yet
          </h3>
          <p className="text-sm text-gray-400 leading-relaxed">
            {emptyMessage}
          </p>
        </motion.div>
      </div>
    );
  }

  // Data state (for Phase 3+ when data exists)
  return (
    <div className="min-h-screen pb-28 pt-6 px-4 max-w-lg mx-auto">
      {/* Header */}
      <motion.div
        initial={{ opacity: 0, y: 10 }}
        animate={{ opacity: 1, y: 0 }}
        className="mb-6"
      >
        <h1 className="font-display text-2xl font-bold text-white">Bills & Subscriptions</h1>
        <p className="text-sm text-gray-400">
          Auto-detected from your bank statements
        </p>
      </motion.div>

      {/* Monthly Overview */}
      <motion.div
        initial={{ opacity: 0, y: 20 }}
        animate={{ opacity: 1, y: 0 }}
        transition={{ delay: 0.1 }}
        className="rounded-2xl bg-[#1E1E1E] border border-white/5 p-5 mb-6 relative overflow-hidden"
      >
        <div
          className="absolute inset-0 opacity-10 pointer-events-none"
          style={{
            background:
              "radial-gradient(ellipse at 80% 20%, rgba(204,255,0,0.2) 0%, transparent 50%)",
          }}
        />
        <div className="relative z-10 flex items-center justify-between">
          <div>
            <p className="text-[10px] text-gray-500 uppercase tracking-widest mb-1">
              Est. Monthly Outflow
            </p>
            <p className="font-display text-3xl font-extrabold text-white">
              ₹{totalMonthly.toLocaleString("en-IN")}
            </p>
          </div>
          <div className="text-right">
            <p className="text-[10px] text-gray-500 mb-1">Due this week</p>
            <p className="font-display text-lg font-bold text-[#FF4D4D]">₹{dueThisWeek.toLocaleString("en-IN")}</p>
          </div>
        </div>
      </motion.div>

      {/* Subscriptions */}
      {subscriptions.length > 0 && (
        <motion.div
          initial={{ opacity: 0, y: 15 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ delay: 0.15 }}
          className="mb-6"
        >
          <div className="flex items-center gap-2 mb-3">
            <Sparkles size={14} className="text-[#CCFF00]" />
            <h2 className="font-display text-[10px] font-semibold text-gray-400 uppercase tracking-widest">
              Subscriptions • Entertainment
            </h2>
          </div>

          <div className="space-y-2">
            {subscriptions.map((sub, i) => (
              <motion.div
                key={i}
                initial={{ opacity: 0, x: -10 }}
                animate={{ opacity: 1, x: 0 }}
                transition={{ delay: 0.2 + i * 0.05 }}
                className="rounded-2xl bg-[#1E1E1E] border border-white/5 px-4 py-3.5 flex items-center gap-3"
              >
                <div className="h-10 w-10 rounded-xl bg-gray-600 flex items-center justify-center shrink-0">
                  <Tv size={18} className="text-white" strokeWidth={1.5} />
                </div>
                <div className="flex-1 min-w-0">
                  <p className="font-display text-sm font-semibold text-white">{sub.name}</p>
                  <p className="text-[10px] text-gray-500">Next billing: {sub.next_billing || "—"}</p>
                </div>
                <div className="text-right shrink-0">
                  <p className="font-display text-sm font-bold text-white">₹{sub.amount}</p>
                  <p className="text-[9px] text-gray-500">/month</p>
                </div>
              </motion.div>
            ))}
          </div>
        </motion.div>
      )}

      {/* Utilities */}
      {utilities.length > 0 && (
        <motion.div
          initial={{ opacity: 0, y: 15 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ delay: 0.3 }}
        >
          <div className="flex items-center gap-2 mb-3">
            <Zap size={14} className="text-[#CCFF00]" />
            <h2 className="font-display text-[10px] font-semibold text-gray-400 uppercase tracking-widest">
              Utilities & Bills
            </h2>
          </div>

          <div className="space-y-2">
            {utilities.map((bill, i) => {
              const style = statusStyle[(bill.status as keyof typeof statusStyle) || "upcoming"];
              return (
                <motion.div
                  key={i}
                  initial={{ opacity: 0, x: -10 }}
                  animate={{ opacity: 1, x: 0 }}
                  transition={{ delay: 0.35 + i * 0.05 }}
                  className={`rounded-2xl bg-[#1E1E1E] border ${style.border} px-4 py-3.5 flex items-center gap-3`}
                >
                  <div className="h-10 w-10 rounded-xl bg-gray-600 flex items-center justify-center shrink-0">
                    <Zap size={18} className="text-white" strokeWidth={1.5} />
                  </div>
                  <div className="flex-1 min-w-0">
                    <div className="flex items-center gap-2">
                      <p className="font-display text-sm font-semibold text-white">{bill.name}</p>
                      {bill.status === "due-soon" && (
                        <span
                          className={`text-[9px] font-bold px-1.5 py-0.5 rounded-full ${style.badgeBg} ${style.badgeText}`}
                        >
                          {style.badge}
                        </span>
                      )}
                    </div>
                    <p className="text-[10px] text-gray-500">{bill.provider}</p>
                  </div>
                  <div className="text-right shrink-0 flex items-center gap-2">
                    <div>
                      <p className="font-display text-sm font-bold text-white">₹{bill.amount}</p>
                      <p className="text-[9px] text-gray-500">Due {bill.due_date || "—"}</p>
                    </div>
                    <button className="h-7 w-7 rounded-full bg-[#CCFF00] flex items-center justify-center">
                      <ArrowRight size={12} className="text-black" />
                    </button>
                  </div>
                </motion.div>
              );
            })}
          </div>
        </motion.div>
      )}
    </div>
  );
};

export default BillsScreen;
