import { useEffect, useState } from "react";
import { motion } from "framer-motion";
import { ChevronLeft, ChevronRight, FileText, Loader2, Sparkles, Zap } from "lucide-react";
import { api, BillsData } from "@/lib/api";

const MONTH_NAMES = [
  "January",
  "February",
  "March",
  "April",
  "May",
  "June",
  "July",
  "August",
  "September",
  "October",
  "November",
  "December",
];

const BillsScreen = () => {
  const today = new Date();
  const [year, setYear] = useState(today.getFullYear());
  const [month, setMonth] = useState(today.getMonth() + 1);
  const [data, setData] = useState<BillsData | null>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    const userId = localStorage.getItem("user_id");
    if (!userId) {
      setLoading(false);
      return;
    }

    setLoading(true);
    api.getBills(userId, year, month)
      .then((res) => {
        setData(res);
        setYear(res.year);
        setMonth(res.month_number);
      })
      .catch((err) => console.error("[BillsScreen] API error:", err))
      .finally(() => setLoading(false));
  }, [year, month]);

  const moveMonth = (direction: -1 | 1) => {
    if (direction === -1) {
      if (month === 1) {
        setMonth(12);
        setYear((current) => current - 1);
      } else {
        setMonth((current) => current - 1);
      }
      return;
    }

    if (month === 12) {
      setMonth(1);
      setYear((current) => current + 1);
    } else {
      setMonth((current) => current + 1);
    }
  };

  if (loading) {
    return (
      <div className="min-h-screen flex items-center justify-center">
        <Loader2 size={32} className="text-[#CCFF00] animate-spin" />
      </div>
    );
  }

  const bills = data?.bills ?? [];
  const hasData = data?.has_data ?? false;
  const emptyMessage = data?.message || "No bills detected for this month.";

  return (
    <div className="min-h-screen pb-28 pt-6 px-4 max-w-lg mx-auto">
      <motion.div
        initial={{ opacity: 0, y: 10 }}
        animate={{ opacity: 1, y: 0 }}
        className="mb-6"
      >
        <h1 className="font-display text-2xl font-bold text-white">Bills</h1>
        <p className="text-sm text-gray-400">One clean bill view per month, grouped by type</p>
      </motion.div>

      <motion.div
        initial={{ opacity: 0, y: 10 }}
        animate={{ opacity: 1, y: 0 }}
        transition={{ delay: 0.05 }}
        className="flex items-center justify-center gap-5 mb-5"
      >
        <button
          onClick={() => moveMonth(-1)}
          className="h-8 w-8 rounded-full bg-white/5 border border-white/5 flex items-center justify-center hover:border-[#CCFF00]/30 transition-colors"
        >
          <ChevronLeft size={16} className="text-gray-400" />
        </button>
        <h2 className="font-display text-lg font-bold text-white min-w-[160px] text-center">
          {data?.month || `${MONTH_NAMES[month - 1]} ${year}`}
        </h2>
        <button
          onClick={() => moveMonth(1)}
          className="h-8 w-8 rounded-full bg-white/5 border border-white/5 flex items-center justify-center hover:border-[#CCFF00]/30 transition-colors"
        >
          <ChevronRight size={16} className="text-gray-400" />
        </button>
      </motion.div>

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
            <p className="text-[10px] text-gray-500 uppercase tracking-widest mb-1">Monthly Outflow</p>
            <p className="font-display text-3xl font-extrabold text-white">
              ₹{(data?.total_outflow ?? 0).toLocaleString("en-IN")}
            </p>
          </div>
          <div className="text-right">
            <p className="text-[10px] text-gray-500 mb-1">Due this week</p>
            <p className="font-display text-lg font-bold text-[#FF4D4D]">
              ₹{(data?.due_this_week ?? 0).toLocaleString("en-IN")}
            </p>
          </div>
        </div>
      </motion.div>

      {!hasData ? (
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
          <h3 className="font-display text-lg font-bold text-white mb-2">No Bills Yet</h3>
          <p className="text-sm text-gray-400 leading-relaxed">{emptyMessage}</p>
        </motion.div>
      ) : (
        <motion.div
          initial={{ opacity: 0, y: 15 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ delay: 0.2 }}
        >
          <div className="flex items-center gap-2 mb-3">
            <Zap size={14} className="text-[#CCFF00]" />
            <h2 className="font-display text-[10px] font-semibold text-gray-400 uppercase tracking-widest">
              Grouped Monthly Bills
            </h2>
          </div>

          <div className="space-y-3">
            {bills.map((bill, index) => (
              <motion.div
                key={`${bill.name}-${bill.due_date}`}
                initial={{ opacity: 0, y: 10 }}
                animate={{ opacity: 1, y: 0 }}
                transition={{ delay: 0.25 + index * 0.04 }}
                className="rounded-2xl bg-[#1E1E1E] border border-white/5 px-4 py-4"
              >
                <div className="flex items-start justify-between gap-4">
                  <div>
                    <div className="flex items-center gap-2 mb-1">
                      <Sparkles size={14} className="text-[#CCFF00]" />
                      <p className="font-display text-sm font-semibold text-white">{bill.name}</p>
                    </div>
                    <p className="text-[11px] text-gray-500">Due on {bill.due_date || "TBD"}</p>
                    <p className="text-[11px] text-gray-500 mt-1">
                      3-month average: ₹{(bill.avg ?? 0).toLocaleString("en-IN")}
                    </p>
                  </div>
                  <div className="text-right">
                    <p className="font-display text-lg font-bold text-white">
                      ₹{bill.amount.toLocaleString("en-IN")}
                    </p>
                    <span className="inline-flex rounded-full bg-white/5 px-2 py-1 text-[10px] text-gray-400 mt-2">
                      {bill.status === "due-soon" ? "Due Soon" : "Upcoming"}
                    </span>
                  </div>
                </div>
              </motion.div>
            ))}
          </div>
        </motion.div>
      )}
    </div>
  );
};

export default BillsScreen;
