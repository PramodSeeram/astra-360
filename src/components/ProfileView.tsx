import { useState } from "react";
import { motion } from "framer-motion";
import { User, CreditCard, Building2, Shield, LogOut, ChevronRight, Fingerprint, Bell, Moon } from "lucide-react";

interface Props {
  onLogout: () => void;
}

const linkedAccounts = [
  { bank: "SBI", type: "Savings", number: "••••4521", balance: "₹45,200", color: "bg-blue-500" },
  { bank: "HDFC", type: "Savings", number: "••••8834", balance: "₹74,800", color: "bg-red-500" },
  { bank: "ICICI", type: "Credit Card", number: "••••3301", balance: "₹12,400 due", color: "bg-orange-500" },
];

const ProfileView = ({ onLogout }: Props) => {
  const [biometric, setBiometric] = useState(true);
  const [notifications, setNotifications] = useState(true);
  const [darkMode, setDarkMode] = useState(true);

  return (
    <div className="min-h-screen pb-24 pt-6 px-4 max-w-lg mx-auto">
      {/* Profile Header */}
      <motion.div
        initial={{ opacity: 0, y: 10 }}
        animate={{ opacity: 1, y: 0 }}
        className="flex items-center gap-4 mb-8"
      >
        <div className="flex h-16 w-16 items-center justify-center rounded-2xl gradient-teal text-primary-foreground text-xl font-bold font-display">
          PK
        </div>
        <div>
          <h1 className="font-display text-xl font-bold text-foreground">Pramod Kumar</h1>
          <p className="text-sm text-muted-foreground">+91 98765 43210</p>
          <p className="text-xs text-primary mt-0.5">Astra 360 Premium Member</p>
        </div>
      </motion.div>

      {/* Linked Accounts */}
      <motion.div
        initial={{ opacity: 0, y: 15 }}
        animate={{ opacity: 1, y: 0 }}
        transition={{ delay: 0.1 }}
        className="mb-6"
      >
        <h2 className="font-display text-sm font-semibold text-muted-foreground mb-3 uppercase tracking-wider">
          Linked Accounts
        </h2>
        <div className="space-y-2">
          {linkedAccounts.map((acc, i) => (
            <motion.div
              key={i}
              initial={{ opacity: 0, x: -10 }}
              animate={{ opacity: 1, x: 0 }}
              transition={{ delay: 0.15 + i * 0.06 }}
              className="glass rounded-xl px-4 py-3 flex items-center gap-3"
            >
              <div className={`h-8 w-8 rounded-lg ${acc.color} flex items-center justify-center`}>
                {acc.type === "Credit Card" ? (
                  <CreditCard size={14} className="text-white" />
                ) : (
                  <Building2 size={14} className="text-white" />
                )}
              </div>
              <div className="flex-1 min-w-0">
                <p className="text-sm font-semibold text-foreground">
                  {acc.bank} {acc.type}
                </p>
                <p className="text-xs text-muted-foreground">{acc.number}</p>
              </div>
              <p className="text-sm font-display font-semibold text-foreground">{acc.balance}</p>
            </motion.div>
          ))}
        </div>
      </motion.div>

      {/* Settings */}
      <motion.div
        initial={{ opacity: 0, y: 15 }}
        animate={{ opacity: 1, y: 0 }}
        transition={{ delay: 0.3 }}
        className="mb-6"
      >
        <h2 className="font-display text-sm font-semibold text-muted-foreground mb-3 uppercase tracking-wider">
          Settings
        </h2>
        <div className="glass rounded-2xl divide-y divide-border/30 overflow-hidden">
          <ToggleRow
            icon={<Fingerprint size={16} />}
            label="Biometric Login"
            value={biometric}
            onChange={setBiometric}
          />
          <ToggleRow
            icon={<Bell size={16} />}
            label="Push Notifications"
            value={notifications}
            onChange={setNotifications}
          />
          <ToggleRow
            icon={<Moon size={16} />}
            label="Dark Mode"
            value={darkMode}
            onChange={setDarkMode}
          />
        </div>
      </motion.div>

      {/* Security */}
      <motion.div
        initial={{ opacity: 0, y: 15 }}
        animate={{ opacity: 1, y: 0 }}
        transition={{ delay: 0.4 }}
        className="mb-6"
      >
        <h2 className="font-display text-sm font-semibold text-muted-foreground mb-3 uppercase tracking-wider">
          Security
        </h2>
        <div className="glass rounded-2xl overflow-hidden">
          <button className="w-full flex items-center gap-3 px-4 py-3.5 text-left hover:bg-white/5 transition-colors">
            <Shield size={16} className="text-primary" />
            <span className="flex-1 text-sm text-foreground">Change PIN</span>
            <ChevronRight size={14} className="text-muted-foreground" />
          </button>
          <div className="border-t border-border/30" />
          <button className="w-full flex items-center gap-3 px-4 py-3.5 text-left hover:bg-white/5 transition-colors">
            <Shield size={16} className="text-primary" />
            <span className="flex-1 text-sm text-foreground">Two-Factor Authentication</span>
            <ChevronRight size={14} className="text-muted-foreground" />
          </button>
        </div>
      </motion.div>

      {/* Logout */}
      <motion.button
        initial={{ opacity: 0 }}
        animate={{ opacity: 1 }}
        transition={{ delay: 0.5 }}
        onClick={onLogout}
        className="w-full flex items-center justify-center gap-2 rounded-xl border border-danger/20 bg-danger/5 px-4 py-3 text-sm text-danger font-medium transition-colors hover:bg-danger/10"
      >
        <LogOut size={16} />
        Log Out
      </motion.button>
    </div>
  );
};

const ToggleRow = ({
  icon,
  label,
  value,
  onChange,
}: {
  icon: React.ReactNode;
  label: string;
  value: boolean;
  onChange: (v: boolean) => void;
}) => (
  <button
    onClick={() => onChange(!value)}
    className="w-full flex items-center gap-3 px-4 py-3.5 text-left hover:bg-white/5 transition-colors"
  >
    <span className="text-primary">{icon}</span>
    <span className="flex-1 text-sm text-foreground">{label}</span>
    <div
      className={`relative h-6 w-11 rounded-full transition-colors ${
        value ? "bg-primary" : "bg-muted"
      }`}
    >
      <div
        className={`absolute top-0.5 h-5 w-5 rounded-full bg-white shadow transition-transform ${
          value ? "translate-x-[22px]" : "translate-x-0.5"
        }`}
      />
    </div>
  </button>
);

export default ProfileView;
