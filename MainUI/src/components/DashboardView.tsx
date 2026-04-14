import { motion } from "framer-motion";
import { Gift, Clock, CreditCard, ShieldCheck, ArrowRight, ShieldAlert } from "lucide-react";
import CreditScoreGauge from "./CreditScoreRing";

interface Props {
  onAgentClick: (agent: string) => void;
  onTriggerScam: () => void;
  onNavigate?: (view: string) => void;
}

const cards = [
  { bank: "ICICI Bank", type: "AMAZON PAY", number: "•••• •••• •••• 8905", name: "Pramod Kumar", network: "VISA" },
  { bank: "HDFC Bank", type: "REGALIA", number: "•••• •••• •••• 4823", name: "Pramod Kumar", network: "Mastercard" },
  { bank: "SBI Card", type: "ELITE", number: "•••• •••• •••• 3301", name: "Pramod Kumar", network: "VISA" },
];

const insights = [
  { icon: Clock, title: "On Time Payments", desc: "Ensure you make all payments before the due date to improve your score." },
  { icon: CreditCard, title: "Keep old cards active", desc: "Total age of your credit activity boosts your credit score." },
  { icon: ShieldCheck, title: "Low credit usage", desc: "Keep utilization under 30% for best impact on score." },
  { icon: Gift, title: "Cashback rewards", desc: "You've earned ₹2,340 in rewards this month." },
];

