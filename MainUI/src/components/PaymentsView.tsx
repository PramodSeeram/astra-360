import { motion } from "framer-motion";
import { ArrowRight, Home as HomeIcon, Wifi, Smartphone, Zap, GraduationCap, Building2 } from "lucide-react";

const bills = [
  { logo: "Jio", name: "Jio Prepaid", number: "897651234", icon: Smartphone, color: "bg-blue-600" },
  { logo: "Airtel", name: "Airtel Prepaid", number: "976543210", icon: Wifi, color: "bg-red-500" },
];

const drafts = [
  { name: "Broadband Bill", provider: "Spectra Broadband", amount: "₹1,200", icon: Wifi, color: "bg-purple-500" },
];

const rentItems = [
  { name: "House Rent Payment", desc: "Pay your rent. Win Rewards.", icon: HomeIcon, color: "bg-emerald-600" },
];

const utilityItems = [
  { name: "Maintenance", icon: Building2 },
  { name: "Office rent", icon: Building2 },
  { name: "Security Deposit", icon: Building2 },
  { name: "Education Fees", icon: GraduationCap },
  { name: "Electricity", icon: Zap },
];

const PaymentsView = () => (
  <div className="min-h-screen pb-24 pt-6 px-4 max-w-lg mx-auto">
    <motion.div initial={{ opacity: 0, y: 10 }} animate={{ opacity: 1, y: 0 }} className="mb-6">
      <h1 className="font-display text-2xl font-bold text-foreground">Payments</h1>
      <p className="text-sm text-muted-foreground">Home for all your payments.</p>
    </motion.div>

    {/* YOUR BILLS */}
    <motion.div initial={{ opacity: 0, y: 15 }} animate={{ opacity: 1, y: 0 }} transition={{ delay: 0.1 }} className="mb-6">
      <h2 className="font-display text-[10px] font-semibold text-muted-foreground uppercase tracking-widest mb-3">
        Your Bills
      </h2>
      <div className="space-y-2">
        {bills.map((bill, i) => (
          <motion.div
            key={i}
            initial={{ opacity: 0, x: -10 }}
            animate={{ opacity: 1, x: 0 }}
            transition={{ delay: 0.15 + i * 0.06 }}
            className="rounded-2xl bg-card border border-border/30 px-4 py-3.5 flex items-center gap-3"
          >
            <div className={`h-10 w-10 rounded-xl ${bill.color} flex items-center justify-center`}>
              <bill.icon size={18} className="text-foreground" strokeWidth={1.5} />
            </div>
            <div className="flex-1 min-w-0">
              <p className="font-display text-sm font-semibold text-foreground">{bill.name}</p>
              <p className="text-xs text-muted-foreground">{bill.number}</p>
            </div>
            <button className="flex h-8 w-8 items-center justify-center rounded-full bg-primary text-primary-foreground transition-transform hover:scale-110 active:scale-95">
              <ArrowRight size={14} />
            </button>
          </motion.div>
        ))}
      </div>
    </motion.div>

    {/* YOUR PAYMENT DRAFTS */}
    <motion.div initial={{ opacity: 0, y: 15 }} animate={{ opacity: 1, y: 0 }} transition={{ delay: 0.25 }} className="mb-6">
      <h2 className="font-display text-[10px] font-semibold text-muted-foreground uppercase tracking-widest mb-3">
        Your Payment Drafts
      </h2>
      {drafts.map((draft, i) => (
        <motion.div
          key={i}
          initial={{ opacity: 0, x: -10 }}
          animate={{ opacity: 1, x: 0 }}
          transition={{ delay: 0.3 }}
          className="rounded-2xl bg-card border border-border/30 p-4 flex items-center gap-3"
        >
          <div className={`h-10 w-10 rounded-xl ${draft.color} flex items-center justify-center`}>
            <draft.icon size={18} className="text-foreground" strokeWidth={1.5} />
          </div>
          <div className="flex-1">
            <p className="font-display text-sm font-semibold text-foreground">{draft.name}</p>
            <p className="text-xs text-muted-foreground">{draft.provider}</p>
          </div>
          <div className="text-right">
            <p className="font-display text-sm font-bold text-foreground">{draft.amount}</p>
            <button className="mt-1 rounded-full bg-primary px-3 py-1 text-[10px] font-semibold text-primary-foreground">
              Continue
            </button>
          </div>
        </motion.div>
      ))}
    </motion.div>

    {/* RENT AND EDUCATION */}
    <motion.div initial={{ opacity: 0, y: 15 }} animate={{ opacity: 1, y: 0 }} transition={{ delay: 0.35 }} className="mb-6">
      <h2 className="font-display text-[10px] font-semibold text-muted-foreground uppercase tracking-widest mb-3">
        Rent and Education
      </h2>
      {rentItems.map((item, i) => (
        <div
          key={i}
          className="rounded-2xl bg-card border border-border/30 px-4 py-3.5 flex items-center gap-3 mb-2"
        >
          <div className={`h-10 w-10 rounded-xl ${item.color} flex items-center justify-center`}>
            <item.icon size={18} className="text-foreground" strokeWidth={1.5} />
          </div>
          <div className="flex-1">
            <p className="font-display text-sm font-semibold text-foreground">{item.name}</p>
            <p className="text-xs text-muted-foreground">{item.desc}</p>
          </div>
          <button className="flex h-8 w-8 items-center justify-center rounded-full bg-primary text-primary-foreground">
            <ArrowRight size={14} />
          </button>
        </div>
      ))}
    </motion.div>

    {/* Utility grid */}
    <motion.div initial={{ opacity: 0, y: 15 }} animate={{ opacity: 1, y: 0 }} transition={{ delay: 0.45 }}>
      <div className="grid grid-cols-4 gap-3">
        {utilityItems.map((item, i) => (
          <motion.button
            key={i}
            initial={{ opacity: 0, scale: 0.9 }}
            animate={{ opacity: 1, scale: 1 }}
            transition={{ delay: 0.5 + i * 0.05 }}
            className="flex flex-col items-center gap-2 rounded-2xl bg-card border border-border/30 p-3 hover:border-primary/30 transition-colors"
          >
            <item.icon size={18} className="text-primary" strokeWidth={1.5} />
            <span className="text-[9px] text-muted-foreground text-center leading-tight font-medium">{item.name}</span>
          </motion.button>
        ))}
      </div>
    </motion.div>
  </div>
);

export default PaymentsView;
