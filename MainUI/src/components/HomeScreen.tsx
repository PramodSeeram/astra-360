import { motion } from "framer-motion";
import { Bell, TrendingUp, AlertTriangle, CheckCircle2, Brain, ChevronRight, Sparkles } from "lucide-react";

interface Props {
  onAgentClick: (agent: string) => void;
  onNavigate?: (view: string) => void;
}

const insights = [
  {
    id: 1,
    type: "warning" as const,
    icon: AlertTriangle,
    text: "⚠️ House Rent of ₹18,000 is due in 3 days. Your account balance is sufficient.",
    action: "bills",
    time: "2 hrs ago",
  },
  {
    id: 2,
    type: "warning" as const,
    icon: AlertTriangle,
    text: "⚠️ TATA Power Electricity Bill of ₹2,340 is due tomorrow. Tap to pay now.",
    action: "bills",
    time: "5 hrs ago",
  },
  {
    id: 3,
    type: "info" as const,
    icon: TrendingUp,
    text: "ℹ️ Detected a new subscription: Netflix Premium at ₹649/month. Tap to review.",
    action: "bills",
    time: "1 day ago",
  },
  {
    id: 4,
    type: "success" as const,
    icon: CheckCircle2,
    text: "✅ HDFC FD of ₹50,000 maturing in 2 days. Should I reinvest it at 7.1% or move to Liquid Fund?",
    time: "1 day ago",
  },
  {
    id: 5,
    type: "success" as const,
    icon: CheckCircle2,
    text: "✅ Tax-saving SIP target 80% complete. ₹30,000 more needed before March to maximize 80C.",
    time: "2 days ago",
  },
];

const typeStyles = {
  warning: {
    border: "border-amber-500/20",
    bg: "bg-amber-500/5",
    iconColor: "text-amber-400",
  },
  success: {
    border: "border-[#CCFF00]/20",
    bg: "bg-[#CCFF00]/5",
    iconColor: "text-[#CCFF00]",
  },
  info: {
    border: "border-cyan-400/20",
    bg: "bg-cyan-400/5",
    iconColor: "text-cyan-400",
  },
};

