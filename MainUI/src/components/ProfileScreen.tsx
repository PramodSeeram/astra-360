import { useState } from "react";
import { motion } from "framer-motion";
import {
  User,
  ChevronRight,
  Fingerprint,
  Shield,
  Lock,
  LogOut,
  Building2,
  CheckCircle2,
  Smartphone,
  KeyRound,
} from "lucide-react";

interface Props {
  onLogout: () => void;
}

const linkedAccounts = [
  {
    bank: "State Bank of India",
    shortName: "SBI",
    type: "Savings Account",
    accNo: "••••6789",
    color: "bg-blue-600",
  },
  {
    bank: "HDFC Bank",
    shortName: "HDFC",
    type: "Savings Account",
    accNo: "••••4321",
    color: "bg-red-600",
  },
  {
    bank: "HDFC Bank",
    shortName: "HDFC",
    type: "Credit Card",
    accNo: "••••4823",
    color: "bg-red-600",
  },
  {
    bank: "ICICI Bank",
    shortName: "ICICI",
    type: "Credit Card",
    accNo: "••••8905",
    color: "bg-orange-600",
  },
];

interface SecuritySetting {
  icon: typeof Shield;
  label: string;
  desc: string;
  hasToggle: boolean;
  defaultOn: boolean;
}

const securitySettings: SecuritySetting[] = [
  {
    icon: Fingerprint,
    label: "Biometric Login",
    desc: "Use fingerprint or face unlock",
    hasToggle: true,
    defaultOn: true,
  },
  {
    icon: Smartphone,
    label: "Two-Factor Authentication",
    desc: "SMS + App verification",
    hasToggle: true,
    defaultOn: true,
  },
  {
    icon: KeyRound,
    label: "Change PIN",
    desc: "Update your 4-digit Astra PIN",
    hasToggle: false,
    defaultOn: false,
  },
  {
    icon: Lock,
    label: "App Lock Timeout",
    desc: "Lock after 2 minutes of inactivity",
    hasToggle: true,
    defaultOn: false,
  },
];

const NeonToggle = ({
  enabled,
  onToggle,
}: {
  enabled: boolean;
  onToggle: () => void;
}) => (
  <button
    onClick={onToggle}
    className={`relative h-7 w-12 rounded-full transition-colors duration-300 ${
      enabled ? "bg-[#CCFF00]" : "bg-white/10"
    }`}
  >
    <motion.div
      className={`absolute top-0.5 h-6 w-6 rounded-full shadow-md ${
        enabled ? "bg-black" : "bg-gray-400"
      }`}
      animate={{ left: enabled ? "calc(100% - 1.625rem)" : "0.125rem" }}
      transition={{ type: "spring", stiffness: 500, damping: 30 }}
    />
  </button>
);

