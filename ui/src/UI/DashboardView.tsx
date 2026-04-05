import { motion } from "framer-motion";
import { TrendingUp, Bot, ShieldAlert, FileText, Sparkles } from "lucide-react";
import CreditScoreRing from "./CreditScoreRing";

interface Props {
  onAgentClick: (agent: string) => void;
  onTriggerScam: () => void;
}

const agents = [
  { id: "wealth", label: "Wealth Optimizer", icon: TrendingUp, emoji: "📈" },
  { id: "teller", label: "Virtual Teller", icon: Bot, emoji: "🤖" },
  { id: "scam", label: "Scam Defender", icon: ShieldAlert, emoji: "🛡️" },
  { id: "claims", label: "Claims Adjuster", icon: FileText, emoji: "📋" },
];

const insights = [
  { text: "SBI Card Offer: 5% Cashback on Amazon", tag: "Offer" },
  { text: "HDFC FD maturity in 12 days – ₹50,000", tag: "Reminder" },
  { text: "Mutual Fund NAV up 2.3% this week", tag: "Update" },
];

const DashboardView = ({ onAgentClick, onTriggerScam }: Props) => (
  <div className="min-h-screen pb-24 pt-6 px-4 max-w-lg mx-auto">
    {/* Header */}
    <motion.div
      initial={{ opacity: 0, y: 10 }}
      animate={{ opacity: 1, y: 0 }}
      className="mb-6"
    >
      <p className="text-muted-foreground text-sm">Good morning</p>
      <h1 className="font-display text-2xl font-bold text-foreground">
        Welcome, <span className="text-gradient-teal">Pramod!</span>
      </h1>
    </motion.div>

    {/* Financial Health Card */}
    <motion.div
      initial={{ opacity: 0, y: 20 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ delay: 0.1 }}
      className="glass rounded-2xl p-5 mb-6 teal-glow"
    >
      <div className="flex items-center justify-between">
        <div>
          <p className="text-xs uppercase tracking-wider text-muted-foreground mb-1">
            Total Balance
          </p>
          <p className="font-display text-3xl font-bold text-foreground">
            ₹1,20,000
          </p>
          <p className="mt-1 flex items-center gap-1 text-xs text-primary">
            <Sparkles size={12} /> All accounts linked
          </p>
        </div>
        <CreditScoreRing score={785} />
      </div>
    </motion.div>

    {/* Agent Grid */}
    <div className="grid grid-cols-2 gap-3 mb-6">
      {agents.map((agent, i) => (
        <motion.button
          key={agent.id}
          initial={{ opacity: 0, scale: 0.9 }}
          animate={{ opacity: 1, scale: 1 }}
          transition={{ delay: 0.2 + i * 0.08 }}
          onClick={() => onAgentClick(agent.id)}
          className="neu-raised rounded-2xl p-5 flex flex-col items-start gap-3 text-left transition-all hover:scale-[1.02] active:scale-[0.98] active:neu-pressed"
        >
          <div className="flex h-10 w-10 items-center justify-center rounded-xl bg-primary/10 text-lg">
            {agent.emoji}
          </div>
          <span className="font-display text-sm font-semibold text-foreground leading-tight">
            {agent.label}
          </span>
        </motion.button>
      ))}
    </div>

    {/* Scam test button */}
    <motion.button
      initial={{ opacity: 0 }}
      animate={{ opacity: 1 }}
      transition={{ delay: 0.6 }}
      onClick={onTriggerScam}
      className="mb-6 w-full flex items-center justify-center gap-2 rounded-xl border border-danger/20 bg-danger/5 px-4 py-2.5 text-xs text-danger font-medium transition-colors hover:bg-danger/10"
    >
      <ShieldAlert size={14} />
      Test Scam Alert
    </motion.button>

    {/* Insights Feed */}
    <motion.div
      initial={{ opacity: 0, y: 10 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ delay: 0.5 }}
    >
      <h2 className="font-display text-sm font-semibold text-muted-foreground mb-3 uppercase tracking-wider">
        Insights
      </h2>
      <div className="space-y-2">
        {insights.map((item, i) => (
          <div
            key={i}
            className="glass rounded-xl px-4 py-3 flex items-center justify-between gap-3"
          >
            <p className="text-sm text-foreground flex-1">{item.text}</p>
            <span className="shrink-0 rounded-full bg-primary/10 px-2.5 py-0.5 text-[10px] font-medium text-primary">
              {item.tag}
            </span>
          </div>
        ))}
      </div>
    </motion.div>
  </div>
);

export default DashboardView;
