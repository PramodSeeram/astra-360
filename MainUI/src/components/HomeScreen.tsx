import { ChangeEvent, useEffect, useRef, useState } from "react";
import { motion } from "framer-motion";
import { Bell, TrendingUp, AlertTriangle, Brain, ChevronRight, Sparkles, Upload, Loader2, Lightbulb, Wallet } from "lucide-react";
import { api, HomeSummary } from "@/lib/api";

interface Props {
  onAgentClick: (agent: string) => void;
  onNavigate?: (view: string) => void;
  isEmpty?: boolean;
}

const typeStyles = {
  income: {
    border: "border-emerald-400/20",
    bg: "bg-emerald-400/10",
    iconColor: "text-emerald-400",
    Icon: Wallet,
  },
  spending: {
    border: "border-cyan-400/20",
    bg: "bg-cyan-400/5",
    iconColor: "text-cyan-400",
    Icon: TrendingUp,
  },
  risk: {
    border: "border-amber-500/20",
    bg: "bg-amber-500/5",
    iconColor: "text-amber-400",
    Icon: AlertTriangle,
  },
  behavior: {
    border: "border-violet-400/20",
    bg: "bg-violet-400/10",
    iconColor: "text-violet-300",
    Icon: Brain,
  },
  optimization: {
    border: "border-[#CCFF00]/20",
    bg: "bg-[#CCFF00]/5",
    iconColor: "text-[#CCFF00]",
    Icon: Lightbulb,
  },
  system: {
    border: "border-white/10",
    bg: "bg-white/5",
    iconColor: "text-gray-300",
    Icon: Sparkles,
  },
};