const ProfileScreen = ({ onLogout }: Props) => {
  const [toggles, setToggles] = useState<Record<string, boolean>>(() => {
    const initial: Record<string, boolean> = {};
    securitySettings.forEach((s) => {
      if (s.hasToggle) initial[s.label] = s.defaultOn;
    });
    return initial;
  });

  const handleToggle = (label: string) => {
    setToggles((prev) => ({ ...prev, [label]: !prev[label] }));
  };

  return (
    <div className="min-h-screen pb-28 pt-6 px-4 max-w-lg mx-auto">
      {/* Profile Header */}
      <motion.div
        initial={{ opacity: 0, y: 10 }}
        animate={{ opacity: 1, y: 0 }}
        className="flex flex-col items-center mb-8"
      >
        <div className="relative mb-4">
          <div className="h-22 w-22 rounded-full bg-gradient-to-br from-[#CCFF00]/20 to-transparent border-2 border-[#CCFF00] flex items-center justify-center shadow-[0_0_25px_rgba(204,255,0,0.2)]"
               style={{ height: '5.5rem', width: '5.5rem' }}>
            <span className="font-display text-2xl font-bold text-white">
              PK
            </span>
          </div>
          <motion.div
            className="absolute -bottom-1 -right-1 h-6 w-6 rounded-full bg-[#CCFF00] flex items-center justify-center"
            initial={{ scale: 0 }}
            animate={{ scale: 1 }}
            transition={{ delay: 0.3, type: "spring" }}
          >
            <CheckCircle2 size={14} className="text-black" />
          </motion.div>
        </div>
        <h1 className="font-display text-xl font-bold text-white">
          Pramod Kumar
        </h1>
        <p className="text-sm text-gray-400 mt-0.5">+91 98765 43210</p>
        <p className="text-xs text-gray-500 mt-1">Joined Dec 2024</p>
      </motion.div>

      {/* Linked Accounts */}
      <motion.div
        initial={{ opacity: 0, y: 15 }}
        animate={{ opacity: 1, y: 0 }}
        transition={{ delay: 0.1 }}
        className="mb-6"
      >
        <div className="flex items-center gap-2 mb-3">
          <Building2 size={14} className="text-[#CCFF00]" />
          <h2 className="font-display text-[10px] font-semibold text-gray-400 uppercase tracking-widest">
            Linked Accounts (Account Aggregator)
          </h2>
        </div>

        <div className="space-y-2.5">
          {linkedAccounts.map((acc, i) => (
            <motion.div
              key={i}
              initial={{ opacity: 0, x: -15 }}
              animate={{ opacity: 1, x: 0 }}
              transition={{ delay: 0.15 + i * 0.06 }}
              className="rounded-2xl bg-[#1E1E1E] border border-white/5 px-4 py-3.5 flex items-center gap-3"
            >
              <div
                className={`h-10 w-10 rounded-xl ${acc.color} flex items-center justify-center shrink-0`}
              >
                <span className="text-white font-display text-[10px] font-bold">
                  {acc.shortName}
                </span>
              </div>
              <div className="flex-1 min-w-0">
                <p className="font-display text-sm font-semibold text-white truncate">
                  {acc.bank}
                </p>
                <p className="text-xs text-gray-400">
                  {acc.type} • {acc.accNo}
                </p>
              </div>
              <span className="shrink-0 inline-flex items-center gap-1 text-[10px] font-semibold text-emerald-400 bg-emerald-400/10 rounded-full px-2.5 py-1">
                <span className="h-1.5 w-1.5 rounded-full bg-emerald-400" />
                Linked
              </span>
            </motion.div>
          ))}
        </div>

        <motion.button
          initial={{ opacity: 0 }}
          animate={{ opacity: 1 }}
          transition={{ delay: 0.4 }}
          className="mt-3 w-full rounded-xl border border-dashed border-white/10 py-3 text-xs text-gray-400 font-medium hover:border-[#CCFF00]/30 hover:text-[#CCFF00] transition-colors"
        >
          + Link Another Account
        </motion.button>
      </motion.div>

      {/* Security Settings */}
      <motion.div
        initial={{ opacity: 0, y: 15 }}
        animate={{ opacity: 1, y: 0 }}
        transition={{ delay: 0.3 }}
        className="mb-6"
      >
        <div className="flex items-center gap-2 mb-3">
          <Shield size={14} className="text-[#CCFF00]" />
          <h2 className="font-display text-[10px] font-semibold text-gray-400 uppercase tracking-widest">
            Security Settings
          </h2>
        </div>

        <div className="rounded-3xl bg-[#1E1E1E] border border-white/5 overflow-hidden divide-y divide-white/5">
          {securitySettings.map((setting, i) => (
            <motion.div
              key={i}
              initial={{ opacity: 0, x: -10 }}
              animate={{ opacity: 1, x: 0 }}
              transition={{ delay: 0.35 + i * 0.05 }}
              className="flex items-center gap-4 px-5 py-4"
            >
              <div className="shrink-0 h-9 w-9 rounded-xl bg-white/5 flex items-center justify-center">
                <setting.icon
                  size={16}
                  className="text-gray-400"
                  strokeWidth={1.5}
                />
              </div>
              <div className="flex-1 min-w-0">
                <p className="font-display text-sm font-semibold text-white">
                  {setting.label}
                </p>
                <p className="text-[10px] text-gray-500 mt-0.5">
                  {setting.desc}
                </p>
              </div>
              {setting.hasToggle ? (
                <NeonToggle
                  enabled={toggles[setting.label] ?? false}
                  onToggle={() => handleToggle(setting.label)}
                />
              ) : (
                <ChevronRight size={14} className="text-gray-500 shrink-0" />
              )}
            </motion.div>
          ))}
        </div>
      </motion.div>

      {/* Logout */}
      <motion.button
        initial={{ opacity: 0, y: 10 }}
        animate={{ opacity: 1, y: 0 }}
        transition={{ delay: 0.55 }}
        whileTap={{ scale: 0.97 }}
        onClick={onLogout}
        className="w-full flex items-center justify-center gap-2 rounded-2xl border border-red-500/20 bg-red-500/10 px-4 py-3.5 text-sm text-red-500 font-semibold transition-colors hover:bg-red-500/15"
      >
        <LogOut size={16} />
        Log Out
      </motion.button>
    </div>
  );
};

export default ProfileScreen;