const DashboardView = ({ onAgentClick, onTriggerScam, onNavigate }: Props) => (
  <div className="min-h-screen pb-24 pt-4 px-4 max-w-lg mx-auto">
    {/* Header */}
    <motion.div
      initial={{ opacity: 0, y: 10 }}
      animate={{ opacity: 1, y: 0 }}
      className="flex items-center justify-between mb-6"
    >
      <div className="flex items-center gap-3">
        <div className="h-10 w-10 rounded-full bg-primary flex items-center justify-center text-primary-foreground font-display font-bold text-sm">
          PK
        </div>
        <div>
          <p className="text-xs text-muted-foreground">Good morning</p>
          <p className="font-display text-base font-semibold text-foreground">Pramod Kumar</p>
        </div>
      </div>
      <button className="flex items-center gap-1.5 rounded-full border border-border px-3 py-1.5 text-xs text-muted-foreground hover:text-foreground hover:border-primary/30 transition-colors">
        <Gift size={14} className="text-primary" />
        Refer & Earn
      </button>
    </motion.div>

    {/* Credit Score Widget */}
    <motion.div
      initial={{ opacity: 0, y: 20 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ delay: 0.1 }}
      className="rounded-3xl bg-card border border-border/30 p-6 mb-6 neon-glow"
    >
      <p className="text-sm font-display font-semibold text-foreground mb-1">All about your credit Score</p>
      <p className="text-xs text-muted-foreground mb-4">Get insights and track your credit standing.</p>
      <CreditScoreGauge score={780} />
      <p className="text-center text-[10px] text-muted-foreground mt-2">contacting RBI approved credit bureau</p>
    </motion.div>

    {/* Credit Cards - Horizontal Scroll */}
    <motion.div
      initial={{ opacity: 0, y: 20 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ delay: 0.2 }}
      className="mb-6"
    >
      <div className="flex items-center justify-between mb-3">
        <h2 className="font-display text-xs font-semibold text-muted-foreground uppercase tracking-wider">
          Your Cards
        </h2>
        <button className="text-xs text-primary font-medium">Add / Manage Cards</button>
      </div>
      <div className="flex gap-3 overflow-x-auto pb-2 -mx-1 px-1 snap-x snap-mandatory">
        {cards.map((card, i) => (
          <motion.div
            key={i}
            initial={{ opacity: 0, scale: 0.95 }}
            animate={{ opacity: 1, scale: 1 }}
            transition={{ delay: 0.25 + i * 0.08 }}
            className="shrink-0 w-[280px] snap-center rounded-2xl gradient-neon p-5 flex flex-col justify-between h-[160px]"
          >
            <div className="flex items-start justify-between">
              <div>
                <p className="font-display text-xs font-bold text-primary-foreground/80">{card.bank}</p>
                <p className="font-display text-[10px] text-primary-foreground/50 mt-0.5">{card.type}</p>
              </div>
              <CreditCard size={20} className="text-primary-foreground/60" />
            </div>
            <div>
              <p className="font-display text-sm font-medium text-primary-foreground tracking-[3px] mb-2">
                {card.number}
              </p>
              <div className="flex items-end justify-between">
                <p className="text-[10px] text-primary-foreground/60">{card.name}</p>
                <p className="font-display text-xs font-bold text-primary-foreground/80">{card.network}</p>
              </div>
            </div>
          </motion.div>
        ))}
      </div>
    </motion.div>

    {/* Insights Grid */}
    <motion.div
      initial={{ opacity: 0, y: 15 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ delay: 0.35 }}
      className="mb-6"
    >
      <h2 className="font-display text-xs font-semibold text-muted-foreground uppercase tracking-wider mb-3">
        Insights for you
      </h2>
      <div className="grid grid-cols-2 gap-3">
        {insights.map((item, i) => (
          <motion.div
            key={i}
            initial={{ opacity: 0, y: 10 }}
            animate={{ opacity: 1, y: 0 }}
            transition={{ delay: 0.4 + i * 0.06 }}
            className="rounded-2xl bg-card border border-border/30 p-4 flex flex-col gap-3 hover:border-primary/20 transition-colors cursor-pointer"
          >
            <div className="flex h-10 w-10 items-center justify-center rounded-xl bg-primary/10">
              <item.icon size={18} className="text-primary" strokeWidth={1.5} />
            </div>
            <div>
              <p className="font-display text-sm font-semibold text-foreground leading-tight mb-1">{item.title}</p>
              <p className="text-[10px] text-muted-foreground leading-relaxed">{item.desc}</p>
            </div>
          </motion.div>
        ))}
      </div>
    </motion.div>

    {/* AI Agents quick access */}
    <motion.div
      initial={{ opacity: 0, y: 15 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ delay: 0.5 }}
      className="mb-6"
    >
      <h2 className="font-display text-xs font-semibold text-muted-foreground uppercase tracking-wider mb-3">
        AI Agents
      </h2>
      <div className="grid grid-cols-2 gap-3">
        {[
          { id: "wealth", label: "Wealth Optimizer", emoji: "📈" },
          { id: "teller", label: "Virtual Teller", emoji: "🤖" },
          { id: "scam", label: "Scam Defender", emoji: "🛡️" },
          { id: "claims", label: "Claims Adjuster", emoji: "📋" },
        ].map((agent, i) => (
          <motion.button
            key={agent.id}
            initial={{ opacity: 0, scale: 0.95 }}
            animate={{ opacity: 1, scale: 1 }}
            transition={{ delay: 0.55 + i * 0.06 }}
            onClick={() => onAgentClick(agent.id)}
            className="rounded-2xl bg-card border border-border/30 p-4 flex items-center gap-3 text-left transition-all hover:border-primary/30 active:scale-[0.98]"
          >
            <span className="text-lg">{agent.emoji}</span>
            <span className="font-display text-xs font-semibold text-foreground">{agent.label}</span>
          </motion.button>
        ))}
      </div>
    </motion.div>

    {/* Scam test */}
    <motion.button
      initial={{ opacity: 0 }}
      animate={{ opacity: 1 }}
      transition={{ delay: 0.7 }}
      onClick={onTriggerScam}
      className="w-full flex items-center justify-center gap-2 rounded-2xl border border-danger/20 bg-danger/5 px-4 py-3 text-xs text-danger font-medium transition-colors hover:bg-danger/10"
    >
      <ShieldAlert size={14} />
      Test Scam Alert
    </motion.button>
  </div>
);

export default DashboardView;
