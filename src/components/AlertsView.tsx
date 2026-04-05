import { motion } from "framer-motion";
import { ShieldAlert, TrendingUp, CreditCard, Bell, AlertTriangle, CheckCircle2, Info } from "lucide-react";

interface Alert {
  id: number;
  type: "warning" | "info" | "success" | "critical";
  agent: string;
  title: string;
  description: string;
  time: string;
}

const alerts: Alert[] = [
  {
    id: 1,
    type: "critical",
    agent: "🛡️ Scam Defender",
    title: "Suspicious Login Detected",
    description: "Unrecognized device attempted login from Mumbai at 2:14 AM. Device has been blocked.",
    time: "2 min ago",
  },
  {
    id: 2,
    type: "warning",
    agent: "📈 Wealth Optimizer",
    title: "Portfolio Rebalancing Needed",
    description: "Your equity allocation has drifted 8% above target. Consider rebalancing to maintain risk profile.",
    time: "1 hr ago",
  },
  {
    id: 3,
    type: "success",
    agent: "🤖 Virtual Teller",
    title: "UPI Payment Successful",
    description: "₹2,500 transferred to Swiggy via UPI. Reference: TXN928374651.",
    time: "3 hrs ago",
  },
  {
    id: 4,
    type: "info",
    agent: "📋 Claims Adjuster",
    title: "Claim #4521 Under Review",
    description: "Your health insurance claim for ₹15,000 is being processed. Expected resolution: 3-5 days.",
    time: "5 hrs ago",
  },
  {
    id: 5,
    type: "warning",
    agent: "🛡️ Scam Defender",
    title: "Card Used Internationally",
    description: "Your HDFC credit card ending 4823 was used at AMAZON US for ₹20,000.",
    time: "8 hrs ago",
  },
  {
    id: 6,
    type: "success",
    agent: "📈 Wealth Optimizer",
    title: "SIP Executed Successfully",
    description: "Monthly SIP of ₹5,000 in Axis Bluechip Fund processed. NAV: ₹48.23.",
    time: "1 day ago",
  },
  {
    id: 7,
    type: "info",
    agent: "🤖 Virtual Teller",
    title: "HDFC FD Maturity Reminder",
    description: "Your Fixed Deposit of ₹50,000 matures in 12 days. Consider reinvestment options.",
    time: "1 day ago",
  },
];

const typeConfig = {
  critical: { icon: AlertTriangle, color: "text-danger", bg: "bg-danger/10", border: "border-danger/20" },
  warning: { icon: Bell, color: "text-yellow-400", bg: "bg-yellow-400/10", border: "border-yellow-400/20" },
  success: { icon: CheckCircle2, color: "text-primary", bg: "bg-primary/10", border: "border-primary/20" },
  info: { icon: Info, color: "text-blue-400", bg: "bg-blue-400/10", border: "border-blue-400/20" },
};

const AlertsView = () => (
  <div className="min-h-screen pb-24 pt-6 px-4 max-w-lg mx-auto">
    <motion.div initial={{ opacity: 0, y: 10 }} animate={{ opacity: 1, y: 0 }} className="mb-6">
      <h1 className="font-display text-2xl font-bold text-foreground">Alerts</h1>
      <p className="text-muted-foreground text-sm">Real-time updates from your AI agents</p>
    </motion.div>

    {/* Filter pills */}
    <motion.div
      initial={{ opacity: 0 }}
      animate={{ opacity: 1 }}
      transition={{ delay: 0.1 }}
      className="flex gap-2 mb-5 overflow-x-auto pb-1"
    >
      {["All", "Critical", "Warnings", "Info"].map((f, i) => (
        <button
          key={f}
          className={`shrink-0 rounded-full px-4 py-1.5 text-xs font-medium transition-colors ${
            i === 0
              ? "gradient-teal text-primary-foreground"
              : "glass text-muted-foreground hover:text-foreground"
          }`}
        >
          {f}
        </button>
      ))}
    </motion.div>

    {/* Alert list */}
    <div className="space-y-3">
      {alerts.map((alert, i) => {
        const config = typeConfig[alert.type];
        const Icon = config.icon;
        return (
          <motion.div
            key={alert.id}
            initial={{ opacity: 0, y: 15 }}
            animate={{ opacity: 1, y: 0 }}
            transition={{ delay: 0.15 + i * 0.06 }}
            className={`glass rounded-2xl p-4 border ${config.border}`}
          >
            <div className="flex gap-3">
              <div className={`shrink-0 flex h-9 w-9 items-center justify-center rounded-xl ${config.bg}`}>
                <Icon size={16} className={config.color} />
              </div>
              <div className="flex-1 min-w-0">
                <div className="flex items-start justify-between gap-2">
                  <p className="font-display text-sm font-semibold text-foreground leading-tight">
                    {alert.title}
                  </p>
                  <span className="shrink-0 text-[10px] text-muted-foreground">{alert.time}</span>
                </div>
                <p className="text-xs text-muted-foreground mt-1 leading-relaxed">
                  {alert.description}
                </p>
                <p className="text-[10px] font-semibold text-primary mt-2 uppercase tracking-wider">
                  {alert.agent}
                </p>
              </div>
            </div>
          </motion.div>
        );
      })}
    </div>
  </div>
);

export default AlertsView;
