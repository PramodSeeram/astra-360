import { useState, useEffect } from "react";
import { motion } from "framer-motion";
import {
  ArrowLeft,
  Clock,
  CreditCard,
  Scale,
  Search,
  Layers,
  TrendingUp,
  ChevronRight,
  Sparkles,
  MessageCircle,
  Loader2,
  AlertCircle,
} from "lucide-react";
import { api, HomeSummary } from "@/lib/api";

interface Props {
  onBack: () => void;
  onAskImprove: () => void;
}

/* ─── Factor data (SuperMoney-style) ─── */
const factors = [
  {
    icon: Clock,
    label: "On-Time Payments",
    status: "Excellent",
    statusColor: "text-emerald-400",
    detail: "100% payments on time (36/36)",
    barPct: 100,
    barColor: "from-emerald-400 to-emerald-500",
    impact: "High Impact",
  },
  {
    icon: CreditCard,
    label: "Credit Utilization",
    status: "Good",
    statusColor: "text-[#CCFF00]",
    detail: "Using 24% of available credit",
    barPct: 76,
    barColor: "from-[#CCFF00] to-[#88cc00]",
    impact: "High Impact",
  },
  {
    icon: Layers,
    label: "Credit Age",
    status: "Fair",
    statusColor: "text-amber-400",
    detail: "Average age: 3 years 4 months",
    barPct: 55,
    barColor: "from-amber-400 to-amber-500",
    impact: "Medium Impact",
  },
  {
    icon: Search,
    label: "Credit Enquiries",
    status: "Good",
    statusColor: "text-[#CCFF00]",
    detail: "2 hard enquiries in last 6 months",
    barPct: 70,
    barColor: "from-[#CCFF00] to-[#88cc00]",
    impact: "Low Impact",
  },
  {
    icon: Scale,
    label: "Credit Mix",
    status: "Excellent",
    statusColor: "text-emerald-400",
    detail: "Good mix of secured & unsecured loans",
    barPct: 90,
    barColor: "from-emerald-400 to-emerald-500",
    impact: "Low Impact",
  },
];

/* ─── Account summary ─── */
const accounts = [
  { label: "Active Loans", value: "2", detail: "Home Loan, Car Loan" },
  { label: "Credit Cards", value: "4", detail: "Active accounts" },
  { label: "Late Payments", value: "0", detail: "In last 12 months" },
  { label: "Total Credit Limit", value: "₹11.5L", detail: "Across all cards" },
];

/* ─── SVG arc helpers ─── */
const r = 90;
const cx = 110;
const cy = 105;
const startAngle = 180;

const polarToCart = (angleDeg: number) => ({
  x: cx + r * Math.cos((angleDeg * Math.PI) / 180),
  y: cy - r * Math.sin((angleDeg * Math.PI) / 180),
});