const HomeScreen = ({ onAgentClick, onNavigate, isEmpty: isEmptyProp = false }: Props) => {
  const [data, setData] = useState<HomeSummary | null>(null);
  const [loading, setLoading] = useState(true);
  const [uploading, setUploading] = useState(false);
  const [uploadMessage, setUploadMessage] = useState<string | null>(null);
  const fileInputRef = useRef<HTMLInputElement | null>(null);

  useEffect(() => {
    const userId = localStorage.getItem("user_id");
    if (!userId) {
      setLoading(false);
      return;
    }

    api.getHomeSummary(userId)
      .then((res) => setData(res))
      .catch((err) => console.error("[HomeScreen] API error:", err))
      .finally(() => setLoading(false));
  }, []);

  const isEmpty = data ? !data.has_data : isEmptyProp;
  const firstName = data?.first_name || "User";
  const initials = data?.initials || "U";
  const balance = data?.balance ?? 0;
  const savings = data?.savings ?? 0;
  const investments = data?.investments ?? 0;
  const creditDue = data?.credit_due ?? 0;
  const creditScore = data?.credit_score ?? 0;
  const insights = data?.insights ?? [];
  const emptyMessage = data?.message || "Upload your financial documents to get started. We'll analyze your accounts, investments, and bills to give you personalized AI insights.";

  const formatCurrency = (val: number) => {
    if (val === 0) return "₹0";
    return `₹${val.toLocaleString("en-IN")}`;
  };

  const handleUploadClick = () => {
    setUploadMessage(null);
    fileInputRef.current?.click();
  };

  const handleFileChange = async (event: ChangeEvent<HTMLInputElement>) => {
    const selectedFile = event.target.files?.[0];
    const userId = localStorage.getItem("user_id");
    if (!selectedFile || !userId) return;

    try {
      setUploading(true);
      setUploadMessage("Starting analysis...");
      await api.activateData(userId, selectedFile);
      
      // Start Polling
      const poll = setInterval(async () => {
        try {
          const status = await api.getActivationStatus(userId);
          setUploadMessage(`Analyzing: ${status.stage} (${status.progress}%)`);
          
          if (status.status === "completed") {
            clearInterval(poll);
            setUploadMessage("Activation complete! Reloading...");
            setTimeout(() => window.location.reload(), 1500);
          } else if (status.status === "failed") {
            clearInterval(poll);
            setUploadMessage(`Error: ${status.error}`);
            setUploading(false);
          }
        } catch (e) {
          console.error("Polling error:", e);
        }
      }, 2000);

    } catch (error) {
      console.error("[HomeScreen] Upload error:", error);
      setUploadMessage(error instanceof Error ? error.message : "Upload failed");
      setUploading(false);
    } finally {
      event.target.value = "";
    }
  };

  if (loading) {
    return (
      <div className="min-h-screen flex items-center justify-center">
        <Loader2 size={32} className="text-[#CCFF00] animate-spin" />
      </div>
    );
  }

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
            {initials}
          </div>
          <div>
            <p className="text-xs text-gray-400">Welcome back,</p>
            <p className="font-display text-lg font-bold text-white">
              {firstName}! 👋
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
            {formatCurrency(balance)}
          </motion.p>
          {!isEmpty && (
            <div className="flex items-center gap-2 mt-2">
              <span className="inline-flex items-center gap-1 text-xs text-emerald-400 bg-emerald-400/10 rounded-full px-2.5 py-0.5">
                <TrendingUp size={12} />
                +12.4%
              </span>
              <span className="text-xs text-gray-500">vs last month</span>
            </div>
          )}

          {/* Mini stats row */}
          <div className="mt-5 grid grid-cols-3 gap-3">
            {[
              { label: "Savings", value: formatCurrency(savings), accent: false },
              { label: "Investments", value: formatCurrency(investments), accent: false },
              { label: "Credit Due", value: formatCurrency(creditDue), accent: creditDue > 0 },
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
            {/* Filled arc */}
            <motion.path
              d="M 5 40 A 30 30 0 0 1 65 40"
              fill="none"
              stroke="#CCFF00"
              strokeWidth="6"
              strokeLinecap="round"
              initial={{ pathLength: 0 }}
              animate={{ pathLength: creditScore > 0 ? creditScore / 900 : 0 }}
              transition={{ duration: 1.5, ease: "easeOut", delay: 0.5 }}
              style={{ filter: "drop-shadow(0 0 6px rgba(204,255,0,0.4))" }}
            />
          </svg>
          <div className="absolute inset-0 flex items-end justify-center pb-0">
            <span className="font-display text-lg font-extrabold text-white">
              {creditScore > 0 ? creditScore : "—"}
            </span>
          </div>
        </div>

        <div className="flex-1">
          <p className="font-display text-sm font-bold text-white">
            CIBIL Score
          </p>
          <p className="text-[11px] text-gray-400 mt-0.5">
            {creditScore > 0 ? "Excellent • Updated 2 days ago" : "Not available yet"}
          </p>
          {creditScore > 0 && (
            <div className="flex items-center gap-1.5 mt-1.5">
              <span className="h-1.5 w-1.5 rounded-full bg-[#CCFF00]" />
              <p className="text-[10px] text-[#CCFF00] font-medium">
                +15 pts since last month
              </p>
            </div>
          )}
        </div>

        <ChevronRight size={16} className="text-gray-500 shrink-0" />
      </motion.button>

      {/* AI Insights Feed or Empty State */}
      {isEmpty ? (
        <motion.div
          initial={{ opacity: 0, y: 15 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ delay: 0.3 }}
          className="rounded-2xl bg-[#1E1E1E] border border-white/10 p-8 text-center"
        >
          <div className="flex justify-center mb-4">
            <div className="h-16 w-16 rounded-2xl bg-[#CCFF00]/10 flex items-center justify-center">
              <Upload size={28} className="text-[#CCFF00]" />
            </div>
          </div>
          <h3 className="font-display text-lg font-bold text-white mb-2">
            Welcome to Astra 360!
          </h3>
          <p className="text-sm text-gray-400 leading-relaxed mb-4">
            {emptyMessage}
          </p>
          <input
            ref={fileInputRef}
            type="file"
            accept=".pdf,.csv,.xls,.xlsx"
            className="hidden"
            onChange={handleFileChange}
          />
          <button
            type="button"
            onClick={handleUploadClick}
            disabled={uploading}
            className="rounded-xl bg-[#CCFF00] px-6 py-3 text-sm font-semibold text-black transition-all hover:opacity-90 active:scale-[0.98] disabled:cursor-not-allowed disabled:opacity-60"
          >
            {uploading ? "Uploading..." : "Upload Documents"}
          </button>
          {uploadMessage && (
            <p className="mt-3 text-sm text-gray-300">{uploadMessage}</p>
          )}
        </motion.div>
      ) : (
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
              const style = typeStyles[insight.type] || typeStyles.behavior;
              const InsightIcon = style.Icon;
              const canOpenBills = insight.action === "bills" && Boolean(onNavigate);
              return (
                <motion.div
                  key={insight.id}
                  initial={{ opacity: 0, y: 15 }}
                  animate={{ opacity: 1, y: 0 }}
                  transition={{ delay: 0.35 + i * 0.07 }}
                  whileTap={{ scale: 0.98 }}
                  onClick={() => {
                    if (canOpenBills && onNavigate) {
                      onNavigate("bills");
                    }
                  }}
                  className={`rounded-2xl bg-[#1E1E1E] border ${style.border} p-4 transition-all hover:border-white/15 ${canOpenBills ? "cursor-pointer" : "cursor-default"}`}
                >
                  <div className="flex gap-3">
                    <div
                      className={`shrink-0 flex h-8 w-8 items-center justify-center rounded-xl ${style.bg}`}
                    >
                      <InsightIcon size={14} className={style.iconColor} />
                    </div>
                    <div className="flex-1 min-w-0">
                      <p className="text-[10px] text-gray-500 uppercase tracking-[0.18em] mb-1">
                        {insight.title}
                      </p>
                      <p className="text-[13px] text-white leading-relaxed font-medium">
                        {insight.text}
                      </p>
                      {insight.suggestion && (
                        <p className="text-[11px] text-gray-400 mt-2 leading-relaxed">
                          <span className="text-[#CCFF00]">Suggestion:</span> {insight.suggestion}
                        </p>
                      )}
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
      )}
    </div>
  );
};

export default HomeScreen;