const HomeScreen = ({ onAgentClick, onNavigate }: Props) => {
  return (
    <div className="min-h-screen pb-28 pt-4 px-4 max-w-lg mx-auto">
      {/* Header */}
      <motion.div
        initial={{ opacity: 0, y: 10 }}
        animate={{ opacity: 1, y: 0 }}
        className="flex items-center justify-between mb-6"
      >
        <div className="flex items-center gap-3">
          <div className="h-11 w-11 rounded-full bg-gradient-to-br from-[#CCFF00] to-[#88cc00] flex items-center justify-center text-black font-bold text-sm shadow-[0_0_15px_rgba(204,255,0,0.3)]">
            PK
          </div>
          <div>
            <p className="text-xs text-gray-400">Welcome back,</p>
            <p className="font-display text-lg font-bold text-white">
              Pramod! 👋
            </p>
          </div>
        </div>
        <motion.button
          whileTap={{ scale: 0.9 }}
          className="relative h-10 w-10 rounded-full bg-white/5 border border-white/10 flex items-center justify-center backdrop-blur-md"
        >
          <Bell size={18} className="text-gray-400" />
          <span className="absolute -top-0.5 -right-0.5 h-2.5 w-2.5 rounded-full bg-[#FF4D4D] border-2 border-[#111111]" />
        </motion.button>
      </motion.div>

      {/* Net Worth Hero Card */}
      <motion.div
        initial={{ opacity: 0, y: 20 }}
        animate={{ opacity: 1, y: 0 }}
        transition={{ delay: 0.1 }}
        className="relative rounded-3xl overflow-hidden border border-white/10 p-6 mb-6"
      >
        {/* Animated background */}
        <div className="absolute inset-0 bg-[#1E1E1E]" />
        <motion.div
          className="absolute inset-0 opacity-30"
          style={{
            background:
              "radial-gradient(ellipse at 30% 50%, rgba(204,255,0,0.15) 0%, transparent 60%), radial-gradient(ellipse at 70% 50%, rgba(0,240,255,0.08) 0%, transparent 60%)",
          }}
          animate={{
            opacity: [0.2, 0.35, 0.2],
          }}
          transition={{
            duration: 4,
            repeat: Infinity,
            ease: "easeInOut",
          }}
        />
        {/* Grid pattern overlay */}
        <div
          className="absolute inset-0 opacity-[0.03]"
          style={{
            backgroundImage:
              "linear-gradient(rgba(255,255,255,0.1) 1px, transparent 1px), linear-gradient(90deg, rgba(255,255,255,0.1) 1px, transparent 1px)",
            backgroundSize: "20px 20px",
          }}
        />

        <div className="relative z-10">
          <div className="flex items-center gap-2 mb-3">
            <Sparkles size={14} className="text-[#CCFF00]" />
            <p className="text-xs text-gray-400 uppercase tracking-widest font-medium">
              Total Aggregated Balance
            </p>
          </div>
          <motion.p
            className="font-display text-5xl font-extrabold text-[#CCFF00] mb-1 tracking-tight"
            style={{
              textShadow: "0 0 30px rgba(204,255,0,0.3)",
            }}
            initial={{ opacity: 0, scale: 0.9 }}
            animate={{ opacity: 1, scale: 1 }}
            transition={{ delay: 0.3, type: "spring", stiffness: 200 }}
          >
            ₹1,20,000
          </motion.p>
          <div className="flex items-center gap-2 mt-2">
            <span className="inline-flex items-center gap-1 text-xs text-emerald-400 bg-emerald-400/10 rounded-full px-2.5 py-0.5">
              <TrendingUp size={12} />
              +12.4%
            </span>
            <span className="text-xs text-gray-500">vs last month</span>
          </div>

          {/* Mini stats row */}
          <div className="mt-5 grid grid-cols-3 gap-3">
            {[
              { label: "Savings", value: "₹85,000", accent: false },
              { label: "Investments", value: "₹30,000", accent: false },
              { label: "Credit Due", value: "₹5,000", accent: true },
            ].map((stat, i) => (
              <div
                key={i}
                className="rounded-xl bg-white/5 border border-white/5 px-3 py-2.5 text-center"
              >
                <p className="text-[10px] text-gray-500 mb-1">{stat.label}</p>
                <p
                  className={`font-display text-sm font-bold ${stat.accent ? "text-amber-400" : "text-white"}`}
                >
                  {stat.value}
                </p>
              </div>
            ))}
          </div>
        </div>
      </motion.div>

      {/* Credit Health Widget (clickable → credit score detail) */}
      <motion.button
        initial={{ opacity: 0, y: 20 }}
        animate={{ opacity: 1, y: 0 }}
        transition={{ delay: 0.2 }}
        whileTap={{ scale: 0.98 }}
        onClick={() => onNavigate?.("credit-score")}
        className="w-full rounded-2xl bg-[#1E1E1E] border border-white/5 p-4 mb-6 flex items-center gap-4 text-left hover:border-[#CCFF00]/15 transition-colors"
      >
        {/* Mini Arc Chart */}
        <div className="relative shrink-0">
          <svg width="70" height="45" viewBox="0 0 70 45">
            {/* Background arc */}
            <path
              d="M 5 40 A 30 30 0 0 1 65 40"
              fill="none"
              stroke="rgba(255,255,255,0.08)"
              strokeWidth="6"
              strokeLinecap="round"
            />
            {/* Filled arc - 780/900 = ~86.7% */}
            <motion.path
              d="M 5 40 A 30 30 0 0 1 65 40"
              fill="none"
              stroke="#CCFF00"
              strokeWidth="6"
              strokeLinecap="round"
              initial={{ pathLength: 0 }}
              animate={{ pathLength: 0.867 }}
              transition={{ duration: 1.5, ease: "easeOut", delay: 0.5 }}
              style={{ filter: "drop-shadow(0 0 6px rgba(204,255,0,0.4))" }}
            />
          </svg>
          <div className="absolute inset-0 flex items-end justify-center pb-0">
            <span className="font-display text-lg font-extrabold text-white">
              780
            </span>
          </div>
        </div>

        <div className="flex-1">
          <p className="font-display text-sm font-bold text-white">
            CIBIL Score
          </p>
          <p className="text-[11px] text-gray-400 mt-0.5">
            Excellent • Updated 2 days ago
          </p>
          <div className="flex items-center gap-1.5 mt-1.5">
            <span className="h-1.5 w-1.5 rounded-full bg-[#CCFF00]" />
            <p className="text-[10px] text-[#CCFF00] font-medium">
              +15 pts since last month
            </p>
          </div>
        </div>

        <ChevronRight size={16} className="text-gray-500 shrink-0" />
      </motion.button>

      {/* AI Insights Feed */}
      <motion.div
        initial={{ opacity: 0, y: 15 }}
        animate={{ opacity: 1, y: 0 }}
        transition={{ delay: 0.3 }}
      >
        <div className="flex items-center gap-2 mb-4">
          <Brain size={16} className="text-[#CCFF00]" />
          <h2 className="font-display text-xs font-semibold text-gray-400 uppercase tracking-widest">
            Latest Brain Insights
          </h2>
        </div>

        <div className="space-y-3">
          {insights.map((insight, i) => {
            const style = typeStyles[insight.type];
            return (
              <motion.div
                key={insight.id}
                initial={{ opacity: 0, y: 15 }}
                animate={{ opacity: 1, y: 0 }}
                transition={{ delay: 0.35 + i * 0.07 }}
                whileTap={{ scale: 0.98 }}
                onClick={() => {
                  if (insight.action === "bills" && onNavigate) {
                    onNavigate("bills");
                  }
                }}
                className={`rounded-2xl bg-[#1E1E1E] border ${style.border} p-4 cursor-pointer transition-all hover:border-white/15`}
              >
                <div className="flex gap-3">
                  <div
                    className={`shrink-0 flex h-8 w-8 items-center justify-center rounded-xl ${style.bg}`}
                  >
                    <insight.icon size={14} className={style.iconColor} />
                  </div>
                  <div className="flex-1 min-w-0">
                    <p className="text-[13px] text-white leading-relaxed font-medium">
                      {insight.text}
                    </p>
                    <p className="text-[10px] text-gray-500 mt-2">
                      {insight.time}
                    </p>
                  </div>
                </div>
              </motion.div>
            );
          })}
        </div>
      </motion.div>
    </div>
  );
};

export default HomeScreen;