const CreditScoreDetail = ({ onBack, onAskImprove }: Props) => {
  const [data, setData] = useState<HomeSummary | null>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    const userId = localStorage.getItem("astra_user_id");
    if (!userId) {
      setLoading(false);
      return;
    }

    api.getHomeSummary(userId)
      .then((res) => setData(res))
      .catch((err) => console.error("[CreditScoreDetail] API error:", err))
      .finally(() => setLoading(false));
  }, []);

  if (loading) {
    return (
      <div className="min-h-screen flex items-center justify-center">
        <Loader2 size={32} className="text-[#CCFF00] animate-spin" />
      </div>
    );
  }

  const score = data?.credit_score ?? 0;
  const hasData = (data?.has_data ?? false) && score > 0;
  
  const minScore = 300;
  const maxScore = 900;
  const normalizedScore = Math.max(minScore, Math.min(maxScore, score));
  const pct = (normalizedScore - minScore) / (maxScore - minScore);
  const endAngle = 180 - pct * 180;

  const start = polarToCart(startAngle);
  const end = polarToCart(endAngle);
  const arcPath = `M ${start.x} ${start.y} A ${r} ${r} 0 0 1 ${end.x} ${end.y}`;
  const bgEnd = polarToCart(0);
  const bgPath = `M ${start.x} ${start.y} A ${r} ${r} 0 0 1 ${bgEnd.x} ${bgEnd.y}`;

  return (
    <div className="min-h-screen pb-28 pt-4 px-4 max-w-lg mx-auto">
      {/* Header */}
      <motion.div
        initial={{ opacity: 0, y: 10 }}
        animate={{ opacity: 1, y: 0 }}
        className="flex items-center gap-3 mb-6"
      >
        <button
          onClick={onBack}
          className="h-9 w-9 rounded-full bg-white/5 border border-white/10 flex items-center justify-center"
        >
          <ArrowLeft size={16} className="text-gray-400" />
        </button>
        <div>
          <h1 className="font-display text-lg font-bold text-white">Credit Score</h1>
          <p className="text-[11px] text-gray-400">Powered by RBI-approved bureau</p>
        </div>
      </motion.div>

      {/* Score Hero */}
      <motion.div
        initial={{ opacity: 0, y: 20 }}
        animate={{ opacity: 1, y: 0 }}
        transition={{ delay: 0.1 }}
        className="relative rounded-3xl bg-[#1E1E1E] border border-white/5 p-6 mb-6 overflow-hidden"
      >
        {/* Subtle radial glow */}
        <div
          className="absolute inset-0 opacity-20 pointer-events-none"
          style={{
            background:
              "radial-gradient(ellipse at 50% 80%, rgba(204,255,0,0.15) 0%, transparent 60%)",
          }}
        />

        <div className="relative flex flex-col items-center">
          <svg width="220" height="130" viewBox="0 0 220 130">
            {/* Tick marks */}
            {[0, 0.25, 0.5, 0.75, 1].map((t, i) => {
              const angle = 180 - t * 180;
              const inner = polarToCart(angle);
              const outerR = r + 10;
              const outer = {
                x: cx + outerR * Math.cos((angle * Math.PI) / 180),
                y: cy - outerR * Math.sin((angle * Math.PI) / 180),
              };
              return (
                <line
                  key={i}
                  x1={inner.x}
                  y1={inner.y}
                  x2={outer.x}
                  y2={outer.y}
                  stroke="rgba(255,255,255,0.15)"
                  strokeWidth="1.5"
                />
              );
            })}

            {/* Background arc */}
            <path
              d={bgPath}
              fill="none"
              stroke="rgba(255,255,255,0.06)"
              strokeWidth="10"
              strokeLinecap="round"
            />

            {/* Gradient fill definition */}
            <defs>
              <linearGradient id="scoreGrad" x1="0%" y1="0%" x2="100%" y2="0%">
                <stop offset="0%" stopColor="#FF4D4D" />
                <stop offset="30%" stopColor="#FFB800" />
                <stop offset="60%" stopColor="#CCFF00" />
                <stop offset="100%" stopColor="#00FF66" />
              </linearGradient>
            </defs>

            {/* Filled arc */}
            <motion.path
              d={arcPath}
              fill="none"
              stroke="url(#scoreGrad)"
              strokeWidth="10"
              strokeLinecap="round"
              initial={{ pathLength: 0 }}
              animate={{ pathLength: hasData ? 1 : 0 }}
              transition={{ duration: 2, ease: "easeOut", delay: 0.3 }}
              style={{ filter: "drop-shadow(0 0 8px rgba(204,255,0,0.3))" }}
            />

            {/* Dot at end */}
            {hasData && (
              <motion.circle
                cx={end.x}
                cy={end.y}
                r="7"
                fill="#CCFF00"
                initial={{ opacity: 0, scale: 0 }}
                animate={{ opacity: 1, scale: 1 }}
                transition={{ delay: 2 }}
                style={{ filter: "drop-shadow(0 0 6px rgba(204,255,0,0.6))" }}
              />
            )}

            {/* Labels */}
            <text x="15" y="125" fill="rgba(255,255,255,0.3)" fontSize="10" fontFamily="Outfit">
              300
            </text>
            <text x="190" y="125" fill="rgba(255,255,255,0.3)" fontSize="10" fontFamily="Outfit">
              900
            </text>
          </svg>

          {/* Central score */}
          <motion.div
            className="absolute bottom-4 flex flex-col items-center"
            initial={{ opacity: 0 }}
            animate={{ opacity: 1 }}
            transition={{ delay: 1 }}
          >
            {hasData ? (
              <>
                <span className="font-display text-5xl font-extrabold text-white">{score}</span>
                <span className="text-sm font-bold text-[#CCFF00] mt-0.5 tracking-wider uppercase">
                  {score >= 750 ? "Excellent" : score >= 700 ? "Good" : score >= 600 ? "Fair" : "Poor"}
                </span>
              </>
            ) : (
              <div className="flex flex-col items-center opacity-60">
                <span className="font-display text-4xl font-extrabold text-gray-500">N/A</span>
                <span className="text-[10px] font-bold text-gray-600 mt-1 tracking-wider text-center max-w-[120px]">
                  UPLOAD DATA TO CALCULATE
                </span>
              </div>
            )}
          </motion.div>
        </div>

        <div className="flex items-center justify-center gap-2 mt-2">
          {hasData ? (
            <>
              <TrendingUp size={14} className="text-emerald-400" />
              <span className="text-xs text-emerald-400 font-medium">+15 pts since last month</span>
              <span className="text-xs text-gray-500">• Updated 2 days ago</span>
            </>
          ) : (
            <>
              <AlertCircle size={14} className="text-gray-500" />
              <span className="text-xs text-gray-500">No score history available</span>
            </>
          )}
        </div>
      </motion.div>

      {/* Account Overview - Only show real values if hasData */}
      <motion.div
        initial={{ opacity: 0, y: 15 }}
        animate={{ opacity: 1, y: 0 }}
        transition={{ delay: 0.2 }}
        className="grid grid-cols-2 gap-3 mb-6"
      >
        {accounts.map((acc, i) => (
          <motion.div
            key={i}
            initial={{ opacity: 0, scale: 0.95 }}
            animate={{ opacity: 1, scale: 1 }}
            transition={{ delay: 0.25 + i * 0.05 }}
            className={`rounded-2xl bg-[#1E1E1E] border border-white/5 p-4 ${!hasData ? 'opacity-50' : ''}`}
          >
            <p className="text-[10px] text-gray-500 uppercase tracking-wider mb-1">{acc.label}</p>
            <p className="font-display text-2xl font-extrabold text-white">{hasData ? acc.value : '—'}</p>
            <p className="text-[10px] text-gray-400 mt-0.5">{hasData ? acc.detail : 'Upload docs'}</p>
          </motion.div>
        ))}
      </motion.div>

      {/* Credit Factors (SuperMoney-style) */}
      <motion.div
        initial={{ opacity: 0, y: 15 }}
        animate={{ opacity: 1, y: 0 }}
        transition={{ delay: 0.3 }}
        className="mb-6"
      >
        <div className="flex items-center gap-2 mb-4">
          <Sparkles size={14} className="text-[#CCFF00]" />
          <h2 className="font-display text-xs font-semibold text-gray-400 uppercase tracking-widest">
            Credit Score Factors
          </h2>
        </div>

        <div className="space-y-3">
          {factors.map((factor, i) => (
            <motion.div
              key={i}
              initial={{ opacity: 0, x: -15 }}
              animate={{ opacity: 1, x: 0 }}
              transition={{ delay: 0.35 + i * 0.06 }}
              className={`rounded-2xl bg-[#1E1E1E] border border-white/5 p-4 ${!hasData ? 'opacity-40' : ''}`}
            >
              <div className="flex items-start gap-3 mb-3">
                <div className="shrink-0 h-9 w-9 rounded-xl bg-white/5 flex items-center justify-center">
                  <factor.icon size={16} className="text-gray-400" strokeWidth={1.5} />
                </div>
                <div className="flex-1 min-w-0">
                  <div className="flex items-center justify-between">
                    <p className="font-display text-sm font-semibold text-white">{factor.label}</p>
                    <span className={`text-xs font-bold ${hasData ? factor.statusColor : 'text-gray-500'}`}>
                      {hasData ? factor.status : 'N/A'}
                    </span>
                  </div>
                  <p className="text-[11px] text-gray-400 mt-0.5">{hasData ? factor.detail : 'Analysis pending data upload'}</p>
                </div>
              </div>

              {/* Progress bar */}
              <div className="flex items-center gap-3">
                <div className="flex-1 h-1.5 rounded-full bg-white/5 overflow-hidden">
                  <motion.div
                    className={`h-full rounded-full bg-gradient-to-r ${hasData ? factor.barColor : 'from-gray-700 to-gray-800'}`}
                    initial={{ width: 0 }}
                    animate={{ width: hasData ? `${factor.barPct}%` : '0%' }}
                    transition={{ duration: 1, delay: 0.5 + i * 0.1, ease: "easeOut" }}
                  />
                </div>
                <span className="text-[10px] text-gray-500 shrink-0 w-16 text-right">
                  {factor.impact}
                </span>
              </div>
            </motion.div>
          ))}
        </div>
      </motion.div>

      {/* How to Improve CTA */}
      <motion.button
        initial={{ opacity: 0, y: 10 }}
        animate={{ opacity: 1, y: 0 }}
        transition={{ delay: 0.65 }}
        whileTap={{ scale: 0.97 }}
        onClick={onAskImprove}
        className={`w-full flex items-center justify-center gap-3 rounded-2xl bg-[#CCFF00] py-4 shadow-[0_0_20px_rgba(204,255,0,0.3)] mb-3 ${!hasData ? 'opacity-50' : ''}`}
      >
        <MessageCircle size={18} className="text-black" />
        <span className="font-display text-sm font-bold text-black">
          {hasData ? "How to Improve My Score" : "Get AI Strategy to Build Score"}
        </span>
        <ChevronRight size={16} className="text-black" />
      </motion.button>

      <p className="text-center text-[10px] text-gray-500">
        Powered by Astra AI • Data from TransUnion CIBIL
      </p>
    </div>
  );
};

export default CreditScoreDetail;
