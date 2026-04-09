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
} from "lucide-react";

/* ─── Subscriptions (detected from bank statements) ─── */
const subscriptions = [
  {
    name: "Netflix Premium",
    amount: "₹649",
    nextBilling: "Apr 15",
    icon: Tv,
    color: "bg-red-600",
    category: "Entertainment",
  },
  {
    name: "Amazon Prime",
    amount: "₹1,499",
    nextBilling: "May 02",
    icon: Flame,
    color: "bg-cyan-600",
    category: "Entertainment",
  },
  {
    name: "Spotify Family",
    amount: "₹179",
    nextBilling: "Apr 22",
    icon: Music,
    color: "bg-green-600",
    category: "Entertainment",
  },
  {
    name: "Xbox Game Pass",
    amount: "₹499",
    nextBilling: "Apr 28",
    icon: Gamepad2,
    color: "bg-emerald-700",
    category: "Entertainment",
  },
];

/* ─── Utility Bills ─── */
const utilities = [
  {
    name: "Electricity Bill",
    provider: "TATA Power",
    amount: "₹2,340",
    dueDate: "Apr 12",
    status: "due-soon" as const,
    icon: Zap,
    color: "bg-amber-600",
  },
  {
    name: "Water Bill",
    provider: "Municipal Corp",
    amount: "₹450",
    dueDate: "Apr 20",
    status: "upcoming" as const,
    icon: Droplets,
    color: "bg-blue-600",
  },
  {
    name: "Broadband",
    provider: "Spectra 200 Mbps",
    amount: "₹1,200",
    dueDate: "Apr 18",
    status: "upcoming" as const,
    icon: Wifi,
    color: "bg-purple-600",
  },
  {
    name: "House Rent",
    provider: "Monthly rent payment",
    amount: "₹18,000",
    dueDate: "May 01",
    status: "upcoming" as const,
    icon: HomeIcon,
    color: "bg-teal-600",
  },
  {
    name: "Mobile Recharge",
    provider: "Jio ₹999 Plan • Exp Apr 25",
    amount: "₹999",
    dueDate: "Apr 25",
    status: "upcoming" as const,
    icon: Phone,
    color: "bg-blue-500",
  },
];

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

const BillsScreen = () => {
  const totalMonthly =
    subscriptions.reduce((s, sub) => s + parseInt(sub.amount.replace(/[₹,]/g, "")), 0) +
    utilities.reduce((s, u) => s + parseInt(u.amount.replace(/[₹,]/g, "")), 0);

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
            <p className="font-display text-lg font-bold text-[#FF4D4D]">₹2,340</p>
          </div>
        </div>
      </motion.div>

      {/* Subscriptions (Entertainment) */}
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
              <div
                className={`h-10 w-10 rounded-xl ${sub.color} flex items-center justify-center shrink-0`}
              >
                <sub.icon size={18} className="text-white" strokeWidth={1.5} />
              </div>
              <div className="flex-1 min-w-0">
                <p className="font-display text-sm font-semibold text-white">{sub.name}</p>
                <p className="text-[10px] text-gray-500">Next billing: {sub.nextBilling}</p>
              </div>
              <div className="text-right shrink-0">
                <p className="font-display text-sm font-bold text-white">{sub.amount}</p>
                <p className="text-[9px] text-gray-500">/month</p>
              </div>
            </motion.div>
          ))}
        </div>

        <div className="mt-3 flex items-center justify-between rounded-xl bg-amber-500/5 border border-amber-500/15 px-4 py-2.5">
          <p className="text-[11px] text-amber-400 font-medium">
            💡 You spend ₹
            {subscriptions
              .reduce((s, sub) => s + parseInt(sub.amount.replace(/[₹,]/g, "")), 0)
              .toLocaleString("en-IN")}{" "}
            /month on subscriptions
          </p>
          <ChevronRight size={14} className="text-amber-400" />
        </div>
      </motion.div>

      {/* Utilities */}
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
            const style = statusStyle[bill.status];
            return (
              <motion.div
                key={i}
                initial={{ opacity: 0, x: -10 }}
                animate={{ opacity: 1, x: 0 }}
                transition={{ delay: 0.35 + i * 0.05 }}
                className={`rounded-2xl bg-[#1E1E1E] border ${style.border} px-4 py-3.5 flex items-center gap-3`}
              >
                <div
                  className={`h-10 w-10 rounded-xl ${bill.color} flex items-center justify-center shrink-0`}
                >
                  <bill.icon size={18} className="text-white" strokeWidth={1.5} />
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
                    <p className="font-display text-sm font-bold text-white">{bill.amount}</p>
                    <p className="text-[9px] text-gray-500">Due {bill.dueDate}</p>
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
    </div>
  );
};

export default BillsScreen;
